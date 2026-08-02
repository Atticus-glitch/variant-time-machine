"""Tests for evidence-backed model registry and reporting."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

from variant_time_machine.model_registry import (
    BENIGN,
    DISTINCT_TEST_WARNING,
    PATHOGENIC,
    PROJECT_TIMELINE,
    SMALL_TEST_WARNING,
    UNKNOWN,
    RegistryError,
    baseline_predictions,
    compute_binary_metrics,
    create_registry,
    generate_error_analysis,
    leakage_audit,
    load_model_record_or_placeholder,
    load_prediction_explorer,
    load_prediction_rows,
    load_registry,
    prediction_explorer_detail,
    rank_models,
    save_registry,
    update_error_review,
)

ROOT = Path(__file__).resolve().parents[1]


def _rows() -> list[dict[str, str]]:
    return [
        {
            "variation_id": "1",
            "actual_outcome": BENIGN,
            "pathogenic_probability": "0.1",
            "prediction": "benign",
        },
        {
            "variation_id": "2",
            "actual_outcome": BENIGN,
            "pathogenic_probability": "0.8",
            "prediction": "pathogenic",
        },
        {
            "variation_id": "3",
            "actual_outcome": PATHOGENIC,
            "pathogenic_probability": "0.2",
            "prediction": "benign",
        },
        {
            "variation_id": "4",
            "actual_outcome": PATHOGENIC,
            "pathogenic_probability": "0.9",
            "prediction": "pathogenic",
        },
    ]


def test_registry_creation_and_loading(tmp_path: Path) -> None:
    registry = create_registry(ROOT)
    path = tmp_path / "registry.json"
    save_registry(registry, path)
    loaded = load_registry(path)
    assert [model["model_id"] for model in loaded["models"]] == [
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "V8",
    ]
    assert all("manual_review" in model for model in loaded["models"])
    assert all("input_feature_list" in model for model in loaded["models"])
    assert all("excluded_feature_list" in model for model in loaded["models"])
    assert loaded["warnings"] == [DISTINCT_TEST_WARNING]


def test_registry_reports_missing_artifacts() -> None:
    with pytest.raises(FileNotFoundError, match="Required artifact is missing"):
        create_registry(Path("/definitely/missing/project"))


def test_leakage_detects_banned_future_fields() -> None:
    passed = leakage_audit(["missense_consequence", "classification_age_days"])
    failed = leakage_audit(["missense_consequence", "newer_classification"])
    assert passed["status"] == "pass"
    assert failed["status"] == "fail"
    assert failed["findings"][0]["field"] == "newer_classification"


def test_metrics_include_balanced_accuracy_and_confusion() -> None:
    metrics = compute_binary_metrics(
        [BENIGN, BENIGN, PATHOGENIC, PATHOGENIC],
        [BENIGN, PATHOGENIC, BENIGN, PATHOGENIC],
    )
    assert metrics["accuracy"] == 0.5
    assert metrics["balanced_accuracy"] == 0.5
    assert metrics["macro_f1"] == 0.5
    assert metrics["macro_precision"] == 0.5
    assert metrics["macro_recall"] == 0.5
    assert metrics["weighted_f1"] == 0.5
    assert metrics["number_correct"] == 2
    assert metrics["number_wrong"] == 2
    assert metrics["confusion_matrix"]["actual_benign"] == {
        "predicted_benign": 1,
        "predicted_pathogenic": 1,
    }


def test_v4_v5_metrics_are_derived_without_changing_recorded_headlines() -> None:
    registry = create_registry(ROOT)
    by_id = {model["model_id"]: model for model in registry["models"]}
    assert by_id["V4"]["metrics"]["accuracy"] == 0.76
    assert by_id["V4"]["metrics"]["balanced_accuracy"] == 0.625
    assert by_id["V5"]["metrics"]["accuracy"] == 0.82
    assert by_id["V5"]["metrics"]["balanced_accuracy"] == 0.8219780219780219
    assert isinstance(by_id["V4"]["metrics"]["macro_f1"], float)


def test_v8_registry_uses_versioned_fields_and_paired_same_record_v7() -> None:
    registry = create_registry(ROOT)
    v8 = next(model for model in registry["models"] if model["model_id"] == "V8")
    assert v8["feature_count"] == 64
    assert v8["test_records"] == 1000
    assert v8["class_distribution"]["sealed_test_gene_components"] == 559
    assert v8["metrics"]["accuracy"] == 0.895
    assert v8["metrics"]["balanced_accuracy"] == 0.8712121212121212
    assert v8["paired_same_record_baseline"] == {
        "model_id": "V7",
        "records": 1000,
        "balanced_accuracy": 0.8666878021716731,
        "v8_minus_v7_balanced_accuracy": 0.004524319040448144,
        "paired_difference_95_percent": [
            -0.02450184283147039,
            0.03312248143795588,
        ],
    }


def test_ranking_prioritizes_leakage_and_has_no_stable_winner() -> None:
    models = [
        {
            "model_id": "V5",
            "metrics": {"balanced_accuracy": 0.99, "macro_f1": 0.99},
            "leakage_audit": {"status": "fail"},
            "evaluation_reliability": "independent temporal",
            "interpretability": "high",
            "manual_review": "complete",
        },
        {
            "model_id": "V6",
            "metrics": {"balanced_accuracy": 0.6, "macro_f1": 0.6},
            "leakage_audit": {"status": "pass"},
            "evaluation_reliability": "internal holdout",
            "interpretability": "limited",
            "manual_review": UNKNOWN,
        },
    ]
    result = rank_models(models)
    assert result["ranking"] == []
    assert result["comparison_status"] == "not_rankable_across_current_evaluations"
    assert result["stable_winner"] is None
    assert "strongest component-isolation design" in result["conclusion"]
    assert "not ranked" in result["evidence_summary"]["own_test_score_context"]


def test_small_test_warning_is_explicit() -> None:
    registry = create_registry(ROOT)
    assert "n=100" in SMALL_TEST_WARNING
    assert any("different" in warning for warning in registry["warnings"])


def test_error_file_contains_all_rows_and_unknown_vcv(tmp_path: Path) -> None:
    path = tmp_path / "errors.csv"
    generated = generate_error_analysis("V-test", _rows(), path)
    with path.open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert len(generated) == len(saved) == 4
    assert {row["correct"] for row in saved} == {"true", "false"}
    assert {row["vcv_accession"] for row in saved} == {"not recorded"}
    assert "suspected_error_category" in saved[0]


def test_v8_error_analysis_uses_recorded_temporal_context(tmp_path: Path) -> None:
    path = tmp_path / "v8-errors.csv"
    rows = [
        {
            "variation_id": "8",
            "actual_outcome": PATHOGENIC,
            "v8_probability": "0.9",
            "v8_prediction": "pathogenic",
            "gene_symbols": "GENE8",
            "answer_classification": "Pathogenic",
            "consequence": "missense",
        }
    ]
    generated = generate_error_analysis("V8", rows, path)
    assert generated[0]["gene"] == "GENE8"
    assert generated[0]["actual_later_classification"] == "Pathogenic"
    assert generated[0]["key_features"] == "consequence=missense"


def test_prediction_explorer_uses_all_v8_rows_not_wrong_only() -> None:
    explorer = load_prediction_explorer(
        ROOT, ROOT / "data/manual_review/model_error_reviews.json"
    )
    v8_rows = [row for row in explorer["rows"] if row["v8_prediction"] is not None]
    assert len(v8_rows) == 1000
    assert sum(row["v8_correct"] is False for row in v8_rows) == 105

    correct_id = next(row["variation_id"] for row in v8_rows if row["v8_correct"])
    detail = prediction_explorer_detail(
        ROOT, correct_id, ROOT / "data/manual_review/model_error_reviews.json"
    )
    assert detail["model_results"]["V8"]["correct"] == "true"


def test_generic_review_store_rejects_v8(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    with pytest.raises(RegistryError, match="focused Manual Review Queue"):
        update_error_review(
            path,
            "V8",
            "123",
            status="reviewed",
            category="unknown",
            notes="wrong store",
        )
    assert not path.exists()


def test_timeline_has_exactly_fourteen_ordered_items() -> None:
    assert len(PROJECT_TIMELINE) == 14
    assert [item["due_date"] for item in PROJECT_TIMELINE] == sorted(
        item["due_date"] for item in PROJECT_TIMELINE
    )
    assert PROJECT_TIMELINE[0]["title"] == "Freeze current V4/V5 results"


def test_prediction_reader_refuses_large_files(tmp_path: Path) -> None:
    path = tmp_path / "too-large.csv"
    path.write_text(
        "variation_id,actual_outcome,pathogenic_probability,prediction\n"
        "1,moved_toward_benign,0.1,benign\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="Refusing large prediction"):
        load_prediction_rows(path, max_bytes=2)


def test_missing_predictions_do_not_create_synthetic_evaluation(tmp_path: Path) -> None:
    missing = tmp_path / "predictions.csv"
    with pytest.raises(FileNotFoundError, match="Prediction artifact is missing"):
        load_prediction_rows(missing)
    assert not missing.exists()


def test_seeded_baselines_are_reproducible_and_aligned() -> None:
    rows = _rows()
    first = baseline_predictions(rows, seed=7)
    second = baseline_predictions(list(reversed(rows)), seed=7)
    assert first["majority"] == [BENIGN] * 4
    assert first["seeded_random_stratified"].count(BENIGN) == 2
    assert len(second["seeded_random_stratified"]) == len(rows)
    majority_metrics = compute_binary_metrics(
        [row["actual_outcome"] for row in rows], first["majority"]
    )
    assert majority_metrics["pathogenic_f1"] == 0.0
    assert majority_metrics["macro_f1"] == pytest.approx(1 / 3)


def test_registry_file_rejects_nonstandard_model_set(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps({"schema_version": 1, "models": [{"model_id": "V1"}]}),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="ordered V1-V8"):
        load_registry(path)


def test_missing_model_record_is_honest_placeholder(tmp_path: Path) -> None:
    record = load_model_record_or_placeholder(
        tmp_path / "model_v6.json", "V6", ["outputs/models/frozen/model_v6.json"]
    )
    assert record["status"] == "files_not_found"
    assert record["metrics"]["accuracy"] == UNKNOWN
    assert "no metrics were fabricated" in record["warnings"][1]


def test_generated_registry_contract_and_standardized_v5_metrics() -> None:
    registry_root = ROOT / "outputs" / "model_registry"
    for version in range(1, 9):
        assert (registry_root / f"model_v{version}.json").is_file()
    index = json.loads((registry_root / "model_index.json").read_text(encoding="utf-8"))
    assert index["latest_model_version"] == "V8"
    assert "strongest component-isolation design" in index["best_validated_model"]
    assert (
        "V7 retains the stronger archive-time boundary" in index["best_validated_model"]
    )

    metrics = json.loads(
        (ROOT / "outputs/evaluations/frozen/v5_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert metrics["accuracy"] == 0.82
    assert metrics["balanced_accuracy"] == pytest.approx(0.8219780219780219)
    assert metrics["macro_f1"] == pytest.approx(0.8089983022071308)
    assert {item["model"] for item in metrics["baseline_comparison"]} == {
        "V5",
        "majority",
        "seeded_random_stratified",
        "V2_clue_baseline",
    }
    v6_metrics = json.loads(
        (ROOT / "outputs/evaluations/frozen/v6_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert v6_metrics["records"] == 1000
    assert v6_metrics["accuracy"] == 0.756
    assert v6_metrics["balanced_accuracy"] == pytest.approx(0.7435492978780002)
    v7_metrics = json.loads(
        (ROOT / "outputs/evaluations/frozen/v7_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert v7_metrics["records"] == 1000
    assert v7_metrics["accuracy"] == 0.785
    assert v7_metrics["balanced_accuracy"] == pytest.approx(0.7906832298136646)
    v7_audit = json.loads(
        (ROOT / "outputs/evaluations/frozen/v7_protocol_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert v7_audit["development_test_variation_id_overlap"] == 0
    assert v7_audit["test_records_sharing_development_gene"] == 699
    assert v7_audit["missing_from_answer_snapshot"] == 30
    assert v7_audit["candidate_accounting_complete"] is True
    v8_metrics = json.loads(
        (ROOT / "outputs/evaluations/frozen/v8_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert v8_metrics["records"] == 1000
    assert v8_metrics["sealed_gene_components"] == 559
    assert v8_metrics["accuracy"] == 0.895
    assert v8_metrics["balanced_accuracy"] == 0.8712121212121212
    assert v8_metrics["v7_same_record_baseline"]["balanced_accuracy"] == (
        0.8666878021716731
    )
    assert v8_metrics["v8_minus_v7_balanced_accuracy"] == 0.004524319040448144
    v8_audit = json.loads(
        (ROOT / "outputs/evaluations/frozen/v8_protocol_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert v8_audit["status"] == "pass"
    assert v8_audit["paired_interval_crosses_zero"] is True
    assert v8_audit["checks"]["current_vault_matches_commitment"] is True
    assert v8_audit["checks"]["current_model_matches_commitment"] is True
    assert v8_audit["checks"]["current_sources_match_commitments"] is True


def test_generated_logs_audits_errors_and_timeline_have_required_fields() -> None:
    for suffix in ("json", "md"):
        assert (
            ROOT / f"outputs/logs/2026-08-01_model_v5_evaluation.{suffix}"
        ).is_file()
    audit = json.loads(
        (ROOT / "outputs/leakage_audits/v5_leakage_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["status"] == "pass"
    assert audit["banned_fields_found"] == []
    with (ROOT / "outputs/error_analysis/model_v5_errors.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    assert {
        "gene",
        "old_classification",
        "actual_later_classification",
        "suspected_error_category",
        "manual_review_status",
    }.issubset(rows[0])
    timeline = json.loads(
        (ROOT / "outputs/project_timeline.json").read_text(encoding="utf-8")
    )
    assert len(timeline["tasks"]) == 14
    assert {
        "title",
        "due_date",
        "category",
        "priority",
        "description",
        "success_condition",
        "related_output_file",
        "status",
    } == set(timeline["tasks"][0])


def test_large_local_artifacts_remain_git_ignored() -> None:
    paths = (
        "data/processed/resolved_direction_v2.sqlite3",
        "data/raw/clinvar/variant_summary_2026-07.txt.gz",
        "outputs/ai_holdout_v5/model.joblib",
        "outputs/ai_temporal_v7/model.joblib",
        "outputs/ai_temporal_v7/sealed_candidate_predictions.sqlite3",
        ".venv/bin/python",
    )
    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, path
