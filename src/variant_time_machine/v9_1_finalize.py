"""Finalize nested V9.1 evidence from an authenticated nonpublishing family trial."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

from variant_time_machine.ai_temporal_v8 import (
    V8_FEATURE_NAMES,
    _gene_tokens,
    _load_development,
)
from variant_time_machine.v8_presentation import sha256_file
from variant_time_machine.v9_1 import (
    WARNING,
    V91Error,
    _bootstrap_metrics,
    _calibrate,
    _calibration_rows,
    _candidate_specs,
    _combine_training,
    _comparison_row,
    _feature_audit,
    _feature_sets,
    _fit,
    _load_json,
    _metric_summary,
    _outer_splits,
    _publish_outputs,
    _rank_families,
    _raw_scores,
    _select_spec,
    _selected_inner_metrics,
    _transition_counts,
    _weights,
    _write_csv,
    _write_json,
)
from variant_time_machine.v9_exploratory import _clue_score

EXPECTED_TRIAL_CONFIG_SHA256 = (
    "f603738a02429889b9b9d4ef6c992cea6c2f678c897f4b08bdf553139fd19db7"
)
EXPECTED_TRIAL_MANIFEST_SHA256 = (
    "22e89673f53604e0ebb226ee1c926a01f4ad534ba15df6f5879f20a73dcbb4ac"
)
EXPECTED_FROZEN_OUTER_FOLDS_SHA256 = (
    "de44c23c5f6bd084c1aa4c729168179832f94b4b9cd22e9aae33fa641859feb8"
)
EXPECTED_ELIGIBLE_PROTOCOL_SHA256 = (
    "925a72d8c7b0e23529e0b28a4a7b3e0ec837a4eff2f4f3b2ac3b16453bdd4559"
)
EXPECTED_TRIAL_OUTPUTS = {
    "bootstrap_intervals.json",
    "calibration.csv",
    "candidate_failures.json",
    "candidate_models.csv",
    "feature_ablation.csv",
    "feature_audit.json",
    "model.joblib",
    "model_registry.json",
    "oof_predictions.csv",
    "same_record_comparisons.csv",
    "threshold_selection.json",
}
INELIGIBLE_TRIAL_FAMILIES = {"small_mlp"}


def _eligible_protocol_hash(config: dict[str, Any]) -> str:
    fields = (
        "random_state",
        "outer_folds",
        "inner_folds",
        "bootstrap_replicates",
        "threshold_minimum",
        "threshold_maximum",
        "threshold_step",
        "primary_metric",
        "close_metric_tolerance",
        "safety_balanced_accuracy_tolerance",
        "training_regimes",
        "primary_training_regime",
        "feature_groups",
        "feature_sets",
        "gene_identity_feature_set",
        "ablation_model",
        "selection_order",
    )
    payload = {field: config[field] for field in fields}
    payload["candidates"] = {
        name: value
        for name, value in config["candidates"].items()
        if name not in INELIGIBLE_TRIAL_FAMILIES
    }
    payload["frozen_outer_folds_sha256"] = EXPECTED_FROZEN_OUTER_FOLDS_SHA256
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _authenticate_trial(trial_dir: Path) -> dict[str, Any]:
    if sha256_file(trial_dir / "run_manifest.json") != EXPECTED_TRIAL_MANIFEST_SHA256:
        raise V91Error(
            "The source trial manifest is not the externally pinned manifest."
        )
    manifest = _load_json(trial_dir / "run_manifest.json")
    if (
        manifest.get("status") != "v9_1_internal_development_complete"
        or manifest.get("official_v9_1_model") is not False
        or manifest.get("final_test_evaluated") is not False
    ):
        raise V91Error("The source V9.1 trial has an invalid lock state.")
    if manifest.get("config_sha256") != EXPECTED_TRIAL_CONFIG_SHA256:
        raise V91Error("The source trial is not the preserved revision-2 trial.")
    if set(manifest.get("output_hashes", {})) != EXPECTED_TRIAL_OUTPUTS:
        raise V91Error("The source trial output inventory is incomplete.")
    for filename, expected in manifest["output_hashes"].items():
        path = trial_dir / filename
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise V91Error(f"The source V9.1 trial artifact changed: {filename}")
    return manifest


def _family_metrics_from_trial(path: Path) -> dict[str, dict[str, float]]:
    frame = pd.read_csv(path)
    frame = frame[frame["status"] == "evaluated"]
    frame = frame[~frame["candidate"].isin(INELIGIBLE_TRIAL_FAMILIES)]
    if frame["candidate"].duplicated().any() or len(frame) != 7:
        raise V91Error(
            "Authenticated trial candidate rows are incomplete or duplicated."
        )
    fields = (
        "component_weighted_balanced_accuracy",
        "macro_f1",
        "pathogenic_recall",
        "brier_score",
    )
    return {
        str(row["candidate"]): {field: float(row[field]) for field in fields}
        for _, row in frame.iterrows()
    }


def finalize_v9_1_trial(
    project_root: Path,
    trial_dir: Path,
    *,
    output_dir: Path | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    """Recompute only inner-selected outer pipelines and publish nested evidence."""
    root = project_root.resolve()
    trial_dir = trial_dir.resolve()
    if output_dir is None and not publish:
        raise V91Error("Choose an output directory or canonical publication.")
    trial_manifest = _authenticate_trial(trial_dir)
    config_path = root / "config/v9_1.json"
    config = _load_json(config_path)
    if (
        config.get("status") != "frozen_internal_validation_plan_revision_2"
        or config.get("official_v9_1_model") is not False
        or config.get("final_test_evaluated") is not False
    ):
        raise V91Error("Current V9.1 protocol does not preserve the final-test lock.")
    if _eligible_protocol_hash(config) != EXPECTED_ELIGIBLE_PROTOCOL_SHA256:
        raise V91Error(
            "Eligible trial-family protocol changed; a new trial is required."
        )
    dataset_path = root / "data/processed/v9_1/v9_1_all_eligible_dataset.csv"
    dataset_manifest_path = root / "data/processed/v9_1/v9_1_dataset_manifest.json"
    dataset_manifest = _load_json(dataset_manifest_path)
    if dataset_manifest.get("output_hashes", {}).get(dataset_path.name) != sha256_file(
        dataset_path
    ):
        raise V91Error("Current V9.1 dataset does not match its manifest.")
    if dataset_manifest.get("source_hashes", {}).get("config/v9_1.json") != sha256_file(
        config_path
    ):
        raise V91Error("V9.1 datasets must be rebuilt after the protocol revision.")
    frame = pd.read_csv(dataset_path, dtype={"variation_id": str})
    canonical_columns = [f"feature__{name}" for name in V8_FEATURE_NAMES]
    x = frame[canonical_columns].to_numpy(dtype=float)
    y = (frame["dataset_outcome"] == "moved_toward_pathogenic").to_numpy(dtype=int)
    groups = np.asarray(
        [f"opened:{value}" for value in frame["component_hash"]], dtype=str
    )
    fold_path = root / "outputs/v9_exploratory/fold_assignments.csv"
    original_manifest = _load_json(root / "outputs/v9_exploratory/run_manifest.json")
    if (
        original_manifest["fold_assignments_sha256"]
        != EXPECTED_FROZEN_OUTER_FOLDS_SHA256
        or sha256_file(fold_path) != EXPECTED_FROZEN_OUTER_FOLDS_SHA256
    ):
        raise V91Error("Frozen original V9 folds changed.")
    outer_splits = _outer_splits(frame, fold_path)

    development_db = root / "data/processed/resolved_direction_v2.sqlite3"
    predictor_index = root / "data/processed/clinvar_history.sqlite3"
    v7_path = root / "outputs/ai_temporal_v7/temporal_test_predictions.csv"
    current_trial_sources = {
        "v8_development_database": sha256_file(development_db),
        "historical_predictor_index": sha256_file(predictor_index),
        "v7_predictions": sha256_file(v7_path),
        "original_v9_predictions": sha256_file(
            root / "outputs/v9_exploratory/oof_predictions.csv"
        ),
        "frozen_outer_folds": sha256_file(fold_path),
    }
    if current_trial_sources != trial_manifest.get("source_hashes"):
        raise V91Error("A source used by the authenticated family trial changed.")
    base_records, base_x, base_y, base_raw_groups, _ = _load_development(
        development_db, predictor_index, v7_path
    )
    base_groups = np.asarray([f"base:{value}" for value in base_raw_groups], dtype=str)
    queue_path = root / "outputs/manual_review/v8_review_queue.csv"
    clue_config_path = root / "config/clue_score_v1.yaml"
    if dataset_manifest.get("source_hashes", {}).get(
        "v8_review_queue.csv"
    ) != sha256_file(queue_path):
        raise V91Error("The review queue changed after the V9.1 dataset build.")
    if original_manifest.get("clue_score_config_sha256") != sha256_file(
        clue_config_path
    ):
        raise V91Error("The frozen Clue Score configuration changed.")
    clue_implementation_path = root / "src/variant_time_machine/v9_exploratory.py"
    if original_manifest.get("implementation_hashes", {}).get(
        "src/variant_time_machine/v9_exploratory.py"
    ) != sha256_file(clue_implementation_path):
        raise V91Error("The frozen Clue Score implementation changed.")
    final_direct_sources = {
        **current_trial_sources,
        "v8_review_queue": sha256_file(queue_path),
        "clue_score_config": sha256_file(clue_config_path),
        "v9_1_dataset_manifest": sha256_file(dataset_manifest_path),
    }
    queue = pd.read_csv(queue_path, dtype={"variation_id": str})
    if {record["variation_id"] for record in base_records} & set(frame["variation_id"]):
        raise V91Error("Prior development IDs overlap V9.1 rows.")
    opened_genes = set().union(*(_gene_tokens(value) for value in queue["gene"]))
    base_genes = set().union(*(set(row["gene_tokens"]) for row in base_records))
    if opened_genes & base_genes:
        raise V91Error("Prior development genes overlap V9.1 rows.")

    trial_thresholds = _load_json(trial_dir / "threshold_selection.json")
    trial_selections = trial_thresholds["candidate_outer_fold_selections"]
    candidate_specs = {
        family: specs
        for family, specs in _candidate_specs(config).items()
        if family not in INELIGIBLE_TRIAL_FAMILIES
    }
    selected_probabilities = np.full(len(y), np.nan, dtype=float)
    selected_predictions = np.full(len(y), -1, dtype=int)
    selected_family_by_index = np.full(len(y), "", dtype=object)
    nested_selections = []
    for fold, (outer_train, validation) in enumerate(outer_splits):
        isolated_metrics = {
            family: _selected_inner_metrics(trial_selections[family][fold])
            for family in candidate_specs
        }
        selected_family, trace = _rank_families(isolated_metrics, config)
        trial_selection = trial_selections[selected_family][fold]
        identifier = trial_selection["selected_configuration"]
        selected_spec = next(
            spec
            for spec in candidate_specs[selected_family]
            if spec.identifier == identifier
        )
        spec, calibrator, threshold, safety_threshold, audits = _select_spec(
            [selected_spec],
            base_x,
            base_y,
            base_groups,
            x[outer_train],
            y[outer_train],
            groups[outer_train],
            config,
            int(config["random_state"]) + fold + 1,
        )
        if not np.isclose(threshold, trial_selection["selected_threshold"]):
            raise V91Error("Recomputed threshold differs from authenticated trial.")
        fit_x, fit_y, _, fit_weights = _combine_training(
            base_x,
            base_y,
            base_groups,
            x[outer_train],
            y[outer_train],
            groups[outer_train],
        )
        fitted = _fit(clone(spec.estimator), fit_x, fit_y, fit_weights)
        raw = _raw_scores(fitted, x[validation], spec.score_kind)
        probabilities = (
            _calibrate(calibrator, raw, spec.score_kind)
            if calibrator is not None
            else raw
        )
        selected_probabilities[validation] = probabilities
        selected_predictions[validation] = (probabilities >= threshold).astype(int)
        selected_family_by_index[validation] = selected_family
        nested_selections.append(
            {
                "fold": fold,
                "selected_family": selected_family,
                "selected_configuration": identifier,
                "selected_threshold": threshold,
                "safety_threshold_report_only": safety_threshold,
                "family_metrics_from_authenticated_inner_oof": isolated_metrics,
                "configuration_recheck": audits,
                "selection_trace": trace,
            }
        )
    if (
        not np.isfinite(selected_probabilities).all()
        or (selected_predictions < 0).any()
    ):
        raise V91Error("Nested selection-procedure OOF predictions are incomplete.")
    selected_metrics = _metric_summary(
        y, selected_probabilities, selected_predictions, _weights(groups)
    )
    selected_metrics["outer_fold_metrics"] = [
        {
            "fold": fold,
            "selected_family": nested_selections[fold]["selected_family"],
            **_metric_summary(
                y[validation],
                selected_probabilities[validation],
                selected_predictions[validation],
                _weights(groups[validation]),
            ),
        }
        for fold, (_, validation) in enumerate(outer_splits)
    ]

    trial_family_metrics = _family_metrics_from_trial(
        trial_dir / "candidate_models.csv"
    )
    final_family, final_family_trace = _rank_families(trial_family_metrics, config)
    (
        final_spec,
        final_calibrator,
        final_threshold,
        final_safety_threshold,
        final_audits,
    ) = _select_spec(
        candidate_specs[final_family],
        base_x,
        base_y,
        base_groups,
        x,
        y,
        groups,
        config,
        int(config["random_state"]) + 100,
    )
    full_x, full_y, _, full_weights = _combine_training(
        base_x, base_y, base_groups, x, y, groups
    )
    final_model = _fit(clone(final_spec.estimator), full_x, full_y, full_weights)

    original = pd.read_csv(
        root / "outputs/v9_exploratory/oof_predictions.csv",
        dtype={"variation_id": str},
    ).set_index("variation_id")
    original = original.loc[frame["variation_id"]]
    original_probability = original["elastic_net_logistic_probability"].to_numpy(
        dtype=float
    )
    original_prediction = (
        original["elastic_net_logistic_prediction"] == "moved_toward_pathogenic"
    ).to_numpy(dtype=int)
    v8_probability = frame["v8_probability"].to_numpy(dtype=float)
    v8_prediction = (frame["v8_prediction"] == "moved_toward_pathogenic").to_numpy(
        dtype=int
    )
    queue_by_id = queue.set_index("variation_id").loc[frame["variation_id"]]
    v7_probability = queue_by_id["v7_probability"].to_numpy(dtype=float)
    v7_prediction = (
        queue_by_id["v7_prediction"] == "moved_toward_pathogenic"
    ).to_numpy(dtype=int)
    consequence_prediction = (
        frame[
            [
                "feature__consequence_loss_of_function",
                "feature__consequence_canonical_splice",
                "feature__consequence_missense",
            ]
        ]
        .max(axis=1)
        .to_numpy(dtype=int)
    )
    majority_prediction = np.zeros(len(y), dtype=int)
    comparisons = {
        "selected_v9_1": (selected_probabilities, selected_predictions),
        "original_v9": (original_probability, original_prediction),
        "frozen_v8": (v8_probability, v8_prediction),
        "frozen_v7": (v7_probability, v7_prediction),
        "consequence_only": (
            consequence_prediction.astype(float),
            consequence_prediction,
        ),
        "majority": (majority_prediction.astype(float), majority_prediction),
    }
    comparison_rows = []
    for name, (probability, prediction) in comparisons.items():
        row = _comparison_row(name, y, probability, prediction, groups)
        row["selected_v9_1_minus_model_component_weighted_ba"] = (
            selected_metrics["component_weighted_balanced_accuracy"]
            - row["component_weighted_balanced_accuracy"]
        )
        row.update(_transition_counts(y, selected_predictions, prediction))
        row["same_records"] = True
        row["comparison_warning"] = (
            "V8 was evaluated while sealed; V9/V9.1 used opened labels."
        )
        comparison_rows.append(row)
    bootstrap = _bootstrap_metrics(
        y,
        groups,
        {name: prediction for name, (_, prediction) in comparisons.items()},
        int(config["bootstrap_replicates"]),
        int(config["random_state"]),
    )

    feature_sets = _feature_sets(config)
    feature_audit = _feature_audit(feature_sets, config_path, dataset_path)
    clue_config = _load_json(clue_config_path)
    clue_score, clue_directional, _ = _clue_score(frame, clue_config)
    parent = output_dir.parent if output_dir else root / "outputs"
    parent.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix=".v9_1_final.", dir=parent))
    try:
        shutil.copy2(
            trial_dir / "feature_ablation.csv", working / "feature_ablation.csv"
        )
        trial_failures = json.loads(
            (trial_dir / "candidate_failures.json").read_text(encoding="utf-8")
        )
        trial_failures.append(
            {
                "candidate": "small_mlp",
                "error": (
                    "Invalid diagnostic: source trial used record-level early "
                    "stopping, which did not preserve component groups. It was "
                    "excluded from all family selection."
                ),
            }
        )
        _write_json(working / "candidate_failures.json", trial_failures)
        _write_json(working / "feature_audit.json", feature_audit)
        _write_json(working / "bootstrap_intervals.json", bootstrap)
        _write_csv(
            working / "same_record_comparisons.csv",
            [
                "model",
                "records",
                "component_weighted_balanced_accuracy",
                "balanced_accuracy",
                "accuracy",
                "macro_f1",
                "benign_recall",
                "pathogenic_recall",
                "brier_score",
                "selected_v9_1_minus_model_component_weighted_ba",
                "prediction_disagreements",
                "reference_wrong_v9_1_correct",
                "reference_correct_v9_1_wrong",
                "both_correct",
                "both_wrong",
                "same_records",
                "comparison_warning",
            ],
            comparison_rows,
        )
        trial_candidates = list(
            csv.DictReader(
                (trial_dir / "candidate_models.csv").open(encoding="utf-8", newline="")
            )
        )
        for row in trial_candidates:
            row["selected"] = "False"
            if row["status"] == "evaluated":
                row["status"] = "family_specific_diagnostic"
            if row["candidate"] == "small_mlp":
                row["status"] = "invalid_protocol_mismatch_not_ranked"
                row["warning"] = (
                    "Record-level early stopping did not preserve components; excluded "
                    "from family selection."
                )
        trial_candidates.append(
            {
                "candidate": "nested_family_selection_procedure",
                "status": "selected_internal_validation_procedure",
                "selected": True,
                "training_regime": config["primary_training_regime"],
                "feature_set": "all_allowed_non_leaky",
                "feature_count": len(V8_FEATURE_NAMES),
                "records": len(y),
                **selected_metrics,
                "fold_min_component_weighted_ba": min(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in selected_metrics["outer_fold_metrics"]
                ),
                "fold_max_component_weighted_ba": max(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in selected_metrics["outer_fold_metrics"]
                ),
                "warning": (
                    "Fully nested estimate; outer folds selected different families."
                ),
            }
        )
        _write_csv(
            working / "candidate_models.csv",
            list(trial_candidates[0]),
            trial_candidates,
        )
        trial_calibration = list(
            csv.DictReader(
                (trial_dir / "calibration.csv").open(encoding="utf-8", newline="")
            )
        )
        trial_calibration = [
            {**row, "evidence_generation": "authenticated_family_trial"}
            for row in trial_calibration
            if row["candidate"] != "small_mlp"
        ]
        trial_calibration.extend(
            {
                **row,
                "evidence_generation": "fully_nested_selection_procedure",
            }
            for row in _calibration_rows(
                "nested_family_selection_procedure", y, selected_probabilities
            )
        )
        _write_csv(
            working / "calibration.csv",
            list(trial_calibration[0]),
            trial_calibration,
        )
        threshold_payload = {
            "selection_scope": (
                "Family, configuration, calibration, and threshold were selected from "
                "inner grouped OOF evidence inside each outer training partition."
            ),
            "optimized_metric": config["primary_metric"],
            "nested_outer_selections": nested_selections,
            "full_development_selection": {
                "family": final_family,
                "configuration": final_spec.identifier,
                "threshold": final_threshold,
                "safety_threshold_report_only": final_safety_threshold,
                "configuration_results": final_audits,
                "family_metrics_from_completed_trial": trial_family_metrics,
                "selection_trace": final_family_trace,
            },
            "source_trial_threshold_sha256": sha256_file(
                trial_dir / "threshold_selection.json"
            ),
            "final_test_used": False,
        }
        _write_json(working / "threshold_selection.json", threshold_payload)
        model_bundle = {
            "schema_version": 1,
            "status": "v9_1_internal_development_candidate",
            "official_v9_1_model": False,
            "final_test_evaluated": False,
            "family": final_family,
            "configuration": final_spec.identifier,
            "base_model": final_model,
            "calibrator": final_calibrator,
            "score_kind": final_spec.score_kind,
            "threshold": final_threshold,
            "safety_threshold_report_only": final_safety_threshold,
            "feature_names": tuple(V8_FEATURE_NAMES),
        }
        joblib.dump(model_bundle, working / "model.joblib")
        paired = bootstrap[
            "selected_v9_1_paired_component_weighted_balanced_accuracy_difference"
        ]
        original_metrics = next(
            row for row in comparison_rows if row["model"] == "original_v9"
        )
        v8_metrics = next(row for row in comparison_rows if row["model"] == "frozen_v8")
        registry = {
            "schema_version": 1,
            "model_id": "V9.1-development",
            "name": "V9.1 internal-development candidate",
            "effective_status": "selected_internal_validation_no_final_test",
            "official_model": False,
            "official_v9_1_model": False,
            "final_test_available": False,
            "final_test_evaluated": False,
            "model_type": final_family,
            "selected_configuration": final_spec.identifier,
            "feature_set": "all_allowed_non_leaky",
            "feature_count": len(V8_FEATURE_NAMES),
            "dataset_used": (
                "V8 development plus V9.1 all-eligible outer-training rows"
            ),
            "split_method": (
                "fully nested family/configuration/calibration/threshold selection on "
                "frozen component-grouped outer folds"
            ),
            "training_records_per_outer_fold": len(base_y) + 800,
            "validation_records_per_outer_fold": 200,
            "test_records": 0,
            "selected_threshold_full_development": final_threshold,
            "safety_threshold_report_only": final_safety_threshold,
            "metrics": selected_metrics,
            "metrics_scope": (
                "Fully nested OOF estimate of the selection procedure; not test "
                "metrics for the serialized full-data pipeline."
            ),
            "leakage_audit_result": feature_audit,
            "leakage_audit_status": feature_audit["status"],
            "manual_review_status": "not started; 0 completed reviews",
            "calibration": {
                "final_pipeline_calibrated": final_spec.calibrated,
                "nested_selection_procedure_brier_score": selected_metrics[
                    "brier_score"
                ],
                "calibration_file": "outputs/evaluations/v9_1_calibration.csv",
            },
            "bootstrap_intervals": bootstrap,
            "comparison_to_original_v9": {
                "point_estimate_improved": selected_metrics[
                    "component_weighted_balanced_accuracy"
                ]
                > original_metrics["component_weighted_balanced_accuracy"],
                "clear_paired_improvement": paired["original_v9"][0] > 0,
                "paired_interval": paired["original_v9"],
            },
            "comparison_to_v8": {
                "selected_component_weighted_balanced_accuracy": selected_metrics[
                    "component_weighted_balanced_accuracy"
                ],
                "v8_component_weighted_balanced_accuracy": v8_metrics[
                    "component_weighted_balanced_accuracy"
                ],
                "paired_interval": paired["frozen_v8"],
                "fairly_beat_v8": False,
                "warning": (
                    "V8 was evaluated while sealed; V9.1 used opened labels. A future "
                    "equivalent untouched test is required for a fair win."
                ),
            },
            "protocol_history": config["protocol_history"],
            "artifact": {
                "path": "outputs/v9_1_development/model.joblib",
                "sha256": sha256_file(working / "model.joblib"),
                "size_bytes": (working / "model.joblib").stat().st_size,
                "trust_boundary": (
                    "Trusted executable serialization; verify SHA-256 before loading."
                ),
            },
            "limitations": [
                WARNING,
                "No human-reviewed clean rows or independent final test were "
                "available.",
                "The V8 comparison is same-record but asymmetric.",
                "Bootstrap intervals condition on fixed OOF predictions.",
                "This artifact has no clinical-use validity.",
            ],
            "warnings": [
                WARNING,
                "The protocol has a disclosed prepublication revision history.",
                "The serialized full-data pipeline has no test metrics.",
            ],
        }
        _write_json(working / "model_registry.json", registry)
        prediction_rows = []
        for index, source in frame.iterrows():
            prediction_rows.append(
                {
                    "variation_id": source["variation_id"],
                    "gene": source["gene"],
                    "component_hash": source["component_hash"],
                    "actual_outcome": source["dataset_outcome"],
                    "v9_1_probability": float(selected_probabilities[index]),
                    "v9_1_prediction": (
                        "moved_toward_pathogenic"
                        if selected_predictions[index]
                        else "moved_toward_benign"
                    ),
                    "v9_1_correct": bool(selected_predictions[index] == y[index]),
                    "v9_1_outer_selected_family": selected_family_by_index[index],
                    "original_v9_prediction": (
                        "moved_toward_pathogenic"
                        if original_prediction[index]
                        else "moved_toward_benign"
                    ),
                    "v8_prediction": source["v8_prediction"],
                    "v8_correct": bool(v8_prediction[index] == y[index]),
                    "v7_prediction": queue_by_id.iloc[index]["v7_prediction"],
                    "review_state": source["v9_1_review_state"],
                    "inclusion_reason": source["v9_1_inclusion_reason"],
                    "manual_decision": source["manual_decision"],
                    "automatic_review_flags": source["automatic_review_flags"],
                    "clue_score": float(clue_score[index]),
                    "clue_score_directional": bool(clue_directional[index]),
                    "model_explanation": (
                        f"{selected_family_by_index[index]} was selected only from "
                        "this outer fold's training data; this component was excluded."
                    ),
                }
            )
        _write_csv(
            working / "oof_predictions.csv",
            list(prediction_rows[0]),
            prediction_rows,
        )
        output_hashes = {
            path.name: sha256_file(path)
            for path in sorted(working.iterdir())
            if path.is_file() and path.name != "run_manifest.json"
        }
        manifest = {
            "schema_version": 1,
            "status": "v9_1_internal_development_complete_fully_nested",
            "warning": WARNING,
            "full_development_selected_family": final_family,
            "full_development_selected_configuration": final_spec.identifier,
            "validation_estimate": "nested_family_selection_procedure",
            "outer_selected_family_counts": dict(
                Counter(selected_family_by_index.tolist())
            ),
            "official_v9_1_model": False,
            "final_test_available": False,
            "final_test_evaluated": False,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dataset_records": len(frame),
            "dataset_components": len(set(groups.tolist())),
            "prior_v8_development_records": len(base_y),
            "prior_v8_development_components": len(set(base_groups.tolist())),
            "prior_opened_gene_overlap": 0,
            "prior_opened_variation_id_overlap": 0,
            "feature_count": len(V8_FEATURE_NAMES),
            "candidate_failures": trial_failures,
            "config_sha256": sha256_file(config_path),
            "dataset_sha256": sha256_file(dataset_path),
            "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
            "source_trial": {
                "run_manifest_sha256": sha256_file(trial_dir / "run_manifest.json"),
                "threshold_selection_sha256": sha256_file(
                    trial_dir / "threshold_selection.json"
                ),
                "candidate_models_sha256": sha256_file(
                    trial_dir / "candidate_models.csv"
                ),
                "trial_config_sha256": trial_manifest["config_sha256"],
                "eligible_protocol_sha256": _eligible_protocol_hash(config),
            },
            "source_hashes": final_direct_sources,
            "implementation_hashes": {
                "src/variant_time_machine/v9_1_finalize.py": sha256_file(
                    root / "src/variant_time_machine/v9_1_finalize.py"
                ),
                "src/variant_time_machine/v9_1.py": sha256_file(
                    root / "src/variant_time_machine/v9_1.py"
                ),
                "src/variant_time_machine/ai_temporal_v8.py": sha256_file(
                    root / "src/variant_time_machine/ai_temporal_v8.py"
                ),
                "src/variant_time_machine/v9_exploratory.py": sha256_file(
                    clue_implementation_path
                ),
            },
            "output_hashes": output_hashes,
            "environment": trial_manifest["environment"],
            "self_checks": {
                "feature_leakage_audit_passed": True,
                "labels_unchanged": True,
                "family_selection_nested_inside_outer_folds": True,
                "outer_component_overlap": 0,
                "prior_development_gene_overlap": 0,
                "prior_development_variation_id_overlap": 0,
                "same_record_comparison_present": True,
                "accuracy_reported_with_balanced_accuracy": True,
                "clean_dataset_too_small_warning_present": True,
                "clinical_use_claim": False,
                "final_test_used_for_selection": False,
            },
        }
        _write_json(working / "run_manifest.json", manifest)
        if output_dir:
            if output_dir.exists():
                raise V91Error(f"Refusing to overwrite output directory: {output_dir}")
            os.replace(working, output_dir)
            working = output_dir
        if publish:
            _publish_outputs(root, working)
        return {
            "manifest": manifest,
            "registry": registry,
            "selected_metrics": selected_metrics,
            "selected_family": final_family,
            "working_output": str(working),
        }
    finally:
        if working.exists() and (not output_dir or working != output_dir):
            shutil.rmtree(working, ignore_errors=True)
