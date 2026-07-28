"""Pure aggregation and bounded exports for the real ClinVar history pilot."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.vcv_history import validate_vcv_accession
from variant_time_machine.vcv_history_store import list_histories, load_history

MAX_CANDIDATES = 10
MAX_BATCH_MANIFEST_BYTES = 1024 * 1024
MAX_EXPORT_BYTES = 4 * 1024 * 1024
DEFAULT_OUTPUT_ROOT = Path("data/pilot_results")
NOTICE = (
    "Real pilot data from official ClinVar records. Not yet suitable for model "
    "training or clinical use."
)
OFFICIAL_EFETCH_PREFIX = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
OUTPUT_FILENAMES = (
    "pilot_results.csv",
    "pilot_summary.json",
    "pilot_report.md",
    "transfer_manifest.json",
    "manual_review.csv",
)
RESULT_FIELDS = (
    "Data label",
    "VCV accession",
    "Variation ID",
    "gene",
    "first version",
    "newest version",
    "versions retrieved",
    "first aggregate germline classification",
    "newest aggregate germline classification",
    "detected change category",
    "classification change count",
    "first change",
    "review-status change",
    "submission change",
    "automatic confidence",
    "automatic result",
    "manually reviewed status",
    "reviewer decision",
    "manual confirmed result",
    "review notes",
    "verification complete",
    "verification total",
    "warnings",
    "bytes transferred",
    "source information",
)
MANUAL_REVIEW_FIELDS = (
    "VCV accession",
    "Variation ID",
    "gene",
    "automatic result",
    "reviewer decision",
    "manual confirmed result",
    "manually reviewed status",
    "review notes",
    "verification complete",
    "verification total",
    "source information",
)
_DIRECTIONAL_CHANGES = frozenset(
    {
        "VUS_to_Pathogenic",
        "VUS_to_Likely_Pathogenic",
        "VUS_to_Benign",
        "VUS_to_Likely_Benign",
        "Pathogenic_to_VUS",
        "Benign_to_VUS",
        "Became_Conflicting",
        "Conflict_Resolved",
    }
)
_GERMLINE_CHANGES = _DIRECTIONAL_CHANGES | {"Other_Germline_Change"}


class PilotResultsError(ValueError):
    """Raised when pilot inputs or outputs are malformed or unsafe."""


def _path(value: Path, field: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{field} must be supplied as a pathlib.Path.")
    return value


def _timestamp(value: str | None) -> str:
    return value or datetime.now(UTC).isoformat()


def _read_batch_manifest(output_root: Path) -> dict[str, Any] | None:
    path = output_root / "batch_manifest.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PilotResultsError("batch_manifest.json must be a regular file.")
    if path.stat().st_size > MAX_BATCH_MANIFEST_BYTES:
        raise PilotResultsError("batch_manifest.json exceeds its 1 MB limit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotResultsError("batch_manifest.json is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise PilotResultsError("batch_manifest.json must contain an object.")
    return payload


def _candidate_items(payload: Mapping[str, Any]) -> list[Any]:
    for key in (
        "candidates",
        "candidates_attempted",
        "attempted_candidates",
        "attempts",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [
                {
                    "vcv_accession": accession,
                    **(details if isinstance(details, dict) else {}),
                }
                for accession, details in value.items()
            ]
    raise PilotResultsError(
        "batch_manifest.json must list attempted candidates in candidates, "
        "candidates_attempted, attempted_candidates, or attempts."
    )


def _nonnegative_manifest_integer(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field, 0)
    if type(value) is not int or value < 0:
        raise PilotResultsError(
            f"batch_manifest.json {field} must be a nonnegative integer."
        )
    return value


def _selection_requests(
    payload: Mapping[str, Any], selection_bytes: int
) -> tuple[list[dict[str, object]], int]:
    value = payload.get("candidate_selection_requests", [])
    if type(value) is int:
        if value < 0:
            raise PilotResultsError(
                "batch_manifest.json candidate_selection_requests must be nonnegative."
            )
        return [], value
    if not isinstance(value, list):
        raise PilotResultsError(
            "batch_manifest.json candidate_selection_requests must be a list."
        )
    if len(value) > MAX_CANDIDATES:
        raise PilotResultsError(
            "candidate_selection_requests is limited to 10 provenance records."
        )
    fields = {
        "accession",
        "source_request",
        "response_bytes",
        "retrieved_at_utc",
    }
    requests: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != fields:
            raise PilotResultsError(
                "Each candidate selection request must have exactly accession, "
                "source_request, response_bytes, and retrieved_at_utc."
            )
        try:
            accession = validate_vcv_accession(item["accession"]).identifier
        except (TypeError, ValueError) as exc:
            raise PilotResultsError(
                "A candidate selection request has an invalid accession."
            ) from exc
        source_request = item["source_request"]
        retrieved_at_utc = item["retrieved_at_utc"]
        if not isinstance(source_request, str) or not source_request.strip():
            raise PilotResultsError(
                "Candidate selection source_request must be nonempty text."
            )
        if not isinstance(retrieved_at_utc, str) or not retrieved_at_utc.strip():
            raise PilotResultsError(
                "Candidate selection retrieved_at_utc must be nonempty text."
            )
        response_bytes = item["response_bytes"]
        if type(response_bytes) is not int or response_bytes < 0:
            raise PilotResultsError(
                "Candidate selection response_bytes must be a nonnegative integer."
            )
        requests.append(
            {
                "accession": accession,
                "source_request": source_request.strip(),
                "response_bytes": response_bytes,
                "retrieved_at_utc": retrieved_at_utc.strip(),
            }
        )
    if sum(int(item["response_bytes"]) for item in requests) != selection_bytes:
        raise PilotResultsError(
            "candidate_selection_requests response bytes must sum to "
            "candidate_selection_bytes."
        )
    return requests, len(requests)


def _attempts(
    history_root: Path, output_root: Path
) -> tuple[list[dict[str, Any]], int, list[dict[str, object]], int, bool]:
    payload = _read_batch_manifest(output_root)
    if payload is None:
        items: list[Any] = list(list_histories(history_root))
        selection_bytes = 0
        selection_requests: list[dict[str, object]] = []
        selection_request_count = 0
    else:
        items = _candidate_items(payload)
        selection_bytes = _nonnegative_manifest_integer(
            payload, "candidate_selection_bytes"
        )
        selection_requests, selection_request_count = _selection_requests(
            payload, selection_bytes
        )
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            details: dict[str, Any] = {"vcv_accession": item}
        elif isinstance(item, dict):
            details = dict(item)
            if details.get("attempted") is False:
                continue
        else:
            raise PilotResultsError(
                "Every attempted candidate must be text or an object."
            )
        raw_accession = next(
            (
                details[key]
                for key in ("vcv_accession", "accession", "candidate")
                if isinstance(details.get(key), str)
            ),
            None,
        )
        if raw_accession is None:
            raise PilotResultsError(
                "An attempted candidate is missing its VCV accession."
            )
        try:
            accession = validate_vcv_accession(raw_accession).accession
        except (TypeError, ValueError) as exc:
            raise PilotResultsError(
                f"Invalid attempted VCV accession: {raw_accession}"
            ) from exc
        if accession in seen:
            raise PilotResultsError("Attempted VCV accessions must be unique.")
        seen.add(accession)
        details["vcv_accession"] = accession
        attempts.append(details)
    if len(attempts) > MAX_CANDIDATES:
        raise PilotResultsError("The real pilot is limited to 10 candidates.")
    return (
        attempts,
        selection_bytes,
        selection_requests,
        selection_request_count,
        payload is not None,
    )


def _objects(value: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise PilotResultsError(f"Stored {key}.json has an invalid shape.")
    if not all(isinstance(item, dict) for item in value[key]):
        raise PilotResultsError(f"Stored {key}.json entries must be objects.")
    return value[key]


def _record(item: Mapping[str, Any]) -> dict[str, Any] | None:
    value = item.get("record")
    return value if isinstance(value, dict) else None


def _available_records(versions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [
        record
        for item in versions
        if item.get("status") in {"available", "deleted/replaced"}
        and (record := _record(item)) is not None
        and isinstance(record.get("version"), int)
    ]
    return sorted(records, key=lambda item: item["version"])


def _germline(record: Mapping[str, Any], field: str) -> Any:
    block = record.get("germline")
    return block.get(field) if isinstance(block, dict) else None


def _unique_text(values: Sequence[object]) -> list[str]:
    return list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )


def _warning_text(
    history: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
    extra: Sequence[object],
) -> str:
    manifest = history.get("manifest")
    metadata = history.get("metadata")
    values: list[object] = list(extra)
    if isinstance(manifest, dict) and isinstance(manifest.get("warnings"), list):
        values.extend(manifest["warnings"])
    if isinstance(metadata, dict):
        summary = metadata.get("summary")
        if isinstance(summary, dict) and isinstance(
            summary.get("unresolved_warnings"), list
        ):
            values.extend(summary["unresolved_warnings"])
    for comparison in comparisons:
        warnings = comparison.get("warnings")
        if isinstance(warnings, list):
            values.extend(warnings)
        if comparison.get("detected_classification_change") == "Non_Germline_Change":
            values.append(
                "Non_Germline_Change was normalized to No_Germline_Change; "
                "somatic/oncogenic changes are not germline results."
            )
    return " | ".join(_unique_text(values))


def _category(
    records: Sequence[Mapping[str, Any]], comparisons: Sequence[Mapping[str, Any]]
) -> str:
    if len(records) < 2:
        return "Unable_to_Compare"
    labels = [item.get("detected_classification_change") for item in comparisons]
    changes = [label for label in labels if label in _GERMLINE_CHANGES]
    if changes:
        return str(changes[0])
    if any(_germline(record, "classification") in {None, ""} for record in records):
        return "Missing_Data"
    if not comparisons or any(
        label in {"Missing_Classification", None} for label in labels
    ):
        return "Missing_Data"
    if any(label == "Unable_to_Compare" for label in labels):
        return "Unable_to_Compare"
    return "No_Germline_Change"


def _confidence(category: str, comparisons: Sequence[Mapping[str, Any]]) -> str:
    if category == "Unable_to_Compare":
        return "unable"
    values = {item.get("confidence") for item in comparisons}
    if category == "Missing_Data" or "limited" in values or "unable" in values:
        return "limited"
    return "high"


def _source_information(
    accession: str, manifest: Mapping[str, Any], history_exists: bool
) -> str:
    requests = manifest.get("source_requests")
    official = (
        [
            item.get("request")
            for item in requests
            if isinstance(item, dict) and isinstance(item.get("request"), str)
        ]
        if isinstance(requests, list)
        else []
    )
    raw = []
    if history_exists and isinstance(requests, list):
        raw = [
            f"{accession}/raw/{item['identifier']}.xml"
            for item in requests
            if isinstance(item, dict) and isinstance(item.get("identifier"), str)
        ]
    return json.dumps(
        {
            "official_source_requests": _unique_text(official),
            "local_raw_artifacts": raw,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_official_history(
    history_root: Path,
    accession: str,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
) -> None:
    """Require official provenance, matching digest, and retained response bodies."""
    digest = manifest.get("automatic_artifact_digest")
    if not isinstance(digest, str) or review.get("automatic_artifact_digest") != digest:
        raise PilotResultsError("History automatic evidence digest is inconsistent.")
    requests = manifest.get("source_requests")
    if not isinstance(requests, list) or not requests:
        raise PilotResultsError("History has no official source requests.")
    raw_root = history_root / accession / "raw"
    for item in requests:
        if not isinstance(item, dict):
            raise PilotResultsError("History source request is invalid.")
        source = item.get("request")
        identifier = item.get("identifier")
        response_bytes = item.get("response_bytes")
        if not isinstance(source, str) or not source.startswith(OFFICIAL_EFETCH_PREFIX):
            raise PilotResultsError("History source is not official ClinVar EFetch.")
        if not isinstance(identifier, str):
            raise PilotResultsError("History source identifier is invalid.")
        validate_vcv_accession(identifier)
        if type(response_bytes) is not int or response_bytes < 0:
            raise PilotResultsError("History source byte count is invalid.")
        if response_bytes:
            raw_path = raw_root / f"{identifier}.xml"
            if raw_path.is_symlink() or not raw_path.is_file():
                raise PilotResultsError("Retained raw response is missing.")
            if raw_path.stat().st_size != response_bytes:
                raise PilotResultsError("Retained raw response size does not match.")


def _attempt_transfer_bytes(attempt: Mapping[str, Any]) -> int:
    for key in ("bytes_transferred", "transfer_bytes", "total_bytes"):
        if key not in attempt:
            continue
        value = attempt[key]
        if type(value) is not int or value < 0:
            raise PilotResultsError(f"Candidate {key} must be a nonnegative integer.")
        return value
    return 0


def _history_transfer_bytes(manifest: Mapping[str, Any]) -> int:
    value = manifest.get("total_bytes")
    if type(value) is not int or value < 0:
        raise PilotResultsError(
            "Stored history manifest total_bytes must be a nonnegative integer."
        )
    return value


def _failure(attempt: Mapping[str, Any]) -> str:
    for key in ("failure", "error", "message"):
        value = attempt.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "History was attempted but no saved history artifact is available."


def _local_storage_bytes(history_root: Path, accession: str) -> int:
    directory = history_root / accession
    total = 0
    for item in directory.rglob("*"):
        if item.is_symlink():
            raise PilotResultsError("Symbolic links are not allowed in history trees.")
        if item.is_file():
            total += item.stat().st_size
    return total


def _row(
    history_root: Path, attempt: Mapping[str, Any]
) -> tuple[dict[str, object], dict[str, object], int, bool]:
    accession = str(attempt["vcv_accession"])
    saved = accession in list_histories(history_root)
    if not saved:
        transfer = _attempt_transfer_bytes(attempt)
        failure = _failure(attempt)
        sources = _source_information(accession, attempt, False)
        row: dict[str, object] = {field: "" for field in RESULT_FIELDS}
        row.update(
            {
                "Data label": NOTICE,
                "VCV accession": accession,
                "versions retrieved": 0,
                "detected change category": "Unable_to_Compare",
                "automatic confidence": "unable",
                "automatic result": "Unable_to_Compare",
                "manually reviewed status": "unreviewed",
                "warnings": failure,
                "bytes transferred": transfer,
                "source information": sources,
            }
        )
        transfer_entry = {
            "VCV accession": accession,
            "status": "failed",
            "failure": failure,
            "reused": bool(attempt.get("reused", False)),
            "bytes_transferred": transfer,
            "history_response_bytes": transfer,
            "actual_new_batch_bytes": transfer,
            "source_information": json.loads(sources),
        }
        return row, transfer_entry, 0, False

    history = load_history(history_root, accession)
    versions = _objects(history.get("versions"), "versions")
    comparisons = _objects(history.get("comparisons"), "comparisons")
    records = _available_records(versions)
    manifest = history.get("manifest")
    review = history.get("review")
    if not isinstance(manifest, dict) or not isinstance(review, dict):
        raise PilotResultsError("Stored manifest or review has an invalid shape.")
    _validate_official_history(history_root, accession, manifest, review)
    category = _category(records, comparisons)
    germline_changes = [
        item
        for item in comparisons
        if item.get("detected_classification_change") in _GERMLINE_CHANGES
    ]
    first_change = germline_changes[0] if germline_changes else None
    review_changes = _unique_text(
        [
            f"{item.get('earlier_review_status') or 'missing'} to "
            f"{item.get('later_review_status') or 'missing'}"
            for item in comparisons
            if item.get("earlier_review_status") != item.get("later_review_status")
        ]
    )
    submission_values = [item.get("submissions_changed") for item in comparisons]
    submission_change = (
        "yes"
        if True in submission_values
        else "unknown"
        if None in submission_values
        else "no"
    )
    first = records[0] if records else {}
    newest = records[-1] if records else {}
    source = _source_information(accession, manifest, True)
    warnings = (
        list(attempt.get("warnings", []))
        if isinstance(attempt.get("warnings"), list)
        else []
    )
    if attempt.get("failure"):
        warnings.append(attempt["failure"])
    transfer = _history_transfer_bytes(manifest)
    new_batch_transfer = _attempt_transfer_bytes(attempt)
    manually_verified = review.get("status") == "manually_verified"
    reviewer_decision = str(review.get("reviewer_decision") or "")
    manual_result = reviewer_decision if manually_verified else ""
    review_notes = str(review.get("notes") or "")
    verification = review.get("verification")
    if not isinstance(verification, dict) or any(
        type(value) is not bool for value in verification.values()
    ):
        raise PilotResultsError("Stored review verification has an invalid shape.")
    verification_complete = sum(verification.values())
    variation_id = first.get("variation_id") or newest.get("variation_id") or ""
    genes = _unique_text(
        [gene for record in records for gene in record.get("genes", [])]
    )
    first_change_text = ""
    if first_change:
        first_change_text = (
            f"{first_change.get('earlier_identifier', '')} to "
            f"{first_change.get('later_identifier', '')}: "
            f"{first_change.get('detected_classification_change', '')}"
        )
    row = {
        "Data label": NOTICE,
        "VCV accession": accession,
        "Variation ID": variation_id,
        "gene": "; ".join(genes),
        "first version": first.get("version", ""),
        "newest version": newest.get("version", ""),
        "versions retrieved": len(records),
        "first aggregate germline classification": _germline(first, "classification"),
        "newest aggregate germline classification": _germline(newest, "classification"),
        "detected change category": category,
        "classification change count": len(germline_changes),
        "first change": first_change_text,
        "review-status change": "; ".join(review_changes),
        "submission change": submission_change,
        "automatic confidence": _confidence(category, comparisons),
        "automatic result": category,
        "manually reviewed status": str(review.get("status") or "unreviewed"),
        "reviewer decision": reviewer_decision,
        "manual confirmed result": manual_result,
        "review notes": review_notes,
        "verification complete": verification_complete,
        "verification total": len(verification),
        "warnings": _warning_text(history, comparisons, warnings),
        "bytes transferred": transfer,
        "source information": source,
    }
    transfer_entry = {
        "VCV accession": accession,
        "status": "retrieved" if records else "saved_without_retrieved_versions",
        "failure": str(attempt.get("failure") or ""),
        "reused": bool(attempt.get("reused", False)),
        "bytes_transferred": transfer,
        "history_response_bytes": transfer,
        "actual_new_batch_bytes": new_batch_transfer,
        "source_information": json.loads(source),
    }
    return (
        row,
        transfer_entry,
        _local_storage_bytes(history_root, accession),
        bool(records),
    )


def aggregate_pilot_results(
    history_root: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    """Aggregate at most ten attempted candidates without modifying source artifacts."""
    history_root = _path(history_root, "history_root")
    output_root = _path(output_root, "output_root")
    generated = _timestamp(generated_at_utc)
    rows: list[dict[str, object]] = []
    transfers: list[dict[str, object]] = []
    storage_bytes = 0
    successful = 0
    (
        attempts,
        selection_bytes,
        selection_requests,
        selection_request_count,
        has_batch,
    ) = _attempts(history_root, output_root)
    for attempt in attempts:
        row, transfer, local_bytes, retrieved = _row(history_root, attempt)
        rows.append(row)
        transfers.append(transfer)
        storage_bytes += local_bytes
        successful += int(retrieved)
    counts = Counter(str(row["detected change category"]) for row in rows)
    germline_count = sum(counts[label] for label in _GERMLINE_CHANGES)
    unable_count = counts["Missing_Data"] + counts["Unable_to_Compare"]
    history_response_bytes = sum(int(row["bytes transferred"]) for row in rows)
    actual_new_batch_bytes = (
        sum(int(item["actual_new_batch_bytes"]) for item in transfers)
        if has_batch
        else 0
    )
    summary = {
        "candidates_attempted": len(rows),
        "candidates_successfully_retrieved": successful,
        "total_official_versions_retrieved": sum(
            int(row["versions retrieved"]) for row in rows
        ),
        "variants_with_germline_change": germline_count,
        "variants_with_no_germline_change": counts["No_Germline_Change"],
        "variants_unable_to_compare": unable_count,
        "change_category_counts": dict(sorted(counts.items())),
        "candidate_selection_bytes": selection_bytes,
        "candidate_selection_request_count": selection_request_count,
        "history_response_bytes": history_response_bytes,
        "actual_new_batch_bytes": actual_new_batch_bytes,
        "total_bytes_transferred": selection_bytes + history_response_bytes,
        "total_local_storage_bytes": storage_bytes,
        "manually_verified": sum(
            row["manually reviewed status"] == "manually_verified" for row in rows
        ),
        "needs_review": sum(
            row["manually reviewed status"] == "needs_review" for row in rows
        ),
        "histories_needing_review": sum(
            row["manually reviewed status"] not in {"manually_verified", "excluded"}
            for row in rows
        ),
        "generated_at_utc": generated,
        "notice": NOTICE,
    }
    return {
        "rows": rows,
        "summary": summary,
        "transfer_manifest": {
            "generated_at_utc": generated,
            "notice": NOTICE,
            "candidates": transfers,
            "candidate_selection_bytes": selection_bytes,
            "candidate_selection_requests": selection_requests,
            "candidate_selection_request_count": selection_request_count,
            "history_response_bytes": history_response_bytes,
            "actual_new_batch_bytes": actual_new_batch_bytes,
            "total_bytes_transferred": summary["total_bytes_transferred"],
        },
    }


def _csv_bytes(fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _report(aggregation: Mapping[str, object]) -> bytes:
    rows = aggregation["rows"]
    summary = aggregation["summary"]
    assert isinstance(rows, list) and isinstance(summary, dict)
    examples = [
        f"- {row['VCV accession']}: {row['automatic result']} "
        f"({row['first aggregate germline classification'] or 'missing'} to "
        f"{row['newest aggregate germline classification'] or 'missing'})"
        for row in rows[:3]
    ] or ["- No candidates were attempted; no example was generated."]
    text = f"""# Real ClinVar History Pilot Report

> {NOTICE}

## Research question

Can official versioned ClinVar VCV records support a small, auditable assessment
of aggregate germline classification changes?

## Method

Up to ten attempted candidates were aggregated from bounded local VCV history
artifacts. Consecutive retrieved aggregate germline classifications were compared
without applying manual corrections; somatic clinical impact and oncogenicity were
not treated as germline outcomes.

## Official source

The records and transfer provenance come from official NCBI ClinVar E-utilities
requests retained in each history manifest.

## Sample size

Candidates attempted: {summary["candidates_attempted"]}.
Successfully retrieved: {summary["candidates_successfully_retrieved"]}.
Official versions retrieved: {summary["total_official_versions_retrieved"]}.

## Results

Germline change: {summary["variants_with_germline_change"]}.
No germline change: {summary["variants_with_no_germline_change"]}.
Unable to compare or missing data: {summary["variants_unable_to_compare"]}.
Manually verified: {summary["manually_verified"]}.
Needs review: {summary["needs_review"]}.

## Transfer accounting

Candidate selection requests: {summary["candidate_selection_request_count"]}.
Candidate selection response bytes: {summary["candidate_selection_bytes"]}.
Unique history response bytes: {summary["history_response_bytes"]}.
Actual bytes newly transferred in this batch: {summary["actual_new_batch_bytes"]}.
Total pilot response bytes represented: {summary["total_bytes_transferred"]}.
The total adds candidate selection responses once to each unique row's source-history
responses. New-batch bytes are shown separately and are not added again.

## Examples

{chr(10).join(examples)}

## Limitations

This is a small real-data pilot based on available official record versions, not
monthly snapshots. Missing versions, changed record structure, retrieval failures,
and unreviewed automatic classifications limit interpretation.
This pilot is not the final paper.

## Next step

Manually verify every pilot history against retained official sources, then expand
to approximately 25–50 suitable histories before deciding whether this method can
support model development.
"""
    return text.encode("utf-8")


def _manual_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "VCV accession": row["VCV accession"],
            "Variation ID": row["Variation ID"],
            "gene": row["gene"],
            "automatic result": row["automatic result"],
            "reviewer decision": row["reviewer decision"],
            "manual confirmed result": row["manual confirmed result"],
            "manually reviewed status": row["manually reviewed status"],
            "review notes": row["review notes"],
            "verification complete": row["verification complete"],
            "verification total": row["verification total"],
            "source information": row["source information"],
        }
        for row in rows
    ]


def _atomic_write(path: Path, content: bytes) -> None:
    if len(content) > MAX_EXPORT_BYTES:
        raise PilotResultsError(f"{path.name} exceeds its 4 MB export limit.")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise PilotResultsError(f"Refusing to replace unsafe output {path.name}.")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_pilot_results(
    history_root: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    """Aggregate and atomically write the five fixed pilot result files."""
    output_root = _path(output_root, "output_root")
    if output_root.is_symlink():
        raise PilotResultsError("The pilot output root cannot be a symbolic link.")
    output_root.mkdir(parents=True, exist_ok=True)
    aggregation = aggregate_pilot_results(
        history_root, output_root, generated_at_utc=generated_at_utc
    )
    rows = aggregation["rows"]
    assert isinstance(rows, list)
    payloads = {
        "pilot_results.csv": _csv_bytes(RESULT_FIELDS, rows),
        "pilot_summary.json": _json_bytes(aggregation["summary"]),
        "pilot_report.md": _report(aggregation),
        "transfer_manifest.json": _json_bytes(aggregation["transfer_manifest"]),
        "manual_review.csv": _csv_bytes(MANUAL_REVIEW_FIELDS, _manual_rows(rows)),
    }
    for filename in OUTPUT_FILENAMES:
        _atomic_write(output_root / filename, payloads[filename])
    return aggregation


def download_content(output_root: Path, filename: str) -> tuple[bytes, str, str]:
    """Return one generated fixed-name file as content, MIME type, and filename."""
    output_root = _path(output_root, "output_root")
    if filename not in OUTPUT_FILENAMES:
        raise PilotResultsError("Unknown pilot result download filename.")
    path = output_root / filename
    if path.is_symlink() or not path.is_file():
        raise PilotResultsError(f"Pilot result file is unavailable: {filename}.")
    if path.stat().st_size > MAX_EXPORT_BYTES:
        raise PilotResultsError(f"{filename} exceeds its 4 MB export limit.")
    mimetype = (
        "text/csv; charset=utf-8"
        if path.suffix == ".csv"
        else "application/json"
        if path.suffix == ".json"
        else "text/markdown; charset=utf-8"
    )
    return path.read_bytes(), mimetype, filename


# A concise orchestration alias for callers that treat generation as one operation.
generate_pilot_results = export_pilot_results
