"""Leakage-controlled V9.1 internal development on opened V8 records."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from variant_time_machine.ai_temporal_v8 import (
    V8_FEATURE_NAMES,
    _gene_tokens,
    _load_development,
)
from variant_time_machine.v8_presentation import sha256_file
from variant_time_machine.v9_exploratory import (
    _calibration_rows,
    _clue_score,
    _metric_summary,
    _weighted_balanced_accuracy,
    _weights,
)

WARNING = (
    "Internal nested grouped validation on previously opened V8 records. Not an "
    "official or final V9.1 evaluation."
)
FORBIDDEN_FEATURE_TERMS = {
    "actual",
    "answer",
    "correct",
    "later",
    "manual",
    "newer",
    "outcome",
    "prediction",
    "resolved",
    "target",
}
INTERPRETABILITY = {
    "elastic_net_logistic": 0,
    "calibrated_elastic_net_logistic": 0,
    "linear_svm": 1,
    "hist_gradient_boosting": 2,
    "calibrated_hist_gradient_boosting": 2,
    "random_forest": 3,
    "extra_trees": 3,
    "small_mlp": 4,
}


class V91Error(ValueError):
    """Raised when V9.1 development violates its frozen protocol."""


@dataclass(frozen=True)
class CandidateSpec:
    """One frozen estimator configuration within a candidate family."""

    identifier: str
    estimator: Any
    calibrated: bool
    score_kind: str = "probability"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V91Error(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _fit(estimator: Any, x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> Any:
    if isinstance(estimator, Pipeline):
        return estimator.fit(x, y, model__sample_weight=weights)
    return estimator.fit(x, y, sample_weight=weights)


def _raw_scores(estimator: Any, x: np.ndarray, score_kind: str) -> np.ndarray:
    if score_kind == "decision":
        return np.asarray(estimator.decision_function(x), dtype=float)
    return np.asarray(estimator.predict_proba(x)[:, 1], dtype=float)


def _platt(
    raw: np.ndarray, targets: np.ndarray, weights: np.ndarray, score_kind: str
) -> LogisticRegression:
    transformed = raw
    if score_kind == "probability":
        clipped = np.clip(raw, 1e-6, 1 - 1e-6)
        transformed = np.log(clipped / (1 - clipped))
    return LogisticRegression(C=1_000_000, max_iter=3000).fit(
        transformed.reshape(-1, 1), targets, sample_weight=weights
    )


def _calibrate(
    calibrator: LogisticRegression, raw: np.ndarray, score_kind: str
) -> np.ndarray:
    transformed = raw
    if score_kind == "probability":
        clipped = np.clip(raw, 1e-6, 1 - 1e-6)
        transformed = np.log(clipped / (1 - clipped))
    return calibrator.predict_proba(transformed.reshape(-1, 1))[:, 1]


def _thresholds(
    targets: np.ndarray,
    probabilities: np.ndarray,
    groups: np.ndarray,
    config: dict[str, Any],
) -> tuple[float, float, float]:
    weights = _weights(groups)
    values = np.arange(
        float(config["threshold_minimum"]),
        float(config["threshold_maximum"]) + float(config["threshold_step"]) / 2,
        float(config["threshold_step"]),
    )
    scored = [
        (
            value,
            _weighted_balanced_accuracy(targets, probabilities >= value, weights),
            float((weights[(targets == 1) & (probabilities >= value)]).sum())
            / float(weights[targets == 1].sum()),
        )
        for value in values
    ]
    best_score = max(item[1] for item in scored)
    primary = min(
        (item for item in scored if math.isclose(item[1], best_score)),
        key=lambda item: (abs(item[0] - 0.5), item[0]),
    )[0]
    safety_floor = best_score - float(config["safety_balanced_accuracy_tolerance"])
    safety = min(
        (item for item in scored if item[1] >= safety_floor),
        key=lambda item: (-item[2], -item[1], abs(item[0] - 0.5), item[0]),
    )[0]
    return float(primary), float(safety), float(best_score)


def _combine_training(
    base_x: np.ndarray,
    base_y: np.ndarray,
    base_groups: np.ndarray,
    opened_x: np.ndarray,
    opened_y: np.ndarray,
    opened_groups: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(base_y):
        x = np.vstack((base_x, opened_x))
        y = np.concatenate((base_y, opened_y))
        groups = np.concatenate((base_groups, opened_groups))
    else:
        x, y, groups = opened_x, opened_y, opened_groups
    return x, y, groups, _weights(groups)


def _inner_oof(
    spec: CandidateSpec,
    base_x: np.ndarray,
    base_y: np.ndarray,
    base_groups: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    folds: int,
    seed: int,
) -> np.ndarray:
    values = np.full(len(y), np.nan, dtype=float)
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train, validation in splitter.split(x, y, groups):
        if set(groups[train]) & set(groups[validation]):
            raise V91Error("A component crossed an inner fold.")
        fit_x, fit_y, _, fit_weights = _combine_training(
            base_x,
            base_y,
            base_groups,
            x[train],
            y[train],
            groups[train],
        )
        fitted = _fit(clone(spec.estimator), fit_x, fit_y, fit_weights)
        values[validation] = _raw_scores(fitted, x[validation], spec.score_kind)
    if not np.isfinite(values).all():
        raise V91Error("Inner grouped predictions are incomplete.")
    return values


def _select_spec(
    specs: list[CandidateSpec],
    base_x: np.ndarray,
    base_y: np.ndarray,
    base_groups: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    config: dict[str, Any],
    seed: int,
) -> tuple[
    CandidateSpec, LogisticRegression | None, float, float, list[dict[str, Any]]
]:
    results = []
    weights = _weights(groups)
    for spec in specs:
        raw = _inner_oof(
            spec,
            base_x,
            base_y,
            base_groups,
            x,
            y,
            groups,
            int(config["inner_folds"]),
            seed,
        )
        calibrator = (
            _platt(raw, y, weights, spec.score_kind) if spec.calibrated else None
        )
        probabilities = (
            _calibrate(calibrator, raw, spec.score_kind)
            if calibrator is not None
            else raw
        )
        threshold, safety_threshold, _ = _thresholds(y, probabilities, groups, config)
        summary = _metric_summary(y, probabilities, probabilities >= threshold, weights)
        results.append(
            {
                "spec": spec,
                "calibrator": calibrator,
                "threshold": threshold,
                "safety_threshold": safety_threshold,
                "metrics": summary,
            }
        )
    best_primary = max(
        item["metrics"]["component_weighted_balanced_accuracy"] for item in results
    )
    close = [
        item
        for item in results
        if item["metrics"]["component_weighted_balanced_accuracy"]
        >= best_primary - float(config["close_metric_tolerance"])
    ]
    selected = min(
        close,
        key=lambda item: (
            -item["metrics"]["macro_f1"],
            -item["metrics"]["pathogenic_recall"],
            item["metrics"]["brier_score"],
            item["spec"].identifier,
        ),
    )
    audit_rows = [
        {
            "configuration": item["spec"].identifier,
            "threshold": item["threshold"],
            "safety_threshold": item["safety_threshold"],
            **{
                key: item["metrics"][key]
                for key in (
                    "component_weighted_balanced_accuracy",
                    "balanced_accuracy",
                    "macro_f1",
                    "pathogenic_recall",
                    "benign_recall",
                    "brier_score",
                )
            },
        }
        for item in results
    ]
    return (
        selected["spec"],
        selected["calibrator"],
        selected["threshold"],
        selected["safety_threshold"],
        audit_rows,
    )


def _nested_candidate(
    specs: list[CandidateSpec],
    base_x: np.ndarray,
    base_y: np.ndarray,
    base_groups: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    outer_splits: list[tuple[np.ndarray, np.ndarray]],
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    probabilities = np.full(len(y), np.nan, dtype=float)
    predictions = np.full(len(y), -1, dtype=int)
    selections = []
    for fold, (outer_train, outer_validation) in enumerate(outer_splits):
        selected, calibrator, threshold, safety_threshold, audits = _select_spec(
            specs,
            base_x,
            base_y,
            base_groups,
            x[outer_train],
            y[outer_train],
            groups[outer_train],
            config,
            int(config["random_state"]) + fold + 1,
        )
        fit_x, fit_y, _, fit_weights = _combine_training(
            base_x,
            base_y,
            base_groups,
            x[outer_train],
            y[outer_train],
            groups[outer_train],
        )
        fitted = _fit(clone(selected.estimator), fit_x, fit_y, fit_weights)
        raw = _raw_scores(fitted, x[outer_validation], selected.score_kind)
        fold_probabilities = (
            _calibrate(calibrator, raw, selected.score_kind)
            if calibrator is not None
            else raw
        )
        probabilities[outer_validation] = fold_probabilities
        predictions[outer_validation] = (fold_probabilities >= threshold).astype(int)
        selections.append(
            {
                "fold": fold,
                "selected_configuration": selected.identifier,
                "selected_threshold": threshold,
                "safety_threshold": safety_threshold,
                "inner_configuration_results": audits,
            }
        )
    if not np.isfinite(probabilities).all() or (predictions < 0).any():
        raise V91Error("Outer grouped predictions are incomplete.")
    return probabilities, predictions, selections


def _pipeline(model: Any) -> Pipeline:
    return Pipeline((("scale", StandardScaler()), ("model", model)))


def _candidate_specs(config: dict[str, Any]) -> dict[str, list[CandidateSpec]]:
    seed = int(config["random_state"])
    values: dict[str, list[CandidateSpec]] = {}
    logistic = config["candidates"]["elastic_net"]
    for calibrated in logistic["calibrated"]:
        family = (
            "calibrated_elastic_net_logistic" if calibrated else "elastic_net_logistic"
        )
        values[family] = []
        for item in logistic["configurations"]:
            c_value = float(item["C"])
            ratio = float(item["l1_ratio"])
            class_weight = item["class_weight"]
            weight_name = "none" if class_weight is None else "balanced"
            identifier = f"C_{c_value:g}_l1_{ratio:g}_class_{weight_name}"
            model = (
                LogisticRegression(
                    C=c_value,
                    solver="lbfgs",
                    class_weight=class_weight,
                    max_iter=2000,
                    random_state=seed,
                )
                if ratio == 0
                else LogisticRegression(
                    C=c_value,
                    l1_ratio=ratio,
                    penalty="elasticnet",
                    solver="saga",
                    class_weight=class_weight,
                    max_iter=3000,
                    random_state=seed,
                )
            )
            values[family].append(
                CandidateSpec(
                    identifier,
                    _pipeline(model),
                    calibrated=bool(calibrated),
                )
            )
    hist = config["candidates"]["hist_gradient_boosting"]
    for calibrated in hist["calibrated"]:
        family = (
            "calibrated_hist_gradient_boosting"
            if calibrated
            else "hist_gradient_boosting"
        )
        values[family] = [
            CandidateSpec(
                f"leaf_{item['max_leaf_nodes']}_l2_{item['l2_regularization']:g}_min_{item['min_samples_leaf']}",
                HistGradientBoostingClassifier(
                    max_leaf_nodes=int(item["max_leaf_nodes"]),
                    learning_rate=float(item["learning_rate"]),
                    l2_regularization=float(item["l2_regularization"]),
                    min_samples_leaf=int(item["min_samples_leaf"]),
                    max_iter=int(hist["max_iter"]),
                    random_state=seed,
                ),
                calibrated=bool(calibrated),
            )
            for item in hist["configurations"]
        ]
    for family, estimator_type in (
        ("random_forest", RandomForestClassifier),
        ("extra_trees", ExtraTreesClassifier),
    ):
        values[family] = []
        options = config["candidates"][family]
        for item in options["configurations"]:
            class_weight = item["class_weight"]
            weight_name = "none" if class_weight is None else "balanced"
            values[family].append(
                CandidateSpec(
                    f"depth_{item['max_depth']}_min_{item['min_samples_leaf']}_class_{weight_name}",
                    estimator_type(
                        n_estimators=int(options["n_estimators"]),
                        max_depth=item["max_depth"],
                        min_samples_leaf=int(item["min_samples_leaf"]),
                        max_features="sqrt",
                        class_weight=class_weight,
                        random_state=seed,
                        n_jobs=-1,
                    ),
                    calibrated=False,
                )
            )
    svm = config["candidates"]["linear_svm"]
    values["linear_svm"] = [
        CandidateSpec(
            f"C_{c_value:g}_class_{'none' if weight is None else 'balanced'}",
            _pipeline(
                LinearSVC(
                    C=float(c_value),
                    class_weight=weight,
                    dual="auto",
                    max_iter=5000,
                    random_state=seed,
                )
            ),
            calibrated=True,
            score_kind="decision",
        )
        for c_value in svm["C"]
        for weight in svm["class_weight"]
    ]
    mlp = config["candidates"]["small_mlp"]
    values["small_mlp"] = [
        CandidateSpec(
            f"layers_{'_'.join(map(str, layers))}_alpha_{alpha:g}",
            _pipeline(
                MLPClassifier(
                    hidden_layer_sizes=tuple(layers),
                    alpha=float(alpha),
                    early_stopping=bool(mlp["early_stopping"]),
                    max_iter=int(mlp["max_iter"]),
                    random_state=seed,
                )
            ),
            calibrated=False,
        )
        for layers in mlp["hidden_layer_sizes"]
        for alpha in mlp["alpha"]
    ]
    return values


def _rank_families(
    metrics: dict[str, dict[str, Any]], config: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Apply the frozen family rule to metrics from training-isolated predictions."""
    best_primary = max(
        summary["component_weighted_balanced_accuracy"] for summary in metrics.values()
    )
    close = [
        family
        for family, summary in metrics.items()
        if summary["component_weighted_balanced_accuracy"]
        >= best_primary - float(config["close_metric_tolerance"])
    ]
    selected = min(
        close,
        key=lambda family: (
            -metrics[family]["macro_f1"],
            -metrics[family]["pathogenic_recall"],
            metrics[family]["brier_score"],
            metrics[family].get("stability_penalty", 0.0),
            INTERPRETABILITY[family],
            family,
        ),
    )
    return selected, {
        "best_primary": best_primary,
        "close_families": close,
        "selected_family": selected,
        "selection_reached_stability_tie_break": False,
        "selection_reached_simplicity_tie_break": False,
    }


def _selected_inner_metrics(selection: dict[str, Any]) -> dict[str, Any]:
    identifier = selection["selected_configuration"]
    return next(
        row
        for row in selection["inner_configuration_results"]
        if row["configuration"] == identifier
    )


def _feature_sets(config: dict[str, Any]) -> dict[str, list[str]]:
    groups = config["feature_groups"]
    canonical = list(V8_FEATURE_NAMES)
    if set().union(*(set(values) for values in groups.values())) != set(canonical):
        raise V91Error("Frozen V9.1 feature groups do not equal the V8 feature schema.")
    result = {}
    for name, group_names in config["feature_sets"].items():
        selected = set().union(*(set(groups[group]) for group in group_names))
        result[name] = [feature for feature in canonical if feature in selected]
    return result


def _outer_splits(
    frame: pd.DataFrame, fold_path: Path
) -> list[tuple[np.ndarray, np.ndarray]]:
    folds = pd.read_csv(fold_path, dtype={"variation_id": str})
    by_id = dict(zip(folds["variation_id"], folds["outer_fold"], strict=True))
    assignment = frame["variation_id"].map(by_id).to_numpy(dtype=int)
    if len(by_id) != len(frame) or np.any(assignment < 0):
        raise V91Error("Frozen outer fold assignments are incomplete.")
    groups = frame["component_hash"].to_numpy(dtype=str)
    result = []
    for fold in sorted(set(assignment.tolist())):
        validation = np.flatnonzero(assignment == fold)
        train = np.flatnonzero(assignment != fold)
        if set(groups[train]) & set(groups[validation]):
            raise V91Error("A component crossed a frozen outer fold.")
        result.append((train, validation))
    if len(result) != 5 or any(len(validation) != 200 for _, validation in result):
        raise V91Error("Frozen outer fold accounting changed.")
    return result


def _bootstrap_metrics(
    targets: np.ndarray,
    groups: np.ndarray,
    predictions: dict[str, np.ndarray],
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    unique_groups = np.asarray(sorted(set(groups.tolist())))
    by_group = {group: np.flatnonzero(groups == group) for group in unique_groups}
    rng = np.random.default_rng(seed)
    names = tuple(predictions)
    metric_names = (
        "accuracy",
        "component_weighted_balanced_accuracy",
        "macro_f1",
        "benign_recall",
        "pathogenic_recall",
    )
    values = {name: {metric: [] for metric in metric_names} for name in names}
    differences = {reference: [] for reference in names if reference != "selected_v9_1"}
    skipped = 0
    for _ in range(replicates):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([by_group[group] for group in sampled])
        draw_groups = np.concatenate(
            [
                np.full(len(by_group[group]), draw_index)
                for draw_index, group in enumerate(sampled)
            ]
        )
        y = targets[indices]
        if len(set(y.tolist())) < 2:
            skipped += 1
            continue
        weights = _weights(draw_groups)
        scores = {}
        for name, prediction in predictions.items():
            predicted = prediction[indices]
            benign = y == 0
            pathogenic = y == 1
            summary = {
                "accuracy": float(accuracy_score(y, predicted)),
                "component_weighted_balanced_accuracy": (
                    _weighted_balanced_accuracy(y, predicted, weights)
                ),
                "macro_f1": float(f1_score(y, predicted, average="macro")),
                "benign_recall": float((predicted[benign] == 0).mean()),
                "pathogenic_recall": float((predicted[pathogenic] == 1).mean()),
            }
            scores[name] = summary
            for metric, score in summary.items():
                values[name][metric].append(score)
        for reference in differences:
            differences[reference].append(
                scores["selected_v9_1"]["component_weighted_balanced_accuracy"]
                - scores[reference]["component_weighted_balanced_accuracy"]
            )

    def interval(items: list[float]) -> list[float]:
        return [float(np.percentile(items, 2.5)), float(np.percentile(items, 97.5))]

    return {
        "replicates_requested": replicates,
        "replicates_used": replicates - skipped,
        "replicates_skipped": skipped,
        "intervals_95_percent": {
            name: {metric: interval(items) for metric, items in metrics.items()}
            for name, metrics in values.items()
        },
        "selected_v9_1_paired_component_weighted_balanced_accuracy_difference": {
            name: interval(items) for name, items in differences.items()
        },
        "warning": (
            "Component bootstrap conditions on fixed OOF predictions and omits full "
            "feature, candidate, calibration, and threshold selection uncertainty."
        ),
    }


def _comparison_row(
    name: str,
    targets: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    groups: np.ndarray,
) -> dict[str, Any]:
    return {
        "model": name,
        **_metric_summary(targets, probabilities, predictions, _weights(groups)),
    }


def _transition_counts(
    targets: np.ndarray, selected: np.ndarray, reference: np.ndarray
) -> dict[str, int]:
    selected_correct = selected == targets
    reference_correct = reference == targets
    return {
        "prediction_disagreements": int((selected != reference).sum()),
        "reference_wrong_v9_1_correct": int(
            ((~reference_correct) & selected_correct).sum()
        ),
        "reference_correct_v9_1_wrong": int(
            (reference_correct & (~selected_correct)).sum()
        ),
        "both_correct": int((reference_correct & selected_correct).sum()),
        "both_wrong": int(((~reference_correct) & (~selected_correct)).sum()),
    }


def _feature_audit(
    feature_sets: dict[str, list[str]], config_path: Path, dataset_path: Path
) -> dict[str, Any]:
    group_by_feature = {
        feature: group
        for group, values in _load_json(config_path)["feature_groups"].items()
        for feature in values
    }
    entries = []
    findings = []
    for feature in V8_FEATURE_NAMES:
        matched = sorted(term for term in FORBIDDEN_FEATURE_TERMS if term in feature)
        if matched:
            findings.append({"feature": feature, "terms": matched})
        entries.append(
            {
                "feature": f"feature__{feature}",
                "group": group_by_feature[feature],
                "source_snapshot": "2022-01-06 or 2024-01-04 predictor row",
                "lineage": "frozen V8 feature transformer",
                "allowed": not matched,
            }
        )
    return {
        "schema_version": 1,
        "status": "pass" if not findings else "fail",
        "dataset_sha256": sha256_file(dataset_path),
        "config_sha256": sha256_file(config_path),
        "feature_count": len(entries),
        "features": entries,
        "feature_sets": feature_sets,
        "forbidden_name_findings": findings,
        "forbidden_audit_columns": [
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
        ],
        "gene_identity": "ineligible_not_fit",
        "manual_review_features": 0,
        "future_or_newer_features": 0,
        "warning": (
            "Name and allowlist audit passed; source hashes and frozen transformer "
            "lineage provide the date/provenance control."
        ),
    }


def _publish_outputs(root: Path, working: Path) -> None:
    canonical = root / "outputs/v9_1_development"
    if canonical.exists():
        raise V91Error(f"Refusing to overwrite canonical V9.1 bundle: {canonical}")
    staging = canonical.with_name(f".{canonical.name}.tmp")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(working, staging)
    os.replace(staging, canonical)
    evaluation_dir = root / "outputs/evaluations"
    audit_dir = root / "outputs/leakage_audits"
    model_dir = root / "outputs/models"
    registry_dir = root / "outputs/model_registry"
    for directory in (evaluation_dir, audit_dir, model_dir, registry_dir):
        directory.mkdir(parents=True, exist_ok=True)
    mappings = {
        "feature_ablation.csv": evaluation_dir / "v9_1_feature_ablation.csv",
        "candidate_models.csv": evaluation_dir / "v9_1_candidate_models.csv",
        "threshold_selection.json": evaluation_dir / "v9_1_threshold_selection.json",
        "calibration.csv": evaluation_dir / "v9_1_calibration.csv",
        "bootstrap_intervals.json": evaluation_dir / "v9_1_bootstrap_intervals.json",
        "same_record_comparisons.csv": evaluation_dir
        / "v9_1_same_record_comparisons.csv",
        "oof_predictions.csv": evaluation_dir / "v9_1_oof_predictions.csv",
        "candidate_failures.json": evaluation_dir / "v9_1_candidate_failures.json",
        "run_manifest.json": evaluation_dir / "v9_1_run_manifest.json",
        "feature_audit.json": audit_dir / "v9_1_feature_audit.json",
        "model.joblib": model_dir / "v9_1_development.joblib",
        "model_registry.json": registry_dir / "model_v9_1.json",
    }
    for source, destination in mappings.items():
        temporary = destination.with_name(f".{destination.name}.tmp")
        shutil.copy2(canonical / source, temporary)
        os.replace(temporary, destination)


def run_v9_1_development(
    project_root: Path, *, output_dir: Path | None = None, publish: bool = False
) -> dict[str, Any]:
    """Run preregistered V9.1 internal development; never evaluate a final test."""
    root = project_root.resolve()
    if output_dir is None and not publish:
        raise V91Error(
            "Choose --output-dir for a trial or --publish for canonical output."
        )
    config_path = root / "config/v9_1.json"
    config = _load_json(config_path)
    if (
        config.get("status") != "frozen_internal_validation_plan_revision_2"
        or config.get("official_v9_1_model") is not False
        or config.get("final_test_available") is not False
        or config.get("final_test_evaluated") is not False
    ):
        raise V91Error("V9.1 configuration does not preserve the final-test lock.")
    dataset_path = root / "data/processed/v9_1/v9_1_all_eligible_dataset.csv"
    dataset_manifest_path = root / "data/processed/v9_1/v9_1_dataset_manifest.json"
    dataset_manifest = _load_json(dataset_manifest_path)
    if (
        dataset_manifest.get("status") != "internal_development_only_review_gate_failed"
        or dataset_manifest.get("official_model_selection_allowed") is not False
        or dataset_manifest.get("final_test_allowed") is not False
    ):
        raise V91Error("V9.1 dataset manifest does not preserve the official lock.")
    if dataset_manifest.get("source_hashes", {}).get("config/v9_1.json") != sha256_file(
        config_path
    ):
        raise V91Error("V9.1 dataset manifest is stale after the plan changed.")
    dataset_source_paths = {
        "v9_messy_dataset.csv": root / "data/processed/v9/v9_messy_dataset.csv",
        "v9_dataset_manifest.json": root / "data/processed/v9/v9_dataset_manifest.json",
        "v8_review_queue.csv": root / "outputs/manual_review/v8_review_queue.csv",
        "v8_review_notes.json": root / "outputs/manual_review/v8_review_notes.json",
    }
    for name, path in dataset_source_paths.items():
        if dataset_manifest.get("source_hashes", {}).get(name) != sha256_file(path):
            raise V91Error(f"V9.1 dataset source changed after build: {name}")
    for relative, expected in dataset_manifest.get("implementation_hashes", {}).items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise V91Error(f"V9.1 dataset implementation changed: {relative}")
    expected_hash = dataset_manifest.get("output_hashes", {}).get(dataset_path.name)
    if expected_hash != sha256_file(dataset_path):
        raise V91Error("V9.1 all-eligible data do not match the dataset manifest.")
    frame = pd.read_csv(dataset_path, dtype={"variation_id": str})
    if (
        len(frame) != 1000
        or frame["variation_id"].nunique() != 1000
        or frame["component_hash"].nunique() != 559
    ):
        raise V91Error("V9.1 all-eligible accounting changed.")
    if not (frame["dataset_outcome"] == frame["original_automatic_outcome"]).all():
        raise V91Error("V9.1 source labels changed without completed review.")
    feature_sets = _feature_sets(config)
    expected_columns = {f"feature__{feature}" for feature in V8_FEATURE_NAMES}
    declared_columns = set(dataset_manifest["feature_columns"])
    if declared_columns != expected_columns:
        raise V91Error("V9.1 feature allowlist differs from frozen V8 features.")
    canonical_columns = [f"feature__{feature}" for feature in V8_FEATURE_NAMES]
    x = frame[canonical_columns].to_numpy(dtype=float)
    if not np.isfinite(x).all():
        raise V91Error("V9.1 features contain missing or non-finite values.")
    y = (frame["dataset_outcome"] == "moved_toward_pathogenic").to_numpy(dtype=int)
    groups = np.asarray(
        [f"opened:{value}" for value in frame["component_hash"]], dtype=str
    )
    fold_path = root / "outputs/v9_exploratory/fold_assignments.csv"
    original_manifest = _load_json(root / "outputs/v9_exploratory/run_manifest.json")
    if original_manifest.get("fold_assignments_sha256") != sha256_file(fold_path):
        raise V91Error("Frozen original V9 outer folds changed.")
    outer_splits = _outer_splits(frame, fold_path)

    development_db = root / "data/processed/resolved_direction_v2.sqlite3"
    predictor_index = root / "data/processed/clinvar_history.sqlite3"
    v7_path = root / "outputs/ai_temporal_v7/temporal_test_predictions.csv"
    base_records, base_x, base_y, base_raw_groups, _ = _load_development(
        development_db, predictor_index, v7_path
    )
    if len(base_y) != 9818 or len(set(base_raw_groups.tolist())) != 1792:
        raise V91Error("Authenticated V8 development accounting changed.")
    queue = pd.read_csv(
        root / "outputs/manual_review/v8_review_queue.csv",
        dtype={"variation_id": str},
    )
    opened_gene_tokens = set().union(*(_gene_tokens(value) for value in queue["gene"]))
    base_gene_tokens = set().union(
        *(set(record["gene_tokens"]) for record in base_records)
    )
    if opened_gene_tokens & base_gene_tokens:
        raise V91Error("Prior V8 development genes overlap the opened V9 cohort.")
    if {record["variation_id"] for record in base_records} & set(frame["variation_id"]):
        raise V91Error("Prior V8 development Variation IDs overlap V9.1 rows.")
    base_groups = np.asarray([f"base:{value}" for value in base_raw_groups], dtype=str)
    empty_x = np.empty((0, x.shape[1]), dtype=float)
    empty_y = np.empty(0, dtype=int)
    empty_groups = np.empty(0, dtype=str)
    feature_audit = _feature_audit(feature_sets, config_path, dataset_path)
    if feature_audit["status"] != "pass":
        raise V91Error("V9.1 feature leakage audit failed.")

    parent = output_dir.parent if output_dir else root / "outputs"
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".v9_1.", dir=parent))
    failures: list[dict[str, str]] = []
    try:
        _write_json(temporary / "feature_audit.json", feature_audit)
        canonical_index = {name: index for index, name in enumerate(V8_FEATURE_NAMES)}

        ablation_rows = []
        ablation_outputs: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        fixed_spec = CandidateSpec(
            "C_0.1_l1_0_class_none_calibrated",
            _pipeline(
                LogisticRegression(
                    C=0.1,
                    solver="lbfgs",
                    max_iter=2000,
                    random_state=int(config["random_state"]),
                )
            ),
            calibrated=True,
        )
        for feature_set, names in feature_sets.items():
            if feature_set == "all_allowed_without_gene":
                probabilities, predictions = ablation_outputs["all_allowed_non_leaky"]
                warning = (
                    "Identical to all_allowed_non_leaky; gene identity is forbidden."
                )
            else:
                indices = [canonical_index[name] for name in names]
                probabilities, predictions, _ = _nested_candidate(
                    [fixed_spec],
                    base_x[:, indices],
                    base_y,
                    base_groups,
                    x[:, indices],
                    y,
                    groups,
                    outer_splits,
                    config,
                )
                ablation_outputs[feature_set] = (probabilities, predictions)
                warning = ""
            summary = _metric_summary(y, probabilities, predictions, _weights(groups))
            ablation_rows.append(
                {
                    "feature_set": feature_set,
                    "status": "evaluated",
                    "feature_count": len(names),
                    "training_regime": config["primary_training_regime"],
                    "warning": warning,
                    **summary,
                }
            )
        ablation_rows.append(
            {
                "feature_set": "all_allowed_with_gene_identity",
                "status": "ineligible_not_fit",
                "feature_count": "",
                "training_regime": "not_fit",
                "warning": config["gene_identity_feature_set"]["reason"],
            }
        )
        _write_csv(
            temporary / "feature_ablation.csv",
            [
                "feature_set",
                "status",
                "feature_count",
                "training_regime",
                "component_weighted_balanced_accuracy",
                "balanced_accuracy",
                "accuracy",
                "macro_f1",
                "pathogenic_recall",
                "benign_recall",
                "brier_score",
                "warning",
            ],
            ablation_rows,
        )

        all_indices = [
            canonical_index[name] for name in feature_sets["all_allowed_non_leaky"]
        ]
        opened_probabilities, opened_predictions, opened_selections = _nested_candidate(
            [fixed_spec],
            empty_x[:, all_indices],
            empty_y,
            empty_groups,
            x[:, all_indices],
            y,
            groups,
            outer_splits,
            config,
        )
        regime_metrics = {
            "opened_v9_only": _metric_summary(
                y, opened_probabilities, opened_predictions, _weights(groups)
            ),
            config["primary_training_regime"]: _metric_summary(
                y,
                *ablation_outputs["all_allowed_non_leaky"],
                _weights(groups),
            ),
        }

        candidate_specs = _candidate_specs(config)
        candidate_probabilities: dict[str, np.ndarray] = {}
        candidate_predictions: dict[str, np.ndarray] = {}
        candidate_selections: dict[str, Any] = {
            "training_regime_diagnostic": {
                "opened_v9_only": opened_selections,
                config["primary_training_regime"]: "see all candidate folds",
            }
        }
        for family, specs in candidate_specs.items():
            try:
                probabilities, predictions, selections = _nested_candidate(
                    specs,
                    base_x,
                    base_y,
                    base_groups,
                    x,
                    y,
                    groups,
                    outer_splits,
                    config,
                )
                candidate_probabilities[family] = probabilities
                candidate_predictions[family] = predictions
                candidate_selections[family] = selections
            except (ValueError, RuntimeError, FloatingPointError, TypeError) as exc:
                failures.append({"candidate": family, "error": str(exc)})
        if not candidate_predictions:
            raise V91Error("Every learned V9.1 candidate failed.")
        candidate_metrics = {
            family: _metric_summary(
                y, candidate_probabilities[family], predictions, _weights(groups)
            )
            for family, predictions in candidate_predictions.items()
        }
        for family, summary in candidate_metrics.items():
            summary["outer_fold_metrics"] = [
                {
                    "fold": fold,
                    **_metric_summary(
                        y[validation],
                        candidate_probabilities[family][validation],
                        candidate_predictions[family][validation],
                        _weights(groups[validation]),
                    ),
                }
                for fold, (_, validation) in enumerate(outer_splits)
            ]
        selected_probabilities = np.full(len(y), np.nan, dtype=float)
        selected_predictions = np.full(len(y), -1, dtype=int)
        selected_family_by_index = np.full(len(y), "", dtype=object)
        outer_family_selections = []
        for fold, (_, validation) in enumerate(outer_splits):
            isolated_metrics = {
                family: _selected_inner_metrics(candidate_selections[family][fold])
                for family in candidate_predictions
            }
            selected_fold_family, trace = _rank_families(isolated_metrics, config)
            selected_probabilities[validation] = candidate_probabilities[
                selected_fold_family
            ][validation]
            selected_predictions[validation] = candidate_predictions[
                selected_fold_family
            ][validation]
            selected_family_by_index[validation] = selected_fold_family
            outer_family_selections.append(
                {
                    "fold": fold,
                    "selected_family": selected_fold_family,
                    "family_metrics_from_inner_oof": isolated_metrics,
                    "selection_trace": trace,
                }
            )
        if (
            not np.isfinite(selected_probabilities).all()
            or (selected_predictions < 0).any()
            or (selected_family_by_index == "").any()
        ):
            raise V91Error("Nested family-selection predictions are incomplete.")
        selected_metrics = _metric_summary(
            y, selected_probabilities, selected_predictions, _weights(groups)
        )
        selected_metrics["outer_fold_metrics"] = [
            {
                "fold": fold,
                "selected_family": outer_family_selections[fold]["selected_family"],
                **_metric_summary(
                    y[validation],
                    selected_probabilities[validation],
                    selected_predictions[validation],
                    _weights(groups[validation]),
                ),
            }
            for fold, (_, validation) in enumerate(outer_splits)
        ]
        candidate_selections["nested_outer_family_selection"] = outer_family_selections

        consequence_predictions = (
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
        majority_predictions = np.zeros(len(y), dtype=int)
        frozen_v8_predictions = (
            frame["v8_prediction"] == "moved_toward_pathogenic"
        ).to_numpy(dtype=int)
        frozen_v8_probabilities = frame["v8_probability"].to_numpy(dtype=float)
        original = pd.read_csv(
            root / "outputs/v9_exploratory/oof_predictions.csv",
            dtype={"variation_id": str},
        ).set_index("variation_id")
        original = original.loc[frame["variation_id"]]
        original_probabilities = original["elastic_net_logistic_probability"].to_numpy(
            dtype=float
        )
        original_predictions = (
            original["elastic_net_logistic_prediction"] == "moved_toward_pathogenic"
        ).to_numpy(dtype=int)
        queue_by_id = queue.set_index("variation_id").loc[frame["variation_id"]]
        v7_probabilities = queue_by_id["v7_probability"].to_numpy(dtype=float)
        v7_predictions = (
            queue_by_id["v7_prediction"] == "moved_toward_pathogenic"
        ).to_numpy(dtype=int)
        clue_config = _load_json(root / "config/clue_score_v1.yaml")
        clue_score, clue_directional, clue_predictions = _clue_score(frame, clue_config)

        comparisons = {
            "selected_v9_1": (
                selected_probabilities,
                selected_predictions,
            ),
            "original_v9": (original_probabilities, original_predictions),
            "frozen_v8": (frozen_v8_probabilities, frozen_v8_predictions),
            "frozen_v7": (v7_probabilities, v7_predictions),
            "consequence_only": (
                consequence_predictions.astype(float),
                consequence_predictions,
            ),
            "majority": (majority_predictions.astype(float), majority_predictions),
        }
        comparison_rows = [
            _comparison_row(name, y, probability, prediction, groups)
            for name, (probability, prediction) in comparisons.items()
        ]
        for row in comparison_rows:
            row["selected_v9_1_minus_model_component_weighted_ba"] = (
                selected_metrics["component_weighted_balanced_accuracy"]
                - row["component_weighted_balanced_accuracy"]
            )
            reference_prediction = comparisons[row["model"]][1]
            row.update(
                _transition_counts(y, selected_predictions, reference_prediction)
            )
            row["same_records"] = True
            row["comparison_warning"] = (
                "V8 was evaluated while sealed; V9/V9.1 used opened labels."
            )
        _write_csv(
            temporary / "same_record_comparisons.csv",
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

        bootstrap = _bootstrap_metrics(
            y,
            groups,
            {name: prediction for name, (_, prediction) in comparisons.items()},
            int(config["bootstrap_replicates"]),
            int(config["random_state"]),
        )
        _write_json(temporary / "bootstrap_intervals.json", bootstrap)
        candidate_rows = [
            {
                "candidate": family,
                "status": "family_specific_diagnostic",
                "selected": False,
                "training_regime": config["primary_training_regime"],
                "feature_set": "all_allowed_non_leaky",
                "feature_count": len(V8_FEATURE_NAMES),
                "fold_min_component_weighted_ba": min(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in summary["outer_fold_metrics"]
                ),
                "fold_max_component_weighted_ba": max(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in summary["outer_fold_metrics"]
                ),
                **summary,
            }
            for family, summary in candidate_metrics.items()
        ]
        candidate_rows.append(
            {
                "candidate": "nested_family_selection_procedure",
                "status": "selected_internal_validation_procedure",
                "selected": True,
                "training_regime": config["primary_training_regime"],
                "feature_set": "all_allowed_non_leaky",
                "feature_count": len(V8_FEATURE_NAMES),
                "fold_min_component_weighted_ba": min(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in selected_metrics["outer_fold_metrics"]
                ),
                "fold_max_component_weighted_ba": max(
                    fold["component_weighted_balanced_accuracy"]
                    for fold in selected_metrics["outer_fold_metrics"]
                ),
                **selected_metrics,
                "warning": (
                    "Metrics estimate the full nested family-selection procedure; "
                    "outer folds may select different model families."
                ),
            }
        )
        candidate_rows.extend(
            {
                "candidate": item["candidate"],
                "status": "failed",
                "selected": False,
                "warning": item["error"],
            }
            for item in failures
        )
        candidate_rows.extend(
            [
                {
                    "candidate": "consequence_only",
                    "status": "baseline",
                    "selected": False,
                    **next(
                        row
                        for row in comparison_rows
                        if row["model"] == "consequence_only"
                    ),
                },
                {
                    "candidate": "majority",
                    "status": "baseline",
                    "selected": False,
                    **next(
                        row for row in comparison_rows if row["model"] == "majority"
                    ),
                },
                {
                    "candidate": "clue_score_coverage_only",
                    "status": "coverage_baseline_not_ranked",
                    "selected": False,
                    "records": int(clue_directional.sum()),
                    "coverage": float(clue_directional.mean()),
                    **_metric_summary(
                        y[clue_directional],
                        clue_predictions[clue_directional].astype(float),
                        clue_predictions[clue_directional],
                        _weights(groups[clue_directional]),
                    ),
                    "warning": "Coverage-conditioned; abstains are not errors.",
                },
            ]
        )
        _write_csv(
            temporary / "candidate_models.csv",
            [
                "candidate",
                "status",
                "selected",
                "training_regime",
                "feature_set",
                "feature_count",
                "records",
                "coverage",
                "component_weighted_balanced_accuracy",
                "balanced_accuracy",
                "accuracy",
                "macro_f1",
                "pathogenic_recall",
                "benign_recall",
                "roc_auc",
                "average_precision",
                "brier_score",
                "fold_min_component_weighted_ba",
                "fold_max_component_weighted_ba",
                "warning",
            ],
            candidate_rows,
        )
        _write_json(
            temporary / "threshold_selection.json",
            {
                "selection_scope": "inner grouped OOF within each outer training fold",
                "optimized_metric": config["primary_metric"],
                "primary_threshold_rule": (
                    "maximize component-weighted balanced accuracy; ties closest to "
                    "0.5 then lower"
                ),
                "safety_threshold_rule": (
                    "maximize pathogenic recall within 0.02 of the best inner "
                    "component-weighted balanced accuracy; report only"
                ),
                "candidate_outer_fold_selections": candidate_selections,
                "final_test_used": False,
            },
        )
        calibration_rows = [
            row
            for family, probabilities in candidate_probabilities.items()
            for row in _calibration_rows(family, y, probabilities)
        ]
        calibration_rows.extend(
            _calibration_rows(
                "nested_family_selection_procedure", y, selected_probabilities
            )
        )
        _write_csv(
            temporary / "calibration.csv",
            list(calibration_rows[0]),
            calibration_rows,
        )
        _write_json(temporary / "candidate_failures.json", failures)

        full_family_results: dict[str, dict[str, Any]] = {}
        for family, specs in candidate_specs.items():
            (
                family_spec,
                family_calibrator,
                family_threshold,
                family_safety_threshold,
                family_audits,
            ) = _select_spec(
                specs,
                base_x,
                base_y,
                base_groups,
                x,
                y,
                groups,
                config,
                int(config["random_state"]) + 100,
            )
            family_metrics = next(
                row
                for row in family_audits
                if row["configuration"] == family_spec.identifier
            )
            full_family_results[family] = {
                "spec": family_spec,
                "calibrator": family_calibrator,
                "threshold": family_threshold,
                "safety_threshold": family_safety_threshold,
                "configuration_results": family_audits,
                "selected_configuration_metrics": family_metrics,
            }
        final_family, full_family_trace = _rank_families(
            {
                family: item["selected_configuration_metrics"]
                for family, item in full_family_results.items()
            },
            config,
        )
        final_result = full_family_results[final_family]
        final_spec = final_result["spec"]
        final_calibrator = final_result["calibrator"]
        final_threshold = final_result["threshold"]
        safety_threshold = final_result["safety_threshold"]
        final_audits = final_result["configuration_results"]
        final_x, final_y, final_groups, final_weights = _combine_training(
            base_x, base_y, base_groups, x, y, groups
        )
        final_model = _fit(clone(final_spec.estimator), final_x, final_y, final_weights)
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
            "safety_threshold_report_only": safety_threshold,
            "full_development_configuration_results": final_audits,
            "feature_names": tuple(V8_FEATURE_NAMES),
        }
        joblib.dump(model_bundle, temporary / "model.joblib")

        _write_json(
            temporary / "threshold_selection.json",
            {
                "selection_scope": (
                    "family, configuration, calibration, and threshold selected from "
                    "grouped inner OOF predictions inside each outer training fold"
                ),
                "optimized_metric": config["primary_metric"],
                "primary_threshold_rule": (
                    "maximize component-weighted balanced accuracy; ties closest to "
                    "0.5 then lower"
                ),
                "safety_threshold_rule": (
                    "maximize pathogenic recall within 0.02 of the best inner "
                    "component-weighted balanced accuracy; report only"
                ),
                "candidate_outer_fold_selections": candidate_selections,
                "full_development_family_selection": {
                    "selected_family": final_family,
                    "selected_configuration": final_spec.identifier,
                    "selected_threshold": final_threshold,
                    "safety_threshold_report_only": safety_threshold,
                    "family_results": {
                        family: {
                            key: value
                            for key, value in result.items()
                            if key not in {"spec", "calibrator"}
                        }
                        for family, result in full_family_results.items()
                    },
                    "selection_trace": full_family_trace,
                },
                "final_test_used": False,
            },
        )

        original_metrics = next(
            row for row in comparison_rows if row["model"] == "original_v9"
        )
        v8_metrics = next(row for row in comparison_rows if row["model"] == "frozen_v8")
        paired = bootstrap[
            "selected_v9_1_paired_component_weighted_balanced_accuracy_difference"
        ]
        improves_original_point = (
            selected_metrics["component_weighted_balanced_accuracy"]
            > original_metrics["component_weighted_balanced_accuracy"]
        )
        clear_original_improvement = paired["original_v9"][0] > 0
        fair_v8_win = False
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
            "dataset_used": "V8 development plus V9.1 all-eligible outer-training rows",
            "split_method": "nested component-grouped validation on frozen V9 folds",
            "training_records_per_outer_fold": len(base_y) + 800,
            "validation_records_per_outer_fold": 200,
            "test_records": 0,
            "selected_threshold_full_development": final_threshold,
            "safety_threshold_report_only": safety_threshold,
            "metrics": selected_metrics,
            "metrics_scope": (
                "Fully nested OOF estimate of the family/configuration/calibration/"
                "threshold selection procedure; not a test of the serialized full-data "
                "pipeline."
            ),
            "leakage_audit_result": feature_audit,
            "leakage_audit_status": feature_audit["status"],
            "manual_review_status": "not started; 0 completed reviews",
            "calibration": {
                "calibrated": final_spec.calibrated,
                "nested_selection_procedure_brier_score": selected_metrics[
                    "brier_score"
                ],
                "calibration_file": "outputs/evaluations/v9_1_calibration.csv",
            },
            "bootstrap_intervals": bootstrap,
            "comparison_to_original_v9": {
                "point_estimate_improved": improves_original_point,
                "clear_paired_improvement": clear_original_improvement,
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
                "fairly_beat_v8": fair_v8_win,
                "warning": (
                    "V8 was evaluated while sealed; V9.1 was developed after these "
                    "labels were opened. Only a future equivalent untouched test can "
                    "establish a fair V8 win."
                ),
            },
            "training_regime_diagnosis": regime_metrics,
            "artifact": {
                "path": "outputs/v9_1_development/model.joblib",
                "sha256": sha256_file(temporary / "model.joblib"),
                "size_bytes": (temporary / "model.joblib").stat().st_size,
            },
            "limitations": [
                WARNING,
                "No human-reviewed clean rows were available.",
                "No independent temporal final test was available.",
                "The V8 comparison is same-record but asymmetric.",
                "Bootstrap intervals condition on fixed OOF predictions.",
                "This artifact has no clinical-use validity.",
            ],
            "warnings": [
                WARNING,
                "The nested estimate evaluates a selection procedure on opened labels, "
                "not an independent final test.",
                "The serialized full-data pipeline has no test metrics.",
            ],
        }
        _write_json(temporary / "model_registry.json", registry)

        prediction_rows = []
        selected_probability = selected_probabilities
        selected_prediction = selected_predictions
        for index, source in frame.iterrows():
            prediction_rows.append(
                {
                    "variation_id": source["variation_id"],
                    "gene": source["gene"],
                    "component_hash": source["component_hash"],
                    "actual_outcome": source["dataset_outcome"],
                    "v9_1_probability": float(selected_probability[index]),
                    "v9_1_prediction": (
                        "moved_toward_pathogenic"
                        if selected_prediction[index]
                        else "moved_toward_benign"
                    ),
                    "v9_1_correct": bool(selected_prediction[index] == y[index]),
                    "v9_1_outer_selected_family": selected_family_by_index[index],
                    "original_v9_prediction": (
                        "moved_toward_pathogenic"
                        if original_predictions[index]
                        else "moved_toward_benign"
                    ),
                    "v8_prediction": source["v8_prediction"],
                    "v8_correct": bool(frozen_v8_predictions[index] == y[index]),
                    "v7_prediction": queue_by_id.iloc[index]["v7_prediction"],
                    "review_state": source["v9_1_review_state"],
                    "inclusion_reason": source["v9_1_inclusion_reason"],
                    "manual_decision": source["manual_decision"],
                    "automatic_review_flags": source["automatic_review_flags"],
                    "clue_score": float(clue_score[index]),
                    "clue_score_directional": bool(clue_directional[index]),
                    "model_explanation": (
                        f"{selected_family_by_index[index]} selected inside this outer "
                        "training partition using 64 authenticated old-snapshot "
                        "features; the OOF prediction excluded this component."
                    ),
                }
            )
        _write_csv(
            temporary / "oof_predictions.csv",
            list(prediction_rows[0]),
            prediction_rows,
        )
        output_hashes = {
            path.name: sha256_file(path)
            for path in sorted(temporary.iterdir())
            if path.is_file() and path.name != "run_manifest.json"
        }
        run_manifest = {
            "schema_version": 1,
            "status": "v9_1_internal_development_complete",
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
            "feature_count": len(V8_FEATURE_NAMES),
            "candidate_failures": failures,
            "config_sha256": sha256_file(config_path),
            "dataset_sha256": sha256_file(dataset_path),
            "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
            "source_hashes": {
                "v8_development_database": sha256_file(development_db),
                "historical_predictor_index": sha256_file(predictor_index),
                "v7_predictions": sha256_file(v7_path),
                "original_v9_predictions": sha256_file(
                    root / "outputs/v9_exploratory/oof_predictions.csv"
                ),
                "frozen_outer_folds": sha256_file(
                    root / "outputs/v9_exploratory/fold_assignments.csv"
                ),
                "v8_feature_and_development_loader": sha256_file(
                    root / "src/variant_time_machine/ai_temporal_v8.py"
                ),
                "v9_metric_and_clue_helpers": sha256_file(
                    root / "src/variant_time_machine/v9_exploratory.py"
                ),
                "v9_1_dataset_builder": sha256_file(
                    root / "src/variant_time_machine/v9_1_dataset.py"
                ),
            },
            "implementation_sha256": sha256_file(
                root / "src/variant_time_machine/v9_1.py"
            ),
            "output_hashes": output_hashes,
            "environment": {
                "python": os.sys.version.split()[0],
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "self_checks": {
                "feature_leakage_audit_passed": True,
                "labels_unchanged": True,
                "outer_component_overlap": 0,
                "prior_development_gene_overlap": 0,
                "prior_development_variation_id_overlap": 0,
                "same_record_comparison_present": True,
                "family_selection_nested_inside_outer_folds": True,
                "accuracy_reported_with_balanced_accuracy": True,
                "clean_dataset_too_small_warning_present": True,
                "clinical_use_claim": False,
                "final_test_used_for_selection": False,
            },
        }
        _write_json(temporary / "run_manifest.json", run_manifest)
        if output_dir:
            if output_dir.exists():
                raise V91Error(
                    f"Refusing to overwrite V9.1 output directory: {output_dir}"
                )
            os.replace(temporary, output_dir)
            temporary = output_dir
        if publish:
            _publish_outputs(root, temporary)
        return {
            "manifest": run_manifest,
            "registry": registry,
            "candidate_metrics": candidate_metrics,
            "selected_family": final_family,
            "working_output": str(temporary),
        }
    finally:
        if temporary.exists() and (not output_dir or temporary != output_dir):
            shutil.rmtree(temporary, ignore_errors=True)
