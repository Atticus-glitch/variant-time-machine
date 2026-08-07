"""Fast safeguards for V9.1 data, selection, and final-test isolation."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from variant_time_machine.v8_presentation import sha256_file
from variant_time_machine.v9_1 import (
    V91Error,
    _feature_audit,
    _feature_sets,
    _rank_families,
    _thresholds,
    run_v9_1_development,
)
from variant_time_machine.v9_1_finalize import (
    EXPECTED_ELIGIBLE_PROTOCOL_SHA256,
    _authenticate_trial,
    _eligible_protocol_hash,
)
from variant_time_machine.v9_original import build_original_v9_record

ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict[str, object]:
    return json.loads((ROOT / "config/v9_1.json").read_text(encoding="utf-8"))


def test_original_v9_registry_freezes_opened_not_reviewed_evidence() -> None:
    recorded = json.loads(
        (ROOT / "outputs/model_registry/model_v9_original.json").read_text(
            encoding="utf-8"
        )
    )
    assert recorded == build_original_v9_record(ROOT)
    assert recorded["name"] == "V9 original reviewed-dataset model"
    assert recorded["scientific_name"] == "V9 original opened-V8 exploratory model"
    assert recorded["manual_review_dataset"]["completed_reviews"] == 0
    assert recorded["test_data"]["records"] == 0
    assert recorded["official_model"] is False


def test_v9_1_dataset_views_preserve_every_record_and_label() -> None:
    directory = ROOT / "data/processed/v9_1"
    manifest = json.loads(
        (directory / "v9_1_dataset_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"] == {
        "all_eligible": 1000,
        "ambiguous": 1000,
        "clean_reviewed": 0,
        "excluded": 0,
        "strict_clean": 0,
    }
    assert manifest["labels_corrected"] == 0
    assert manifest["manual_review_completed"] == 0
    assert manifest["official_model_selection_allowed"] is False
    assert manifest["final_test_allowed"] is False
    for filename, expected in manifest["output_hashes"].items():
        assert sha256_file(directory / filename) == expected
    with (directory / "v9_1_all_eligible_dataset.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1000
    assert len({row["variation_id"] for row in rows}) == 1000
    assert all(
        row["dataset_outcome"] == row["original_automatic_outcome"] for row in rows
    )
    assert {row["v9_1_review_state"] for row in rows} == {"review_pending"}


def test_v9_1_feature_sets_are_allowlisted_and_gene_free() -> None:
    config = _config()
    feature_sets = _feature_sets(config)
    audit = _feature_audit(
        feature_sets,
        ROOT / "config/v9_1.json",
        ROOT / "data/processed/v9_1/v9_1_all_eligible_dataset.csv",
    )
    assert audit["status"] == "pass"
    assert audit["feature_count"] == 64
    assert audit["manual_review_features"] == 0
    assert audit["future_or_newer_features"] == 0
    assert audit["gene_identity"] == "ineligible_not_fit"
    assert (
        feature_sets["all_allowed_non_leaky"]
        == feature_sets["all_allowed_without_gene"]
    )


def test_threshold_selection_uses_only_supplied_validation_values() -> None:
    config = _config()
    targets = np.asarray([0, 0, 0, 1, 1, 1])
    probabilities = np.asarray([0.1, 0.2, 0.4, 0.3, 0.7, 0.9])
    groups = np.asarray(["a", "b", "c", "d", "e", "f"])
    primary, safety, score = _thresholds(targets, probabilities, groups, config)
    assert 0.1 <= primary <= 0.9
    assert 0.1 <= safety <= 0.9
    assert score == pytest.approx(5 / 6)
    assert config["final_test_available"] is False
    assert config["final_test_evaluated"] is False


def test_family_ranking_applies_close_tolerance_before_macro_f1() -> None:
    config = _config()
    metrics = {
        "random_forest": {
            "component_weighted_balanced_accuracy": 0.900,
            "macro_f1": 0.81,
            "pathogenic_recall": 0.90,
            "brier_score": 0.08,
        },
        "extra_trees": {
            "component_weighted_balanced_accuracy": 0.896,
            "macro_f1": 0.83,
            "pathogenic_recall": 0.89,
            "brier_score": 0.07,
        },
    }
    selected, trace = _rank_families(metrics, config)
    assert selected == "extra_trees"
    assert trace["close_families"] == ["random_forest", "extra_trees"]


def test_v9_1_runner_requires_persistent_output_or_publication() -> None:
    with pytest.raises(V91Error, match="output-dir"):
        run_v9_1_development(ROOT)


def test_current_eligible_protocol_matches_authenticated_trial_families() -> None:
    assert _eligible_protocol_hash(_config()) == EXPECTED_ELIGIBLE_PROTOCOL_SHA256


def test_finalizer_rejects_wrong_trial_config_before_using_metrics(
    tmp_path: Path,
) -> None:
    manifest = {
        "status": "v9_1_internal_development_complete",
        "official_v9_1_model": False,
        "final_test_evaluated": False,
        "config_sha256": "wrong",
        "output_hashes": {},
    }
    (tmp_path / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V91Error, match="pinned manifest"):
        _authenticate_trial(tmp_path)


def test_published_v9_1_bundle_is_locked_and_hash_complete() -> None:
    output_dir = ROOT / "outputs/v9_1_development"
    manifest = json.loads((output_dir / "run_manifest.json").read_text())
    assert manifest["status"] == "v9_1_internal_development_complete_fully_nested"
    assert manifest["official_v9_1_model"] is False
    assert manifest["final_test_available"] is False
    assert manifest["final_test_evaluated"] is False
    assert manifest["validation_estimate"] == "nested_family_selection_procedure"
    assert manifest["outer_selected_family_counts"] == {
        "extra_trees": 800,
        "random_forest": 200,
    }
    for filename, expected_hash in manifest["output_hashes"].items():
        assert sha256_file(output_dir / filename) == expected_hash


def test_published_v9_1_metrics_and_claim_locks_are_consistent() -> None:
    output_dir = ROOT / "outputs/v9_1_development"
    with (output_dir / "candidate_models.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        candidates = {row["candidate"]: row for row in csv.DictReader(handle)}
    selected = candidates["nested_family_selection_procedure"]
    assert selected["status"] == "selected_internal_validation_procedure"
    assert float(selected["component_weighted_balanced_accuracy"]) == pytest.approx(
        0.8938749515640781
    )
    assert float(selected["accuracy"]) == pytest.approx(0.875)
    assert candidates["small_mlp"]["status"] == "invalid_protocol_mismatch_not_ranked"
    assert candidates["small_mlp"]["selected"] == "False"

    bootstrap = json.loads((output_dir / "bootstrap_intervals.json").read_text())
    for reference in ("original_v9", "frozen_v8"):
        lower, upper = bootstrap[
            "selected_v9_1_paired_component_weighted_balanced_accuracy_difference"
        ][reference]
        assert lower < 0 < upper

    registry = json.loads((output_dir / "model_registry.json").read_text())
    assert registry["official_v9_1_model"] is False
    assert registry["final_test_evaluated"] is False
    assert registry["comparison_to_v8"]["fairly_beat_v8"] is False
    assert (
        sha256_file(ROOT / registry["artifact"]["path"])
        == registry["artifact"]["sha256"]
    )


def test_published_v9_1_oof_and_calibration_schemas_are_complete() -> None:
    output_dir = ROOT / "outputs/v9_1_development"
    with (output_dir / "oof_predictions.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1000
    assert len({row["variation_id"] for row in rows}) == 1000
    assert sum(row["v9_1_correct"] == "True" for row in rows) == 875
    assert {row["v9_1_outer_selected_family"] for row in rows} == {
        "extra_trees",
        "random_forest",
    }

    with (output_dir / "calibration.csv").open(encoding="utf-8", newline="") as handle:
        calibration = list(csv.DictReader(handle))
    assert calibration
    assert {row["evidence_generation"] for row in calibration} == {
        "authenticated_family_trial",
        "fully_nested_selection_procedure",
    }
