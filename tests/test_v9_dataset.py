"""Tests for review-driven V9 dataset preparation and final-test guardrails."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from variant_time_machine.v9_dataset import (
    CHERRY_PICKING_WARNING,
    V9DatasetError,
    assert_final_v9_allowed,
    build_v9_datasets,
    grouped_split_assignments,
)

ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as input_file:
        return list(csv.DictReader(input_file))


def _review(row: dict[str, str], **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "review_id": f"V8:{row['variation_id']}",
        "reviewed_at": "2026-08-02T12:00:00+00:00",
        "manual_decision": "match_correct_model_wrong",
        "manual_error_category": "genuine_model_error",
        "exclude_from_v9_clean_dataset": False,
        "include_in_v9_messy_dataset": True,
        "include_in_v9_clean_dataset": True,
        "corrected_outcome": None,
        "label_correction": False,
        "cleared_automatic_flags": [],
        "note": "Reviewed fixture.",
        "reviewer": "fixture-reviewer",
        "reviewer_confidence": "high",
        "variation_id": row["variation_id"],
        "model_version": "V8",
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
        "v8_probability": float(row["v8_probability"]),
        "v8_confidence": float(row["confidence"]),
        "v8_correctness": row["correct"] == "true",
        "v7_prediction": row["v7_prediction"],
        "match_method": row["match_method"],
        "match_confidence": row["match_confidence"],
        "old_condition_text": row["old_condition_text"],
        "new_condition_text": row["new_condition_text"],
        "old_review_status": row["old_review_status"],
        "new_review_status": row["new_review_status"],
        "old_consequence_fields": json.loads(row["old_consequence_fields"]),
        "feature_values_used_by_v8": json.loads(row["feature_values_used_by_v8"]),
        "official_source_links": json.loads(row["official_source_links"]),
        "automatic_warning_flags": json.loads(row["automatic_review_flags"]),
        "revision": 1,
    }
    value.update(updates)
    return value


def test_current_v9_build_preserves_all_original_labels_and_stays_locked(
    tmp_path: Path,
) -> None:
    manifest = build_v9_datasets(ROOT, output_dir=tmp_path)
    assert manifest["number_records_considered"] == 1000
    assert manifest["number_included_messy"] == 1000
    assert manifest["number_included_clean"] == 0
    assert manifest["number_excluded"] == 1000
    assert manifest["exclusion_categories"] == {"manual_review_pending": 1000}
    assert manifest["training_eligible"] is False
    assert manifest["final_test_allowed"] is False
    assert manifest["status"] == "preparation_only"
    assert (
        manifest["dataset_freeze_checks"]["grouped_split_has_train_and_validation"]
        is False
    )
    assert (tmp_path / "v9_partition_manifest.csv").is_file()
    assert CHERRY_PICKING_WARNING in manifest["warnings"]
    messy = _rows(tmp_path / "v9_messy_dataset.csv")
    assert all(
        row["dataset_outcome"] == row["original_automatic_outcome"] for row in messy
    )


def test_reviewed_clean_correction_stays_separate_and_exclusions_are_reported(
    tmp_path: Path,
) -> None:
    queue = _rows(ROOT / "outputs/manual_review/v8_review_queue.csv")
    severe = {
        "gene_missing",
        "coordinates_missing",
        "match_confidence_below_high",
        "classification_contains_conflicting",
        "possible_non_germline_scope",
        "consequence_missing_or_unrecognized",
    }
    clean_row = next(
        row
        for row in queue
        if not (set(json.loads(row["automatic_review_flags"])) & severe)
    )
    excluded_row = next(row for row in queue if row is not clean_row)
    corrected = (
        "moved_toward_pathogenic"
        if clean_row["normalized_new_outcome"] == "moved_toward_benign"
        else "moved_toward_benign"
    )
    notes = tmp_path / "reviews.json"
    notes.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "reviews": {
                    clean_row["variation_id"]: _review(
                        clean_row, corrected_outcome=corrected, label_correction=True
                    ),
                    excluded_row["variation_id"]: _review(
                        excluded_row,
                        manual_decision="bad_match",
                        manual_error_category="poor_match",
                        exclude_from_v9_clean_dataset=True,
                        include_in_v9_clean_dataset=False,
                        include_in_v9_messy_dataset=False,
                        note="Identity does not support the automatic match.",
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "built"
    manifest = build_v9_datasets(ROOT, notes_path=notes, output_dir=output)
    clean = _rows(output / "v9_clean_reviewed_dataset.csv")
    assert len(_rows(output / "v9_messy_dataset.csv")) == 1000
    assert len(clean) == 1
    assert clean[0]["original_automatic_outcome"] == clean_row["normalized_new_outcome"]
    assert clean[0]["dataset_outcome"] == corrected
    assert clean[0]["label_source"] == "manual_correction"
    excluded = _rows(output / "v9_excluded_records.csv")
    saved_exclusion = next(
        row for row in excluded if row["variation_id"] == excluded_row["variation_id"]
    )
    assert "manual_exclusion:bad_match" in saved_exclusion["exclusion_reasons"]
    assert manifest["number_corrected"] == 1


def test_builder_rejects_tampered_queue_and_schema_invalid_reviews(
    tmp_path: Path,
) -> None:
    queue = tmp_path / "queue.csv"
    shutil.copyfile(ROOT / "outputs/manual_review/v8_review_queue.csv", queue)
    queue.write_bytes(
        queue.read_bytes().replace(b"moved_toward_benign", b"future_label", 1)
    )
    with pytest.raises(V9DatasetError, match="queue hash changed"):
        build_v9_datasets(ROOT, queue_path=queue, output_dir=tmp_path / "tampered")

    first = _rows(ROOT / "outputs/manual_review/v8_review_queue.csv")[0]
    invalid_notes = tmp_path / "invalid-reviews.json"
    invalid_notes.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "reviews": {
                    first["variation_id"]: {
                        "manual_decision": "match_correct_model_wrong"
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(V9DatasetError, match="missing schema fields"):
        build_v9_datasets(
            ROOT, notes_path=invalid_notes, output_dir=tmp_path / "invalid"
        )


def test_grouped_split_never_separates_a_component() -> None:
    rows = [
        {"variation_id": "1", "component_hash": "A"},
        {"variation_id": "2", "component_hash": "A"},
        {"variation_id": "3", "component_hash": "B"},
    ]
    assignments = grouped_split_assignments(rows, seed="frozen-v9-test")
    assert assignments["1"] == assignments["2"]
    assert assignments == grouped_split_assignments(
        list(reversed(rows)), seed="frozen-v9-test"
    )


def test_final_test_guard_rejects_unreviewed_manifest() -> None:
    manifest = {"training_eligible": False, "final_test_allowed": False}
    with pytest.raises(V9DatasetError, match="Manual-review minimum"):
        assert_final_v9_allowed(manifest, ROOT / "research/v9-model-selection-plan.md")


def test_schema_plan_and_partial_report_are_frozen_before_any_final_test() -> None:
    schema = (ROOT / "config/manual_review_schema.yaml").read_text(encoding="utf-8")
    for value in (
        "match_correct_model_wrong",
        "needs_expert_review",
        "genuine_model_error",
        "reviewer_confidence_options",
    ):
        assert value in schema
    plan = (ROOT / "research/v9-model-selection-plan.md").read_text(encoding="utf-8")
    report = (ROOT / "research/v9-clean-dataset-and-model-report.md").read_text(
        encoding="utf-8"
    )
    assert "Frozen planning document" in plan
    assert "No candidate has been trained" in report
    assert "V9 dataset preparation complete; final V9 model not yet" in report
