"""Small pilot dataset, conservative comparison, and manual review helpers."""

import csv
import hashlib
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.config import (
    PILOT_MAX_TEMP_BYTES,
    ClinVarXMLRelease,
)
from variant_time_machine.remote_archive import ExtractedVCVRecord, ExtractionResult

REVIEW_STATUSES = (
    "Not reviewed",
    "Confirmed match",
    "Needs follow-up",
    "Rejected automatic match",
)


def read_pilot_rows(path: Path) -> list[dict[str, str]]:
    """Read the small current-data pilot list."""
    with path.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    if not rows or "variation_id" not in rows[0]:
        raise ValueError("Pilot CSV must contain at least one variation_id row.")
    identifiers = [row["variation_id"].strip() for row in rows]
    if any(not identifier.isdigit() for identifier in identifiers):
        raise ValueError("Every pilot variation_id must be numeric.")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Pilot variation_id values must be unique.")
    return rows


def _record_map(
    records: Iterable[ExtractedVCVRecord],
) -> dict[str, ExtractedVCVRecord]:
    return {record.variation_id: record for record in records}


def compare_pilot_records(
    requested_ids: Iterable[str],
    older_records: Iterable[ExtractedVCVRecord],
    newer_records: Iterable[ExtractedVCVRecord],
    *,
    older_release_date: str,
    newer_release_date: str,
) -> list[dict[str, object]]:
    """Compare only exact Variation IDs and leave every result for human review."""
    older = _record_map(older_records)
    newer = _record_map(newer_records)
    comparisons: list[dict[str, object]] = []
    for variation_id in requested_ids:
        old = older.get(variation_id)
        new = newer.get(variation_id)
        if old and new:
            match_status = "exact_variation_id_match"
        elif not old and not new:
            match_status = "missing_in_both_releases"
        elif not old:
            match_status = "missing_in_older_release"
        else:
            match_status = "missing_in_newer_release"

        old_classification = old.germline_classification if old else None
        new_classification = new.germline_classification if new else None
        if match_status != "exact_variation_id_match":
            classification_change = "Unable_to_Verify"
        elif not old_classification or not new_classification:
            classification_change = "Unable_to_Verify"
        elif old_classification.casefold() == new_classification.casefold():
            classification_change = "No_Germline_Classification_Change"
        else:
            classification_change = "Germline_Classification_Changed"

        history_flags = []
        for label, record in (("older", old), ("newer", new)):
            if record and record.record_status not in (None, "current"):
                history_flags.append(f"{label}_status:{record.record_status}")
            if record and (record.replaced_by or record.replacement_list):
                history_flags.append(f"{label}_replacement_metadata_present")

        comparisons.append(
            {
                "variation_id": variation_id,
                "older_release_date": older_release_date,
                "newer_release_date": newer_release_date,
                "older_accession": old.accession if old else None,
                "newer_accession": new.accession if new else None,
                "older_record_status": old.record_status if old else None,
                "newer_record_status": new.record_status if new else None,
                "older_germline_classification": old_classification,
                "newer_germline_classification": new_classification,
                "older_somatic_clinical_impact": (
                    old.somatic_clinical_impact if old else None
                ),
                "newer_somatic_clinical_impact": (
                    new.somatic_clinical_impact if new else None
                ),
                "older_oncogenicity_classification": (
                    old.oncogenicity_classification if old else None
                ),
                "newer_oncogenicity_classification": (
                    new.oncogenicity_classification if new else None
                ),
                "match_status": match_status,
                "classification_change": classification_change,
                "record_history_flags": history_flags,
                "automatic_verification_status": "requires_manual_review",
            }
        )
    return comparisons


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json_atomic(
    path: Path,
    value: object,
    *,
    max_bytes: int = PILOT_MAX_TEMP_BYTES,
) -> int:
    """Write a bounded JSON file and remove its temporary file on any failure."""
    content = _json_bytes(value)
    if len(content) > max_bytes:
        raise ValueError(f"Output would exceed the {max_bytes:,}-byte limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(content)


def write_extraction_outputs(
    output_dir: Path,
    release: ClinVarXMLRelease,
    result: ExtractionResult,
    *,
    max_bytes: int = PILOT_MAX_TEMP_BYTES,
) -> tuple[Path, Path]:
    """Save only small extracted records and an audit manifest."""
    record_path = output_dir / f"{release.label}_records.json"
    record_payload = {
        "release": release.label,
        "release_date": release.release_date.isoformat(),
        "records": [record.to_dict() for record in result.records],
    }
    record_bytes = _json_bytes(record_payload)
    if len(record_bytes) > max_bytes:
        raise ValueError(f"Extracted records exceed the {max_bytes:,}-byte limit.")
    record_hash = hashlib.sha256(record_bytes).hexdigest()
    write_json_atomic(record_path, record_payload, max_bytes=max_bytes)

    manifest_path = output_dir / f"{release.label}_manifest.json"
    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "release_label": release.label,
        "release_date": release.release_date.isoformat(),
        "schema_version": release.schema_version,
        "source_url": release.source_url,
        "source_expected_compressed_size_bytes": release.compressed_size_bytes,
        "source_expected_md5": release.md5,
        "compressed_bytes_read": result.compressed_bytes_read,
        "completed_full_scan": result.completed_full_scan,
        "requested_ids": list(result.requested_ids),
        "found_ids": [record.variation_id for record in result.records],
        "missing_ids": list(result.missing_ids),
        "record_output": record_path.name,
        "record_output_bytes": len(record_bytes),
        "record_output_sha256": record_hash,
        "source_archive_retained": False,
        "scientific_verification": "Not manually verified",
    }
    write_json_atomic(manifest_path, manifest, max_bytes=max_bytes)
    return record_path, manifest_path


def load_extracted_records(path: Path) -> tuple[ExtractedVCVRecord, ...]:
    """Load records previously written by ``write_extraction_outputs``."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    return tuple(
        ExtractedVCVRecord(
            **{
                **row,
                "allele_ids": tuple(row.get("allele_ids", [])),
                "genes": tuple(row.get("genes", [])),
                "conditions": tuple(row.get("conditions", [])),
                "replaced_by": tuple(row.get("replaced_by", [])),
                "replacement_list": tuple(row.get("replacement_list", [])),
            }
        )
        for row in rows
        if isinstance(row, dict)
    )


def load_reviews(path: Path) -> dict[str, dict[str, str]]:
    """Load local human review decisions, returning an empty set if absent."""
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews", {}) if isinstance(payload, dict) else {}
    return reviews if isinstance(reviews, dict) else {}


def save_review(
    path: Path,
    variation_id: str,
    status: str,
    notes: str,
) -> dict[str, str]:
    """Persist one explicit human review decision."""
    if not variation_id.isdigit():
        raise ValueError("Variation ID must be numeric.")
    if status not in REVIEW_STATUSES:
        raise ValueError("Unknown manual review status.")
    clean_notes = notes.strip()
    if len(clean_notes) > 2000:
        raise ValueError("Review notes must be 2,000 characters or fewer.")
    reviews = load_reviews(path)
    review = {
        "status": status,
        "notes": clean_notes,
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    reviews[variation_id] = review
    write_json_atomic(path, {"version": 1, "reviews": reviews})
    return review


def comparison_payload(
    pilot_rows: list[dict[str, str]],
    comparisons: list[dict[str, object]],
    reviews: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Join current pilot facts, archive comparisons, and human review state."""
    current = {row["variation_id"]: row for row in pilot_rows}
    return [
        {
            **comparison,
            "current": current.get(str(comparison["variation_id"]), {}),
            "manual_review": reviews.get(
                str(comparison["variation_id"]),
                {"status": "Not reviewed", "notes": ""},
            ),
        }
        for comparison in comparisons
    ]
