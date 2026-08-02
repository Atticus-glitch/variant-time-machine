"""Tests for deterministic V8 presentation-only artifacts."""

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from variant_time_machine.v8_presentation import (
    CASE_STUDY_SALT,
    CORRECT_SAMPLE_SIZE,
    ERROR_FIELDS,
    QUEUE_FIELDS,
    SUGGESTED_CATEGORIES,
    V8PresentationError,
    build_case_studies,
    build_error_rows,
    build_review_queue,
    build_v8_presentation,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_csv(relative: str) -> list[dict[str, str]]:
    with (ROOT / relative).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _fixture_rows() -> list[dict[str, str]]:
    return [
        {
            "variation_id": "1",
            "gene_symbols": "ONE",
            "consequence": "missense",
            "v8_probability": "0.1",
            "v8_prediction": "benign",
            "v7_probability": "0.8",
            "v7_prediction": "pathogenic",
            "actual_outcome": "moved_toward_benign",
            "answer_classification": "Likely benign",
        },
        {
            "variation_id": "2",
            "gene_symbols": "TWO",
            "consequence": "loss_of_function",
            "v8_probability": "0.9",
            "v8_prediction": "pathogenic",
            "v7_probability": "0.2",
            "v7_prediction": "benign",
            "actual_outcome": "moved_toward_benign",
            "answer_classification": "Benign",
        },
        {
            "variation_id": "3",
            "gene_symbols": "THREE",
            "consequence": "unrecognized",
            "v8_probability": "0.2",
            "v8_prediction": "benign",
            "v7_probability": "0.7",
            "v7_prediction": "pathogenic",
            "actual_outcome": "moved_toward_pathogenic",
            "answer_classification": "Pathogenic",
        },
        {
            "variation_id": "4",
            "gene_symbols": "FOUR",
            "consequence": "missense",
            "v8_probability": "0.9",
            "v8_prediction": "pathogenic",
            "v7_probability": "0.8",
            "v7_prediction": "pathogenic",
            "actual_outcome": "moved_toward_pathogenic",
            "answer_classification": "Likely pathogenic",
        },
    ]


def test_fixture_error_categories_and_queue_are_deterministic() -> None:
    rows = _fixture_rows()
    contexts = {row["variation_id"]: {} for row in rows}
    errors = build_error_rows(rows, contexts, "frozen-hash")
    assert [row["error_type"] for row in errors] == ["FP", "FN"]
    assert errors[0]["suggested_category"] == ("predicted pathogenic but later benign")
    assert errors[1]["suggested_category"] == "possible missing consequence"
    assert {row["suggestion_status"] for row in errors} == {"unverified"}

    first = build_review_queue(rows, contexts, "frozen-hash")
    second = build_review_queue(list(reversed(rows)), contexts, "frozen-hash")
    assert [row["variation_id"] for row in first] == ["2", "3", "1", "4"]
    assert [row["variation_id"] for row in second] == ["2", "3", "1", "4"]
    assert len({row["variation_id"] for row in first}) == len(first)
    assert "false positive" in first[0]["reasons"]
    assert "V8/V7 disagreement" in first[0]["reasons"]


def test_fixture_case_selection_discloses_hash_method() -> None:
    rows = _fixture_rows()
    cases = build_case_studies(
        rows, {row["variation_id"]: {} for row in rows}, {"fixture": True}
    )
    assert cases["selection"]["salt"] == CASE_STUDY_SALT
    assert cases["selection"]["random_at_page_load"] is False
    assert [row["confusion_group"] for row in cases["case_studies"]] == [
        "TN",
        "TP",
        "FP",
        "FN",
    ]
    assert all(row["vcv_accession"] == "not recorded" for row in cases["case_studies"])


def test_generated_summary_has_exact_frozen_metrics_and_provenance() -> None:
    summary = json.loads(
        (ROOT / "outputs/evaluations/frozen/v8_public_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["n"] == 1000
    assert summary["accuracy"] == 0.895
    assert summary["balanced_accuracy"] == 0.8712121212121212
    assert summary["macro_f1"] == 0.8403709475124472
    assert summary["model_type"] == "calibrated elastic-net logistic regression"
    assert summary["sealed_gene_components"] == 559
    assert len(summary["caveats"]) >= 6
    assert summary["recalls"] == {
        "benign": 0.9090909090909091,
        "pathogenic": 0.8333333333333334,
    }
    assert summary["confusion_matrix"] == {"TN": 740, "FP": 74, "FN": 31, "TP": 155}
    assert summary["wrong"] == 105
    assert summary["leakage_audit"]["status"] == "pass"
    assert summary["v7_same_record"]["interval_crosses_zero"] is True
    assert "no statistically clear overall superiority" in summary["strongest_claim"]
    assert summary["v7_same_record"]["paired_difference_95_percent"] == [
        -0.02450184283147039,
        0.03312248143795588,
    ]
    for source in summary["provenance"]["source_artifacts"]:
        assert source["sha256"] == sha256_file(ROOT / source["path"])


def test_generated_case_studies_have_four_balanced_groups_and_stable_ids() -> None:
    document = json.loads(
        (ROOT / "outputs/case_studies/v8_case_studies.json").read_text(encoding="utf-8")
    )
    rows = document["case_studies"]
    assert len(rows) == 20
    assert Counter(row["confusion_group"] for row in rows) == {
        "TN": 5,
        "TP": 5,
        "FP": 5,
        "FN": 5,
    }
    assert document["selection"]["selected_ids"] == {
        "TN": ["2646459", "1478553", "1519128", "1935539", "1372659"],
        "TP": ["1675625", "1480008", "2002672", "1805124", "2058503"],
        "FP": ["1444570", "1508049", "2153622", "1358885", "2530789"],
        "FN": ["2179139", "2085378", "1403780", "1367200", "2125741"],
    }
    required = {
        "variation_id",
        "vcv_accession",
        "gene",
        "old_classification",
        "later_classification",
        "actual_direction",
        "predicted_direction",
        "v8_probability",
        "confidence",
        "correct",
        "confusion_group",
        "consequence",
        "key_features",
        "match_confidence",
        "review_status",
        "warnings",
        "source_links",
        "manual_status",
    }
    assert all(required.issubset(row) for row in rows)
    assert {row["old_classification"] for row in rows} == {"Uncertain significance"}
    assert {row["vcv_accession"] for row in rows} == {"not recorded"}


def test_generated_error_file_is_wrong_only_and_complete() -> None:
    rows = _read_csv("outputs/error_analysis/model_v8_errors.csv")
    assert len(rows) == 105
    assert Counter(row["error_type"] for row in rows) == {"FP": 74, "FN": 31}
    assert set(ERROR_FIELDS) == set(rows[0])
    assert {row["suggestion_status"] for row in rows} == {"unverified"}
    assert {row["suggested_category"] for row in rows} <= set(SUGGESTED_CATEGORIES)
    assert {row["old_classification"] for row in rows} == {"Uncertain significance"}
    assert all(row["actual_outcome"] != row["predicted_class"] for row in rows)


def test_generated_queue_has_union_reasons_no_duplicates_and_expected_order() -> None:
    predictions = _read_csv("outputs/ai_temporal_v8/temporal_test_predictions.csv")
    queue = _read_csv("outputs/manual_review/v8_review_queue.csv")
    wrong_ids = {
        row["variation_id"]
        for row in predictions
        if row["actual_outcome"].removeprefix("moved_toward_") != row["v8_prediction"]
    }
    disagreement_ids = {
        row["variation_id"]
        for row in predictions
        if row["v8_prediction"] != row["v7_prediction"]
    }
    queue_ids = [row["variation_id"] for row in queue]
    assert set(QUEUE_FIELDS) == set(queue[0])
    assert len(queue_ids) == len(set(queue_ids))
    assert wrong_ids | disagreement_ids <= set(queue_ids)
    assert sum(row["correct_sample"] == "true" for row in queue) == CORRECT_SAMPLE_SIZE
    assert sum(row["high_confidence"] == "true" for row in queue) == 19
    assert [int(row["queue_order"]) for row in queue] == list(range(1, len(queue) + 1))
    buckets = []
    for row in queue:
        if "high-confidence wrong" in row["reasons"]:
            buckets.append(0)
        elif row["error_type"] == "FN":
            buckets.append(1)
        elif row["error_type"] == "FP":
            buckets.append(2)
        elif row["v8_v7_disagreement"] == "true":
            buckets.append(3)
        else:
            buckets.append(4)
    assert buckets == sorted(buckets)


def test_builder_never_overwrites_existing_manual_notes(tmp_path: Path) -> None:
    sources = (
        "outputs/ai_temporal_v8/temporal_test_predictions.csv",
        "outputs/evaluations/frozen/v8_metrics.json",
        "outputs/evaluations/frozen/v8_protocol_audit.json",
        "outputs/error_analysis/v8_all_rows.csv",
    )
    for relative in sources:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    notes = tmp_path / "outputs/manual_review/v8_review_notes.json"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text('{"schema_version": 1, "reviews": {"keep": true}}\n')
    before = notes.read_bytes()
    created = build_v8_presentation(tmp_path)
    assert notes.read_bytes() == before
    assert notes not in created


def test_builder_refuses_changed_frozen_prediction_source(tmp_path: Path) -> None:
    sources = (
        "outputs/ai_temporal_v8/temporal_test_predictions.csv",
        "outputs/evaluations/frozen/v8_metrics.json",
        "outputs/evaluations/frozen/v8_protocol_audit.json",
        "outputs/error_analysis/v8_all_rows.csv",
    )
    for relative in sources:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    predictions = tmp_path / sources[0]
    predictions.write_bytes(predictions.read_bytes() + b"\n")
    with pytest.raises(V8PresentationError, match="source hash changed"):
        build_v8_presentation(tmp_path)


def test_builder_creates_reproducible_empty_notes_store(tmp_path: Path) -> None:
    for relative in (
        "outputs/ai_temporal_v8/temporal_test_predictions.csv",
        "outputs/evaluations/frozen/v8_metrics.json",
        "outputs/evaluations/frozen/v8_protocol_audit.json",
        "outputs/error_analysis/v8_all_rows.csv",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    build_v8_presentation(tmp_path)
    notes = json.loads(
        (tmp_path / "outputs/manual_review/v8_review_notes.json").read_text(
            encoding="utf-8"
        )
    )
    assert notes["reviews"] == {}
    assert notes["allowed_decisions"] == [
        "match correct",
        "match ambiguous",
        "classification-scope problem",
        "model genuinely wrong",
        "exclude from final analysis",
    ]
    assert notes["provenance"]["generator"] == "scripts/build_v8_presentation.py"


def test_public_outputs_make_no_clinical_performance_claim() -> None:
    paths = (
        ROOT / "outputs/evaluations/frozen/v8_public_summary.json",
        ROOT / "outputs/case_studies/v8_case_studies.json",
    )
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "not clinical validation" in text
    assert "does not support clinical use" in text
    assert "clinical utility" not in text
    assert "improves clinical" not in text
