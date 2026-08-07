"""Build lossless V9.1 dataset views without turning suggestions into reviews."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.v8_presentation import sha256_file
from variant_time_machine.v9_dataset import APPROVED_CLEAN_DECISIONS, SEVERE_FLAGS

OUTPUT_NAMES = (
    "v9_1_all_eligible_dataset.csv",
    "v9_1_clean_reviewed_dataset.csv",
    "v9_1_strict_clean_dataset.csv",
    "v9_1_ambiguous_dataset.csv",
    "v9_1_excluded_dataset.csv",
)
EXPLICIT_EXCLUSION_DECISIONS = {
    "bad_match",
    "exclude_non_germline_or_wrong_scope",
    "duplicate_or_related_record_problem",
    "missing_critical_fields",
}
AMBIGUOUS_DECISIONS = {
    "ambiguous_condition_scope",
    "ambiguous_aggregation",
    "possible_label_problem",
    "conflicting_classification_scope",
    "uncertain_manual_review",
    "needs_expert_review",
}


class V91DatasetError(ValueError):
    """Raised when a V9.1 dataset view would lose or silently alter a record."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V91DatasetError(f"Expected a JSON object: {path}")
    return value


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file() or path.is_symlink():
        raise V91DatasetError(f"Required source is unavailable: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not rows or not fields:
        raise V91DatasetError(f"Required source is empty: {path}")
    return fields, rows


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _flags(row: dict[str, str]) -> set[str]:
    try:
        values = json.loads(row["automatic_review_flags"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise V91DatasetError("Invalid automatic review flags.") from exc
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise V91DatasetError("Automatic review flags must be a list of strings.")
    return set(values)


def _class_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row["dataset_outcome"]) for row in rows))


def build_v9_1_datasets(project_root: Path) -> dict[str, Any]:
    """Create auditable V9.1 views while preserving immutable source labels."""
    root = project_root.resolve()
    source_dir = root / "data/processed/v9"
    source_path = source_dir / "v9_messy_dataset.csv"
    source_manifest_path = source_dir / "v9_dataset_manifest.json"
    queue_path = root / "outputs/manual_review/v8_review_queue.csv"
    notes_path = root / "outputs/manual_review/v8_review_notes.json"
    source_manifest = _load_json(source_manifest_path)
    fields, rows = _read_csv(source_path)
    _, queue_rows = _read_csv(queue_path)
    if source_manifest.get("output_hashes", {}).get(source_path.name) != sha256_file(
        source_path
    ):
        raise V91DatasetError("V9 source dataset hash does not match its manifest.")
    if len(rows) != 1000 or len({row["variation_id"] for row in rows}) != 1000:
        raise V91DatasetError("V9.1 source accounting changed from 1,000 unique rows.")
    if {row["variation_id"] for row in rows} != {
        row["variation_id"] for row in queue_rows
    }:
        raise V91DatasetError("V9.1 source and review queue membership differ.")
    queue_by_id = {row["variation_id"]: row for row in queue_rows}
    output_fields = [
        *fields,
        "v9_1_review_state",
        "v9_1_inclusion_reason",
        "v9_1_match_confidence",
        "v9_1_unresolved_severe_flags",
    ]
    all_rows: list[dict[str, Any]] = []
    clean_rows: list[dict[str, Any]] = []
    strict_rows: list[dict[str, Any]] = []
    ambiguous_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    for source in rows:
        row = dict(source)
        identifier = row["variation_id"]
        queue = queue_by_id[identifier]
        decision = row["manual_decision"]
        unresolved = sorted(_flags(row) & SEVERE_FLAGS)
        completed = decision != "not_reviewed"
        if decision in EXPLICIT_EXCLUSION_DECISIONS:
            state = "explicitly_excluded"
            reason = f"manual_decision:{decision}"
        elif decision in APPROVED_CLEAN_DECISIONS:
            state = "clean_reviewed"
            reason = f"completed_manual_acceptance:{decision}"
        elif decision in AMBIGUOUS_DECISIONS:
            state = "ambiguous_after_review"
            reason = f"manual_decision:{decision}"
        elif not completed:
            state = "review_pending"
            reason = "human_review_not_completed"
        else:
            state = "ambiguous_after_review"
            reason = f"manual_decision:{decision}"
        row.update(
            {
                "v9_1_review_state": state,
                "v9_1_inclusion_reason": reason,
                "v9_1_match_confidence": queue["match_confidence"],
                "v9_1_unresolved_severe_flags": json.dumps(unresolved),
            }
        )
        if (
            row["dataset_outcome"] != row["original_automatic_outcome"]
            and not completed
        ):
            raise V91DatasetError("A pending row silently changed its source label.")
        all_rows.append(row)
        state_counts[state] += 1
        if state == "explicitly_excluded":
            excluded_rows.append(row)
        elif state == "clean_reviewed":
            clean_rows.append(row)
            core_complete = all(
                float(row[name]) == 0
                for name in (
                    "feature__missing_gene",
                    "feature__missing_coordinate",
                    "feature__missing_phenotype_ids",
                    "feature__consequence_unrecognized",
                )
            )
            if (
                queue["match_confidence"] == "high under frozen temporal rule"
                and not unresolved
                and core_complete
            ):
                strict_rows.append(row)
        else:
            ambiguous_rows.append(row)
    if len(all_rows) != len(clean_rows) + len(ambiguous_rows) + len(excluded_rows):
        raise V91DatasetError("V9.1 review states do not preserve every source row.")

    output_dir = root / "data/processed/v9_1"
    outputs = {
        OUTPUT_NAMES[0]: all_rows,
        OUTPUT_NAMES[1]: clean_rows,
        OUTPUT_NAMES[2]: strict_rows,
        OUTPUT_NAMES[3]: ambiguous_rows,
        OUTPUT_NAMES[4]: excluded_rows,
    }
    for name, output_rows in outputs.items():
        _write_csv(output_dir / name, output_fields, output_rows)
    output_hashes = {name: sha256_file(output_dir / name) for name in OUTPUT_NAMES}
    manifest = {
        "schema_version": 1,
        "status": "internal_development_only_review_gate_failed",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_records": len(rows),
        "source_components": len({row["component_hash"] for row in rows}),
        "counts": {
            "all_eligible": len(all_rows),
            "clean_reviewed": len(clean_rows),
            "strict_clean": len(strict_rows),
            "ambiguous": len(ambiguous_rows),
            "excluded": len(excluded_rows),
        },
        "review_state_counts": dict(state_counts),
        "class_distributions": {
            "all_eligible": _class_counts(all_rows),
            "clean_reviewed": _class_counts(clean_rows),
            "strict_clean": _class_counts(strict_rows),
            "ambiguous": _class_counts(ambiguous_rows),
            "excluded": _class_counts(excluded_rows),
        },
        "feature_columns": source_manifest["feature_columns"],
        "feature_count": len(source_manifest["feature_columns"]),
        "core_feature_warnings": {
            "unrecognized_consequence": sum(
                float(row["feature__consequence_unrecognized"]) > 0 for row in rows
            ),
            "missing_gene": sum(
                float(row["feature__missing_gene"]) > 0 for row in rows
            ),
            "missing_coordinate": sum(
                float(row["feature__missing_coordinate"]) > 0 for row in rows
            ),
            "missing_phenotype_ids": sum(
                float(row["feature__missing_phenotype_ids"]) > 0 for row in rows
            ),
        },
        "manual_review_completed": sum(
            row["manual_decision"] != "not_reviewed" for row in rows
        ),
        "labels_corrected": sum(
            row["dataset_outcome"] != row["original_automatic_outcome"] for row in rows
        ),
        "training_eligible": True,
        "training_scope": "all-eligible opened-data internal validation only",
        "clean_evaluation_eligible": bool(clean_rows),
        "strict_evaluation_eligible": bool(strict_rows),
        "official_model_selection_allowed": False,
        "final_test_allowed": False,
        "source_hashes": {
            "v9_messy_dataset.csv": sha256_file(source_path),
            "v9_dataset_manifest.json": sha256_file(source_manifest_path),
            "v8_review_queue.csv": sha256_file(queue_path),
            "v8_review_notes.json": sha256_file(notes_path),
            "config/v9_1.json": sha256_file(root / "config/v9_1.json"),
        },
        "implementation_hashes": {
            "src/variant_time_machine/v9_1_dataset.py": sha256_file(
                root / "src/variant_time_machine/v9_1_dataset.py"
            ),
            "scripts/build_v9_1_datasets.py": sha256_file(
                root / "scripts/build_v9_1_datasets.py"
            ),
        },
        "output_hashes": output_hashes,
        "warnings": [
            "All 1,000 rows were previously opened during V8 analysis.",
            "No human reviews are complete, so clean and strict-clean claims are "
            "unavailable.",
            "Review-pending rows are ambiguous for clean-claim accounting, not "
            "scientific exclusions.",
            "AI-assisted suggestions did not become manual decisions or dataset "
            "labels.",
            "Filtered subset metrics must not be compared with V8 all-record metrics "
            "without a cohort warning.",
        ],
    }
    _write_json(output_dir / "v9_1_dataset_manifest.json", manifest)
    return manifest
