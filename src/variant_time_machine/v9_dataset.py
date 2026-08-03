"""Build auditable V9 preparation datasets without training or altering V8."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.ai_temporal_v8 import V8_FEATURE_NAMES
from variant_time_machine.v8_presentation import (
    DECISIONS,
    ERROR_CATEGORIES,
    FROZEN_SOURCE_HASHES,
    NOTE_REQUIRED,
    REVIEWER_CONFIDENCES,
    load_review_notes,
    sha256_file,
)

MESSY_FILENAME = "v9_messy_dataset.csv"
CLEAN_FILENAME = "v9_clean_reviewed_dataset.csv"
EXCLUDED_FILENAME = "v9_excluded_records.csv"
EXPERT_FILENAME = "v9_needs_expert_review.csv"
MANIFEST_FILENAME = "v9_dataset_manifest.json"
PARTITION_FILENAME = "v9_partition_manifest.csv"
CHERRY_PICKING_WARNING = (
    "Clean-dataset performance is not directly comparable to messy all-record "
    "performance if many hard or ambiguous records were excluded."
)
EXPECTED_V8_QUEUE_SHA256 = (
    "f5c3f57c3ac39cd5b3bf5b4be8405b8c8130dd62dc04ed32c9ce1174135e5a42"
)
APPROVED_CLEAN_DECISIONS = {
    "match_correct_model_wrong",
    "match_correct_model_right",
}
SEVERE_FLAGS = {
    "gene_missing",
    "coordinates_missing",
    "match_confidence_below_high",
    "classification_contains_conflicting",
    "possible_non_germline_scope",
    "consequence_missing_or_unrecognized",
}
FORBIDDEN_FEATURE_TERMS = {
    "new_",
    "later",
    "actual",
    "outcome",
    "correct",
    "prediction",
    "manual",
    "answer",
}


class V9DatasetError(ValueError):
    """Raised when V9 dataset preparation violates a frozen rule."""


def grouped_split_assignments(
    rows: list[dict[str, Any]], *, seed: str, validation_fraction: float = 0.2
) -> dict[str, str]:
    """Assign whole connected components without consulting outcomes."""
    if not 0 < validation_fraction < 1:
        raise V9DatasetError("Validation fraction must be between zero and one.")
    assignments: dict[str, str] = {}
    component_partitions: dict[str, str] = {}
    for row in rows:
        identifier = str(row.get("variation_id", ""))
        component = str(row.get("component_hash", ""))
        if not identifier or not component:
            raise V9DatasetError("Grouped splitting requires IDs and component hashes.")
        value = int(
            hashlib.sha256(f"{seed}:{component}".encode()).hexdigest()[:16], 16
        ) / float(16**16)
        partition = "validation" if value < validation_fraction else "train"
        previous = component_partitions.setdefault(component, partition)
        if previous != partition:
            raise V9DatasetError("A connected component crossed grouped partitions.")
        assignments[identifier] = partition
    return assignments


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise V9DatasetError(f"Required V9 source is unavailable: {path}")
    with path.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    if not rows:
        raise V9DatasetError(f"Required V9 source is empty: {path}")
    return rows


def _json_field(row: dict[str, str], name: str, expected: type) -> Any:
    try:
        value = json.loads(row.get(name, ""))
    except json.JSONDecodeError as exc:
        raise V9DatasetError(f"Queue field {name} is invalid JSON.") from exc
    if not isinstance(value, expected):
        raise V9DatasetError(f"Queue field {name} has the wrong JSON type.")
    return value


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _git_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not available"


def _git_dirty(root: Path, paths: list[str] | None = None) -> bool | str:
    command = ["git", "status", "--porcelain"]
    if paths:
        command.extend(["--", *paths])
    try:
        return bool(
            subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except OSError:
        return "not available"


def _source_name(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


def _reviewed(review: dict[str, Any]) -> bool:
    return review.get("manual_decision") not in {None, "", "not_reviewed"}


def _validate_review_record(
    identifier: str, review: dict[str, Any], row: dict[str, str]
) -> None:
    required = {
        "review_id",
        "reviewed_at",
        "reviewer",
        "model_version",
        "variation_id",
        "vcv_accession",
        "allele_id",
        "gene",
        "old_snapshot_date",
        "new_snapshot_date",
        "old_classification_text",
        "new_classification_text",
        "normalized_old_outcome",
        "normalized_new_outcome",
        "v8_prediction",
        "v8_probability",
        "v8_confidence",
        "v8_correctness",
        "v7_prediction",
        "match_method",
        "match_confidence",
        "old_condition_text",
        "new_condition_text",
        "old_review_status",
        "new_review_status",
        "old_consequence_fields",
        "feature_values_used_by_v8",
        "official_source_links",
        "automatic_warning_flags",
        "cleared_automatic_flags",
        "manual_decision",
        "manual_error_category",
        "exclude_from_v9_clean_dataset",
        "include_in_v9_messy_dataset",
        "include_in_v9_clean_dataset",
        "label_correction",
        "corrected_outcome",
        "note",
        "reviewer_confidence",
        "revision",
    }
    missing = sorted(required - set(review))
    if missing:
        raise V9DatasetError(
            f"Review {identifier} is missing schema fields: {', '.join(missing)}"
        )
    if review["variation_id"] != identifier or review["model_version"] != "V8":
        raise V9DatasetError(f"Review {identifier} does not match its V8 queue row.")
    if (
        review["review_id"] != f"V8:{identifier}"
        or not isinstance(review["revision"], int)
        or review["revision"] < 1
    ):
        raise V9DatasetError(f"Review {identifier} has invalid identity or revision.")
    immutable_checks = {
        "vcv_accession": row["vcv_accession"],
        "allele_id": row["allele_id"],
        "gene": row["gene"],
        "old_snapshot_date": row["old_snapshot_date"],
        "new_snapshot_date": row["new_snapshot_date"],
        "old_classification_text": row["old_classification_text"],
        "new_classification_text": row["new_classification_text"],
        "normalized_old_outcome": row["normalized_old_outcome"],
        "normalized_new_outcome": row["normalized_new_outcome"],
        "v8_prediction": row["predicted_class"],
        "v8_correctness": row["correct"] == "true",
        "v7_prediction": row["v7_prediction"],
        "match_method": row["match_method"],
        "match_confidence": row["match_confidence"],
        "old_condition_text": row["old_condition_text"],
        "new_condition_text": row["new_condition_text"],
        "old_review_status": row["old_review_status"],
        "new_review_status": row["new_review_status"],
    }
    if any(review.get(key) != value for key, value in immutable_checks.items()):
        raise V9DatasetError(
            f"Review {identifier} changed an immutable original value."
        )
    if float(review["v8_probability"]) != float(row["v8_probability"]):
        raise V9DatasetError(f"Review {identifier} changed the frozen V8 probability.")
    if float(review["v8_confidence"]) != float(row["confidence"]):
        raise V9DatasetError(f"Review {identifier} changed the frozen V8 confidence.")
    if (
        review["automatic_warning_flags"]
        != _json_field(row, "automatic_review_flags", list)
        or review["feature_values_used_by_v8"]
        != _json_field(row, "feature_values_used_by_v8", dict)
        or review["old_consequence_fields"]
        != _json_field(row, "old_consequence_fields", dict)
        or review["official_source_links"]
        != _json_field(row, "official_source_links", list)
    ):
        raise V9DatasetError(f"Review {identifier} changed immutable evidence fields.")
    decision = review["manual_decision"]
    if decision not in DECISIONS:
        raise V9DatasetError(f"Review {identifier} has an unknown manual decision.")
    if review["manual_error_category"] not in ERROR_CATEGORIES:
        raise V9DatasetError(f"Review {identifier} has an unknown error category.")
    if decision != "not_reviewed" and (
        not str(review["reviewer"]).strip()
        or review["reviewer_confidence"] not in REVIEWER_CONFIDENCES
        or not str(review["reviewed_at"]).strip()
    ):
        raise V9DatasetError(f"Review {identifier} is not a completed valid review.")
    for field in (
        "exclude_from_v9_clean_dataset",
        "include_in_v9_messy_dataset",
        "include_in_v9_clean_dataset",
        "label_correction",
    ):
        if not isinstance(review[field], bool):
            raise V9DatasetError(f"Review {identifier} has a non-boolean {field}.")
    if (
        review["exclude_from_v9_clean_dataset"]
        and review["include_in_v9_clean_dataset"]
    ):
        raise V9DatasetError(f"Review {identifier} has conflicting clean flags.")
    corrected = review["corrected_outcome"]
    if corrected not in {None, "moved_toward_benign", "moved_toward_pathogenic"}:
        raise V9DatasetError(f"Review {identifier} has an invalid corrected outcome.")
    if bool(corrected) != review["label_correction"]:
        raise V9DatasetError(f"Review {identifier} has inconsistent correction fields.")
    note = review["note"]
    if not isinstance(note, str) or len(note) > 5000:
        raise V9DatasetError(f"Review {identifier} has an invalid note.")
    if (
        decision in NOTE_REQUIRED
        or corrected
        or review["exclude_from_v9_clean_dataset"]
        or review.get("cleared_automatic_flags")
    ) and not note.strip():
        raise V9DatasetError(f"Review {identifier} requires a note.")
    if decision == "not_reviewed" and corrected:
        raise V9DatasetError(f"Unreviewed record {identifier} cannot correct a label.")
    cleared = review.get("cleared_automatic_flags", [])
    if not isinstance(cleared, list) or any(
        not isinstance(flag, str) for flag in cleared
    ):
        raise V9DatasetError(f"Review {identifier} has invalid cleared flags.")
    recorded_flags = set(_json_field(row, "automatic_review_flags", list))
    if not set(cleared) <= recorded_flags:
        raise V9DatasetError(f"Review {identifier} clears an unrecorded flag.")


def _clean_exclusion_reasons(
    row: dict[str, str], review: dict[str, Any], flags: list[str]
) -> list[str]:
    if not _reviewed(review):
        return ["manual_review_pending"]
    reasons: list[str] = []
    decision = review.get("manual_decision")
    if decision == "needs_expert_review":
        reasons.append("needs_expert_review")
    if review.get("exclude_from_v9_clean_dataset"):
        reasons.append(f"manual_exclusion:{decision}")
    if decision not in APPROVED_CLEAN_DECISIONS:
        reasons.append(f"manual_decision_not_clean_approved:{decision}")
    if not review.get("include_in_v9_clean_dataset"):
        reasons.append("manual_clean_inclusion_not_approved")
    cleared = set(review.get("cleared_automatic_flags", []))
    severe = sorted((set(flags) & SEVERE_FLAGS) - cleared)
    reasons.extend(f"unresolved_severe_flag:{flag}" for flag in severe)
    if row.get("normalized_old_outcome") != "uncertain":
        reasons.append("old_record_not_strict_vus")
    if row.get("normalized_new_outcome") not in {
        "moved_toward_benign",
        "moved_toward_pathogenic",
    }:
        reasons.append("later_outcome_not_directional")
    return sorted(set(reasons))


def _minimum_review_gate(
    rows: list[dict[str, str]], reviews: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    def done(row: dict[str, str]) -> bool:
        return _reviewed(reviews.get(row["variation_id"], {}))

    fn_rows = [row for row in rows if row["confusion_group"] == "FN"]
    high_fp = [
        row
        for row in rows
        if row["confusion_group"] == "FP" and row["high_confidence"] == "true"
    ]
    tn_reviewed = sum(row["confusion_group"] == "TN" and done(row) for row in rows)
    tp_reviewed = sum(row["confusion_group"] == "TP" and done(row) for row in rows)
    disagreements = [row for row in rows if row["v8_v7_disagreement"] == "true"]
    checks = {
        "all_false_negatives_reviewed": all(done(row) for row in fn_rows),
        "all_high_confidence_false_positives_reviewed": all(
            done(row) for row in high_fp
        ),
        "at_least_25_true_negatives_reviewed": tn_reviewed >= 25,
        "at_least_25_true_positives_reviewed": tp_reviewed >= 25,
        "all_v8_v7_disagreements_reviewed": all(done(row) for row in disagreements),
        "exclusion_reason_counts_reported": True,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "false_negatives": len(fn_rows),
            "high_confidence_false_positives": len(high_fp),
            "true_negatives_reviewed": tn_reviewed,
            "true_positives_reviewed": tp_reviewed,
            "v8_v7_disagreements": len(disagreements),
        },
    }


def build_v9_datasets(
    project_root: Path,
    *,
    queue_path: Path | None = None,
    queue_manifest_path: Path | None = None,
    notes_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Build messy, clean, excluded, and expert-needed V9 preparation tables."""
    root = project_root.resolve()
    queue_path = queue_path or root / "outputs/manual_review/v8_review_queue.csv"
    queue_manifest_path = queue_manifest_path or (
        root / "outputs/manual_review/v8_review_queue_manifest.json"
    )
    notes_path = notes_path or root / "outputs/manual_review/v8_review_notes.json"
    output_dir = output_dir or root / "data/processed/v9"
    frozen_predictions = root / "outputs/ai_temporal_v8/temporal_test_predictions.csv"
    if (
        sha256_file(frozen_predictions)
        != FROZEN_SOURCE_HASHES["outputs/ai_temporal_v8/temporal_test_predictions.csv"]
    ):
        raise V9DatasetError("Frozen V8 predictions changed; refusing V9 preparation.")

    queue_rows = _read_csv(queue_path)
    queue_hash = sha256_file(queue_path)
    if queue_hash != EXPECTED_V8_QUEUE_SHA256:
        raise V9DatasetError("V8 review queue hash changed; refusing V9 preparation.")
    try:
        queue_manifest = json.loads(queue_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V9DatasetError(
            "V8 review queue manifest is unavailable or invalid."
        ) from exc
    if (
        not isinstance(queue_manifest, dict)
        or queue_manifest.get("queue_sha256") != queue_hash
        or queue_manifest.get("source_predictions_sha256")
        != FROZEN_SOURCE_HASHES["outputs/ai_temporal_v8/temporal_test_predictions.csv"]
    ):
        raise V9DatasetError(
            "V8 review queue manifest does not authenticate the queue."
        )
    if len(queue_rows) != 1000 or len(
        {row["variation_id"] for row in queue_rows}
    ) != len(queue_rows):
        raise V9DatasetError("V9 preparation requires 1,000 unique V8 queue rows.")
    if sum(row["correct"] == "false" for row in queue_rows) != 105:
        raise V9DatasetError("V8 queue no longer contains exactly 105 wrong records.")
    prediction_rows = _read_csv(frozen_predictions)
    predictions = {row["variation_id"]: row for row in prediction_rows}
    if set(predictions) != {row["variation_id"] for row in queue_rows}:
        raise V9DatasetError("V8 queue IDs do not match frozen V8 test IDs.")
    for row in queue_rows:
        source = predictions[row["variation_id"]]
        expected_values = {
            "gene": source["gene_symbols"],
            "component_hash": source["component_hash"],
            "normalized_new_outcome": source["actual_outcome"],
            "predicted_class": f"moved_toward_{source['v8_prediction']}",
            "v7_prediction": f"moved_toward_{source['v7_prediction']}",
            "new_classification_text": source["answer_classification"],
        }
        if any(row.get(key) != value for key, value in expected_values.items()):
            raise V9DatasetError(
                "V8 queue changed frozen identity, label, or prediction fields."
            )
        if float(row["v8_probability"]) != float(source["v8_probability"]):
            raise V9DatasetError("V8 queue changed a frozen model probability.")
    review_payload = load_review_notes(notes_path)
    raw_reviews = review_payload.get("reviews", {})
    if not isinstance(raw_reviews, dict):
        raise V9DatasetError("V8 review store has an invalid reviews object.")
    queue_by_id = {row["variation_id"]: row for row in queue_rows}
    reviews: dict[str, dict[str, Any]] = {}
    for key, value in raw_reviews.items():
        identifier = str(key)
        if identifier not in queue_by_id:
            raise V9DatasetError(f"Review store contains orphaned ID {identifier}.")
        if not isinstance(value, dict):
            raise V9DatasetError(f"Review {identifier} must be a JSON object.")
        _validate_review_record(identifier, value, queue_by_id[identifier])
        reviews[identifier] = value

    feature_names = sorted(
        {
            name
            for row in queue_rows
            for name in _json_field(row, "feature_values_used_by_v8", dict)
        }
    )
    if set(feature_names) != set(V8_FEATURE_NAMES):
        raise V9DatasetError(
            "V8 queue feature schema changed or contains extra fields."
        )
    unsafe_features = [
        name
        for name in feature_names
        if any(term in name.casefold() for term in FORBIDDEN_FEATURE_TERMS)
    ]
    if unsafe_features:
        raise V9DatasetError(
            "V9 feature leakage audit failed: " + ", ".join(unsafe_features)
        )

    base_fields = [
        "variation_id",
        "gene",
        "component_hash",
        "original_automatic_outcome",
        "dataset_outcome",
        "label_source",
        "v8_prediction",
        "v8_probability",
        "v8_correct",
        "confusion_group",
        "manual_decision",
        "manual_error_category",
        "automatic_review_flags",
    ]
    fields = [*base_fields, *(f"feature__{name}" for name in feature_names)]
    messy: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    expert: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()

    for row in queue_rows:
        identifier = row["variation_id"]
        review = reviews.get(identifier, {})
        flags = _json_field(row, "automatic_review_flags", list)
        feature_values = _json_field(row, "feature_values_used_by_v8", dict)
        original_outcome = row["normalized_new_outcome"]
        corrected = review.get("corrected_outcome")
        dataset_outcome = corrected or original_outcome
        record: dict[str, Any] = {
            "variation_id": identifier,
            "gene": row["gene"],
            "component_hash": row["component_hash"],
            "original_automatic_outcome": original_outcome,
            "dataset_outcome": dataset_outcome,
            "label_source": "manual_correction" if corrected else "original_automatic",
            "v8_prediction": row["predicted_class"],
            "v8_probability": row["v8_probability"],
            "v8_correct": row["correct"],
            "confusion_group": row["confusion_group"],
            "manual_decision": review.get("manual_decision", "not_reviewed"),
            "manual_error_category": review.get("manual_error_category", "unknown"),
            "automatic_review_flags": json.dumps(flags, separators=(",", ":")),
            **{
                f"feature__{name}": feature_values.get(name, 0.0)
                for name in feature_names
            },
        }
        messy.append({**record, "dataset_outcome": original_outcome})
        reasons = _clean_exclusion_reasons(row, review, flags)
        if not reasons:
            clean.append(record)
        else:
            exclusion_counts.update(reasons)
            excluded.append(
                {
                    "variation_id": identifier,
                    "gene": row["gene"],
                    "confusion_group": row["confusion_group"],
                    "manual_decision": review.get("manual_decision", "not_reviewed"),
                    "exclusion_reasons": ";".join(reasons),
                    "original_automatic_outcome": original_outcome,
                    "corrected_outcome": corrected or "",
                    "note": review.get("note", ""),
                }
            )
        if review.get("manual_decision") == "needs_expert_review":
            expert.append(excluded[-1])

    output_dir.mkdir(parents=True, exist_ok=True)
    messy_path = output_dir / MESSY_FILENAME
    clean_path = output_dir / CLEAN_FILENAME
    excluded_path = output_dir / EXCLUDED_FILENAME
    expert_path = output_dir / EXPERT_FILENAME
    manifest_path = output_dir / MANIFEST_FILENAME
    partition_path = output_dir / PARTITION_FILENAME
    _write_csv(messy_path, fields, messy)
    _write_csv(clean_path, fields, clean)
    exclusion_fields = [
        "variation_id",
        "gene",
        "confusion_group",
        "manual_decision",
        "exclusion_reasons",
        "original_automatic_outcome",
        "corrected_outcome",
        "note",
    ]
    _write_csv(excluded_path, exclusion_fields, excluded)
    _write_csv(expert_path, exclusion_fields, expert)

    gate = _minimum_review_gate(queue_rows, reviews)
    split_assignments = (
        grouped_split_assignments(clean, seed="v9-clean-grouped-split-v1")
        if clean
        else {}
    )
    split_counts = dict(Counter(split_assignments.values()))
    partition_rows = [
        {
            "variation_id": row["variation_id"],
            "component_hash": row["component_hash"],
            "partition": split_assignments[row["variation_id"]],
        }
        for row in clean
    ]
    _write_csv(
        partition_path,
        ["variation_id", "component_hash", "partition"],
        partition_rows,
    )
    train_components = {
        row["component_hash"] for row in partition_rows if row["partition"] == "train"
    }
    validation_components = {
        row["component_hash"]
        for row in partition_rows
        if row["partition"] == "validation"
    }
    dataset_freeze_checks = {
        "queue_hash_authenticated": True,
        "frozen_prediction_hash_authenticated": True,
        "unique_variation_ids": True,
        "exact_v8_feature_schema": True,
        "feature_name_leakage_audit_passed": True,
        "grouped_component_split_has_zero_overlap": not (
            train_components & validation_components
        ),
        "grouped_split_has_train_and_validation": set(split_counts)
        == {"train", "validation"},
        "schema_and_rules_hashed": True,
        "clean_dataset_large_enough_for_candidate_training": len(clean) >= 100,
    }
    explicitly_excluded_errors = sum(
        row["confusion_group"] in {"FP", "FN"}
        and bool(
            reviews.get(row["variation_id"], {}).get("exclude_from_v9_clean_dataset")
        )
        for row in queue_rows
    )
    training_eligible = gate["passed"] and all(dataset_freeze_checks.values())
    manifest = {
        "schema_version": 1,
        "status": "ready_for_candidate_training"
        if training_eligible
        else "preparation_only",
        "headline": (
            "V9 dataset preparation complete; final V9 model not yet valid."
            if not gate["passed"]
            else "Manual-review minimum met; candidate training may be planned."
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "source_datasets": [
            "outputs/ai_temporal_v8/temporal_test_predictions.csv",
            "outputs/manual_review/v8_review_queue.csv",
        ],
        "source_model_version": "V8",
        "review_file_hashes": {
            _source_name(queue_path, root): sha256_file(queue_path),
            _source_name(notes_path, root): sha256_file(notes_path),
        },
        "number_records_considered": len(queue_rows),
        "number_included_messy": len(messy),
        "number_included_clean": len(clean),
        "number_excluded": len(excluded),
        "exclusion_categories": dict(sorted(exclusion_counts.items())),
        "number_corrected": sum(
            bool(reviews.get(row["variation_id"], {}).get("corrected_outcome"))
            for row in queue_rows
        ),
        "number_needing_expert_review": len(expert),
        "feature_columns": [f"feature__{name}" for name in feature_names],
        "target_columns": [
            "original_automatic_outcome",
            "dataset_outcome",
            "label_source",
        ],
        "leakage_audit_status": "pass",
        "leakage_audit_scope": (
            "Only predictor-time V8 feature columns are eligible model inputs. Review, "
            "prediction, correctness, and later-outcome fields remain audit columns."
        ),
        "class_distribution_before": dict(
            Counter(row["normalized_new_outcome"] for row in queue_rows)
        ),
        "class_distribution_after_cleaning": dict(
            Counter(row["dataset_outcome"] for row in clean)
        ),
        "false_positives_outside_clean": sum(
            row["confusion_group"] == "FP" for row in excluded
        ),
        "false_negatives_outside_clean": sum(
            row["confusion_group"] == "FN" for row in excluded
        ),
        "false_positives_explicitly_excluded": sum(
            row["confusion_group"] == "FP"
            and bool(
                reviews.get(row["variation_id"], {}).get(
                    "exclude_from_v9_clean_dataset"
                )
            )
            for row in queue_rows
        ),
        "false_negatives_explicitly_excluded": sum(
            row["confusion_group"] == "FN"
            and bool(
                reviews.get(row["variation_id"], {}).get(
                    "exclude_from_v9_clean_dataset"
                )
            )
            for row in queue_rows
        ),
        "explicitly_excluded_v8_errors": explicitly_excluded_errors,
        "manual_review_minimum": gate,
        "dataset_freeze_checks": dataset_freeze_checks,
        "clean_component_count": len({row["component_hash"] for row in clean}),
        "grouped_partition_counts": split_counts,
        "training_eligible": training_eligible,
        "final_test_allowed": False,
        "warnings": [
            CHERRY_PICKING_WARNING,
            "Pending manual review is reported separately from scientific exclusion.",
            (
                "Reviewer messy-inclusion flags never remove rows from the all-record "
                "audit table."
            ),
            "V8 records are previously opened and cannot become a new hidden V9 test.",
            "No final V9 model was trained or evaluated by this dataset build.",
        ],
        "git_commit": _git_commit(root),
        "git_working_tree_dirty": _git_dirty(root),
        "v9_source_files_dirty": _git_dirty(
            root,
            [
                "src/variant_time_machine/v9_dataset.py",
                "src/variant_time_machine/v8_presentation.py",
                "config/manual_review_schema.yaml",
                "docs/v9-inclusion-rules.md",
                "research/v9-model-selection-plan.md",
            ],
        ),
        "implementation_hashes": {
            "src/variant_time_machine/v9_dataset.py": sha256_file(
                root / "src/variant_time_machine/v9_dataset.py"
            ),
            "config/manual_review_schema.yaml": sha256_file(
                root / "config/manual_review_schema.yaml"
            ),
            "docs/v9-inclusion-rules.md": sha256_file(
                root / "docs/v9-inclusion-rules.md"
            ),
            "research/v9-model-selection-plan.md": sha256_file(
                root / "research/v9-model-selection-plan.md"
            ),
        },
    }
    _write_json(manifest_path, manifest)
    manifest["output_hashes"] = {
        path.name: sha256_file(path)
        for path in (messy_path, clean_path, excluded_path, expert_path, partition_path)
    }
    _write_json(manifest_path, manifest)
    return manifest


def assert_final_v9_allowed(manifest: dict[str, Any], selection_plan: Path) -> None:
    """Refuse final V9 testing before both review and plan gates are satisfied."""
    if not selection_plan.is_file():
        raise V9DatasetError("Frozen V9 model-selection plan is missing.")
    if not manifest.get("training_eligible"):
        raise V9DatasetError("Manual-review minimum is not met; final V9 is invalid.")
    if not manifest.get("final_test_allowed"):
        raise V9DatasetError("Final V9 test remains locked by the dataset manifest.")
