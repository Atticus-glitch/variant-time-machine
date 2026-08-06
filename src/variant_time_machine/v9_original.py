"""Freeze the original opened-data V9 exploration without rewriting its artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from variant_time_machine.v8_presentation import sha256_file


class V9OriginalError(ValueError):
    """Raised when the original V9 evidence cannot be authenticated."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V9OriginalError(f"Expected a JSON object: {path}")
    return value


def build_original_v9_record(project_root: Path) -> dict[str, Any]:
    """Build a deterministic registry record from the committed V9 artifacts."""
    root = project_root.resolve()
    output_dir = root / "outputs/v9_exploratory"
    manifest = _load_json(output_dir / "run_manifest.json")
    metrics = _load_json(output_dir / "candidate_metrics.json")
    selections = _load_json(output_dir / "nested_selections.json")
    dataset_manifest = _load_json(root / "data/processed/v9/v9_dataset_manifest.json")
    model_path = output_dir / "exploratory_leader.joblib"
    expected_model_hash = manifest.get("output_hashes", {}).get(model_path.name)
    if expected_model_hash != sha256_file(model_path):
        raise V9OriginalError("Original V9 model hash does not match its run manifest.")
    model = joblib.load(model_path)
    if (
        manifest.get("status") != "exploratory_opened_v8_only"
        or manifest.get("official_v9_winner") is not None
        or model.get("status") != "exploratory_opened_v8_only"
    ):
        raise V9OriginalError("Original V9 lock state is invalid.")
    leader = str(manifest["exploratory_leader_among_new_candidate_families"])
    result = metrics[leader]
    matrix = result["confusion_matrix"]
    feature_names = list(manifest["feature_names"])
    return {
        "schema_version": 1,
        "model_id": "V9-original",
        "name": "V9 original reviewed-dataset model",
        "scientific_name": "V9 original opened-V8 exploratory model",
        "label_warning": (
            "The requested historical label is retained, but no completed human-review "
            "dataset was used. This was exploration on previously opened V8 records."
        ),
        "effective_status": "frozen_exploratory_opened_data",
        "official_model": False,
        "official_v9_winner": None,
        "model_type": "Platt-calibrated elastic-net logistic regression",
        "estimator": {
            "family": leader,
            "full_data_configuration": model["configuration"],
            "full_data_threshold": model["threshold"],
            "outer_fold_selections": selections[leader],
        },
        "training_data": {
            "dataset": "data/processed/v9/v9_messy_dataset.csv",
            "records_per_outer_fit": 800,
            "opened_records_available": manifest["dataset_records"],
            "components": manifest["dataset_components"],
            "labels": "unchanged original automatic V8 outcomes",
        },
        "validation_data": {
            "method": "5-fold nested component-grouped out-of-fold validation",
            "outer_validation_records_per_fold": 200,
            "inner_folds": 4,
            "fold_assignments": "outputs/v9_exploratory/fold_assignments.csv",
            "component_overlap": 0,
        },
        "test_data": {
            "records": 0,
            "status": "no independent or final V9 test was evaluated",
        },
        "features": feature_names,
        "feature_count": len(feature_names),
        "metrics": result,
        "confusion_matrix": {
            "actual_benign": {
                "predicted_benign": matrix["TN"],
                "predicted_pathogenic": matrix["FP"],
            },
            "actual_pathogenic": {
                "predicted_benign": matrix["FN"],
                "predicted_pathogenic": matrix["TP"],
            },
        },
        "class_distribution": manifest["target_counts"],
        "manual_review_dataset": {
            "completed_reviews": 0,
            "clean_reviewed_records": dataset_manifest["number_included_clean"],
            "review_pending_records": dataset_manifest["number_excluded"],
            "used_for_model_fitting": False,
        },
        "leakage_audit": {
            "status": dataset_manifest["leakage_audit_status"],
            "eligible_features": "exact authenticated feature__* allowlist",
            "outer_component_overlap": 0,
            "final_test_protection": "not applicable; no final test existed",
        },
        "creation_time": manifest["created_at_utc"],
        "frozen_by_git_commit": "14056fff8086104091d3c3f75409860af3d79531",
        "artifact": {
            "path": "outputs/v9_exploratory/exploratory_leader.joblib",
            "sha256": expected_model_hash,
            "size_bytes": model_path.stat().st_size,
        },
        "source_hashes": {
            "run_manifest": sha256_file(output_dir / "run_manifest.json"),
            "candidate_metrics": sha256_file(output_dir / "candidate_metrics.json"),
            "oof_predictions": sha256_file(output_dir / "oof_predictions.csv"),
            "dataset": manifest["dataset_sha256"],
            "dataset_manifest": manifest["dataset_manifest_sha256"],
            "config": manifest["config_sha256"],
        },
        "limitations": [
            "All 1,000 outcomes had already been opened during V8 analysis.",
            "No completed human reviews or clean-reviewed rows were used.",
            "Only 1,000 records were available for nested development, compared with "
            "9,818 V8 development records.",
            "There was no independent temporal or component-disjoint final V9 test.",
            "The OOF comparison with frozen V8 is asymmetric because V8 was evaluated "
            "while sealed.",
            "The task is retrospective aggregate-direction prediction, not prediction "
            "of whether a VUS resolves.",
            "The artifact is not clinically validated and must not be used for medical "
            "decisions.",
        ],
    }


def freeze_original_v9(project_root: Path) -> Path:
    """Create the original V9 registry record once, preserving any exact prior copy."""
    root = project_root.resolve()
    path = root / "outputs/model_registry/model_v9_original.json"
    payload = build_original_v9_record(root)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise V9OriginalError(
                "Existing original V9 registry record differs; preserve it."
            )
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return path
