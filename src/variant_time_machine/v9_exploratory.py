"""Exploratory V9 candidate training on previously opened V8 records only."""

from __future__ import annotations

import csv
import json
import platform
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from variant_time_machine.v8_presentation import sha256_file
from variant_time_machine.v9_dataset import CHERRY_PICKING_WARNING

EXPLORATORY_WARNING = (
    "Exploratory analysis on previously opened V8 records. Not an official V9 model "
    "selection or final evaluation."
)
EXPECTED_RECORDS = 1000
EXPECTED_COMPONENTS = 559
OUTPUT_FILENAMES = {
    "bootstrap_intervals.json",
    "calibration_bins.csv",
    "candidate_failures.json",
    "candidate_metrics.csv",
    "candidate_metrics.json",
    "exploratory_leader.joblib",
    "fold_assignments.csv",
    "nested_selections.json",
    "oof_predictions.csv",
    "run_manifest.json",
}


class V9ExploratoryError(ValueError):
    """Raised when exploratory training violates its isolated protocol."""


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _git_state(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"commit": commit, "working_tree_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "not available", "working_tree_dirty": "not available"}


def _load_inputs(
    root: Path, config_path: Path
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame, list[str]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest_path = root / "data/processed/v9/v9_dataset_manifest.json"
    dataset_path = root / "data/processed/v9/v9_messy_dataset.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if config.get("status") != "frozen_exploratory_opened_v8_plan":
        raise V9ExploratoryError("Exploratory V9 configuration is not frozen.")
    if config.get("official_v9_winner") is not None or config.get(
        "final_test_evaluated"
    ):
        raise V9ExploratoryError("Exploratory configuration cannot authorize final V9.")
    if (
        manifest.get("status") != "preparation_only"
        or manifest.get("training_eligible") is not False
        or manifest.get("final_test_allowed") is not False
    ):
        raise V9ExploratoryError(
            "Current V9 dataset lock state is not exploratory-only."
        )
    expected_dataset_hash = manifest.get("output_hashes", {}).get(
        "v9_messy_dataset.csv"
    )
    if expected_dataset_hash != sha256_file(dataset_path):
        raise V9ExploratoryError("V9 messy dataset hash does not match its manifest.")
    frame = pd.read_csv(dataset_path, dtype={"variation_id": str})
    feature_names = list(manifest.get("feature_columns", []))
    if (
        len(frame) != EXPECTED_RECORDS
        or frame["variation_id"].nunique() != EXPECTED_RECORDS
        or frame["component_hash"].nunique() != EXPECTED_COMPONENTS
    ):
        raise V9ExploratoryError("Exploratory V9 row or component accounting changed.")
    if not feature_names or any(
        not name.startswith("feature__") for name in feature_names
    ):
        raise V9ExploratoryError(
            "Exploratory predictors must use the exact feature allowlist."
        )
    if feature_names != [
        name for name in frame.columns if name.startswith("feature__")
    ]:
        raise V9ExploratoryError("Exploratory feature order changed from the manifest.")
    if not (frame["dataset_outcome"] == frame["original_automatic_outcome"]).all():
        raise V9ExploratoryError(
            "Messy exploratory labels must remain original automatic labels."
        )
    features = frame[feature_names].to_numpy(dtype=float)
    if not np.isfinite(features).all():
        raise V9ExploratoryError(
            "Exploratory predictors contain missing or non-finite values."
        )
    if set(frame["dataset_outcome"]) != {
        "moved_toward_benign",
        "moved_toward_pathogenic",
    }:
        raise V9ExploratoryError("Exploratory target classes changed.")
    return config, manifest, frame, feature_names


def _weights(groups: np.ndarray) -> np.ndarray:
    counts = Counter(groups.tolist())
    return np.asarray([1 / counts[group] for group in groups], dtype=float)


def _weighted_balanced_accuracy(
    targets: np.ndarray, predictions: np.ndarray, weights: np.ndarray
) -> float:
    recalls = []
    for label in (0, 1):
        selected = targets == label
        denominator = float(weights[selected].sum())
        if denominator == 0:
            raise V9ExploratoryError(
                "A grouped metric partition lacks one target class."
            )
        recalls.append(
            float((weights[selected] * (predictions[selected] == label)).sum())
            / denominator
        )
    return float(sum(recalls) / 2)


def _fit(estimator: Any, x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> Any:
    if isinstance(estimator, Pipeline):
        return estimator.fit(x, y, model__sample_weight=weights)
    return estimator.fit(x, y, sample_weight=weights)


def _platt(probabilities: np.ndarray, targets: np.ndarray, weights: np.ndarray) -> Any:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    return LogisticRegression(C=1_000_000, max_iter=3000).fit(
        logits, targets, sample_weight=weights
    )


def _calibrate(calibrator: Any, probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    return calibrator.predict_proba(logits)[:, 1]


def _threshold(
    targets: np.ndarray,
    probabilities: np.ndarray,
    weights: np.ndarray,
    config: dict[str, Any],
) -> float:
    values = np.arange(
        float(config["threshold_minimum"]),
        float(config["threshold_maximum"]) + float(config["threshold_step"]) / 2,
        float(config["threshold_step"]),
    )
    return float(
        max(
            (
                _weighted_balanced_accuracy(targets, probabilities >= value, weights),
                -abs(value - 0.5),
                -value,
                value,
            )
            for value in values
        )[-1]
    )


def _candidate_estimators(family: str, config: dict[str, Any]) -> list[tuple[str, Any]]:
    seed = int(config["random_state"])
    values: list[tuple[str, Any]] = []
    for item in config["candidates"][family]:
        if family == "elastic_net_logistic":
            name = f"logistic_C_{item['C']:g}_l1_{item['l1_ratio']:g}"
            estimator = Pipeline(
                (
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            C=float(item["C"]),
                            l1_ratio=float(item["l1_ratio"]),
                            penalty="elasticnet",
                            solver="saga",
                            max_iter=5000,
                            random_state=seed,
                        ),
                    ),
                )
            )
        elif family == "hist_gradient_boosting":
            name = (
                f"histgb_leaf_{item['max_leaf_nodes']}_l2_{item['l2_regularization']:g}"
            )
            estimator = HistGradientBoostingClassifier(
                max_leaf_nodes=int(item["max_leaf_nodes"]),
                learning_rate=float(item["learning_rate"]),
                l2_regularization=float(item["l2_regularization"]),
                max_iter=300,
                random_state=seed,
            )
        elif family == "extra_trees":
            name = f"extra_trees_leaf_{item['min_samples_leaf']}"
            estimator = ExtraTreesClassifier(
                n_estimators=int(item["n_estimators"]),
                max_features=item["max_features"],
                min_samples_leaf=int(item["min_samples_leaf"]),
                random_state=seed,
                n_jobs=1,
            )
        else:
            raise V9ExploratoryError(f"Unknown exploratory family: {family}")
        values.append((name, estimator))
    return values


def _raw_oof(
    estimator: Any,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    weights: np.ndarray,
    folds: int,
    seed: int,
) -> np.ndarray:
    probabilities = np.full(len(y), np.nan, dtype=float)
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train, validation in splitter.split(x, y, groups):
        fitted = _fit(clone(estimator), x[train], y[train], weights[train])
        probabilities[validation] = fitted.predict_proba(x[validation])[:, 1]
    if not np.isfinite(probabilities).all():
        raise V9ExploratoryError("Inner grouped predictions are incomplete.")
    return probabilities


def _nested_family_oof(
    family: str,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    weights: np.ndarray,
    outer_splits: list[tuple[np.ndarray, np.ndarray]],
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    candidates = _candidate_estimators(family, config)
    probabilities = np.full(len(y), np.nan, dtype=float)
    predictions = np.full(len(y), -1, dtype=int)
    selections = []
    for fold, (outer_train, outer_validation) in enumerate(outer_splits):
        results = []
        for name, estimator in candidates:
            raw = _raw_oof(
                estimator,
                x[outer_train],
                y[outer_train],
                groups[outer_train],
                weights[outer_train],
                int(config["inner_folds"]),
                int(config["random_state"]) + fold + 1,
            )
            calibrator = _platt(raw, y[outer_train], weights[outer_train])
            calibrated = _calibrate(calibrator, raw)
            threshold = _threshold(
                y[outer_train], calibrated, weights[outer_train], config
            )
            score = _weighted_balanced_accuracy(
                y[outer_train], calibrated >= threshold, weights[outer_train]
            )
            results.append(
                {
                    "name": name,
                    "estimator": estimator,
                    "calibrator": calibrator,
                    "threshold": threshold,
                    "score": score,
                }
            )
        selected = min(results, key=lambda item: (-item["score"], item["name"]))
        fitted = _fit(
            clone(selected["estimator"]),
            x[outer_train],
            y[outer_train],
            weights[outer_train],
        )
        raw_validation = fitted.predict_proba(x[outer_validation])[:, 1]
        calibrated_validation = _calibrate(selected["calibrator"], raw_validation)
        probabilities[outer_validation] = calibrated_validation
        predictions[outer_validation] = (
            calibrated_validation >= selected["threshold"]
        ).astype(int)
        selections.append(
            {
                "fold": fold,
                "selected_configuration": selected["name"],
                "inner_component_weighted_balanced_accuracy": selected["score"],
                "threshold": selected["threshold"],
            }
        )
    if not np.isfinite(probabilities).all() or (predictions < 0).any():
        raise V9ExploratoryError(
            f"Nested grouped predictions are incomplete for {family}."
        )
    return probabilities, predictions, selections


def _metric_summary(
    targets: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    weights: np.ndarray,
) -> dict[str, Any]:
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    precision, recall, f1, _ = precision_recall_fscore_support(
        targets, predictions, labels=[0, 1], zero_division=0
    )
    return {
        "records": int(len(targets)),
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "component_weighted_balanced_accuracy": _weighted_balanced_accuracy(
            targets, predictions, weights
        ),
        "macro_f1": float(f1_score(targets, predictions, average="macro")),
        "weighted_f1": float(f1_score(targets, predictions, average="weighted")),
        "benign_precision": float(precision[0]),
        "pathogenic_precision": float(precision[1]),
        "benign_recall": float(recall[0]),
        "pathogenic_recall": float(recall[1]),
        "benign_f1": float(f1[0]),
        "pathogenic_f1": float(f1[1]),
        "roc_auc": float(roc_auc_score(targets, probabilities)),
        "average_precision": float(average_precision_score(targets, probabilities)),
        "brier_score": float(brier_score_loss(targets, probabilities)),
        "log_loss": float(log_loss(targets, np.clip(probabilities, 1e-6, 1 - 1e-6))),
        "confusion_matrix": {
            "TN": int(matrix[0, 0]),
            "FP": int(matrix[0, 1]),
            "FN": int(matrix[1, 0]),
            "TP": int(matrix[1, 1]),
        },
    }


def _calibration_rows(
    name: str, targets: np.ndarray, probabilities: np.ndarray
) -> list[dict[str, Any]]:
    rows = []
    edges = np.linspace(0, 1, 11)
    for index in range(10):
        selected = (probabilities >= edges[index]) & (
            probabilities < edges[index + 1]
            if index < 9
            else probabilities <= edges[index + 1]
        )
        rows.append(
            {
                "candidate": name,
                "bin": index + 1,
                "lower": edges[index],
                "upper": edges[index + 1],
                "records": int(selected.sum()),
                "mean_probability": (
                    float(probabilities[selected].mean()) if selected.any() else ""
                ),
                "observed_pathogenic_fraction": (
                    float(targets[selected].mean()) if selected.any() else ""
                ),
            }
        )
    return rows


def _component_bootstrap(
    targets: np.ndarray,
    groups: np.ndarray,
    predictions: dict[str, np.ndarray],
    reference: str,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    unique_groups = np.asarray(sorted(set(groups.tolist())))
    by_group = {group: np.flatnonzero(groups == group) for group in unique_groups}
    rng = np.random.default_rng(seed)
    values: dict[str, list[float]] = {name: [] for name in predictions}
    differences: dict[str, list[float]] = {
        name: [] for name in predictions if name != reference
    }
    skipped = 0
    for _ in range(replicates):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([by_group[group] for group in sampled])
        sample_groups = np.concatenate(
            [
                np.full(len(by_group[group]), draw_index)
                for draw_index, group in enumerate(sampled)
            ]
        )
        sample_targets = targets[indices]
        if len(set(sample_targets.tolist())) < 2:
            skipped += 1
            continue
        sample_weights = _weights(sample_groups)
        replicate_scores = {
            name: _weighted_balanced_accuracy(
                sample_targets, prediction[indices], sample_weights
            )
            for name, prediction in predictions.items()
        }
        for name, score in replicate_scores.items():
            values[name].append(score)
        for name in differences:
            differences[name].append(
                replicate_scores[name] - replicate_scores[reference]
            )

    def interval(items: list[float]) -> list[float]:
        return [
            float(np.percentile(items, 2.5)),
            float(np.percentile(items, 97.5)),
        ]

    return {
        "replicates_requested": replicates,
        "replicates_used": replicates - skipped,
        "replicates_skipped": skipped,
        "component_weighted_balanced_accuracy_95_percent": {
            name: interval(items) for name, items in values.items()
        },
        "paired_difference_from_frozen_v8_95_percent": {
            name: interval(items) for name, items in differences.items()
        },
        "warning": (
            "Component bootstrap conditions on fixed exploratory OOF predictions and "
            "does not include all model-selection uncertainty."
        ),
    }


def _clue_score(
    frame: pd.DataFrame, clue_config: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if (
        clue_config.get("status") != "frozen"
        or clue_config.get("scoring_version") != "Clue Score V1"
    ):
        raise V9ExploratoryError("Clue Score V1 configuration is not frozen.")
    criteria_without_conflict = frame["feature__criteria_supplied"].to_numpy() * (
        1 - frame["feature__conflicting_interpretations"].to_numpy()
    )
    score = (
        4 * frame["feature__consequence_loss_of_function"].to_numpy()
        + 3 * frame["feature__consequence_canonical_splice"].to_numpy()
        + frame["feature__consequence_missense"].to_numpy()
        - 3 * frame["feature__consequence_synonymous"].to_numpy()
        - frame["feature__consequence_noncoding"].to_numpy()
        + 2 * frame["feature__expert_panel"].to_numpy()
        + frame["feature__multiple_submitters_no_conflict"].to_numpy()
        + criteria_without_conflict
    )
    directional = (score >= 3) | (score <= -2)
    predictions = (score >= 3).astype(int)
    return score, directional, predictions


def run_v9_exploratory(
    project_root: Path,
    *,
    config_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run isolated nested grouped exploration without authorizing official V9."""
    root = project_root.resolve()
    config_path = config_path or root / "config/v9_exploratory.json"
    output_dir = output_dir or root / "outputs/v9_exploratory"
    if "frozen" in output_dir.parts or output_dir == root / "data/processed/v9":
        raise V9ExploratoryError(
            "Exploratory outputs cannot use official or frozen paths."
        )
    config, manifest, frame, feature_names = _load_inputs(root, config_path)
    clue_config_path = root / "config/clue_score_v1.yaml"
    clue_config = json.loads(clue_config_path.read_text(encoding="utf-8"))
    x = frame[feature_names].to_numpy(dtype=float)
    y = (frame["dataset_outcome"] == "moved_toward_pathogenic").to_numpy(dtype=int)
    groups = frame["component_hash"].to_numpy(dtype=str)
    weights = _weights(groups)
    splitter = StratifiedGroupKFold(
        n_splits=int(config["outer_folds"]),
        shuffle=True,
        random_state=int(config["random_state"]),
    )
    outer_splits = list(splitter.split(x, y, groups))
    fold_by_index = np.full(len(frame), -1, dtype=int)
    fold_rows = []
    for fold, (_, validation) in enumerate(outer_splits):
        fold_by_index[validation] = fold
        fold_rows.extend(
            {
                "variation_id": frame.iloc[index]["variation_id"],
                "component_hash": groups[index],
                "outer_fold": fold,
            }
            for index in validation
        )
    if (fold_by_index < 0).any() or any(
        len(set(fold_by_index[groups == group].tolist())) != 1
        for group in set(groups.tolist())
    ):
        raise V9ExploratoryError("Outer grouped folds are incomplete or overlap.")
    output_dir.mkdir(parents=True, exist_ok=True)
    unexpected_outputs = {
        path.name for path in output_dir.iterdir() if path.name not in OUTPUT_FILENAMES
    }
    if unexpected_outputs:
        raise V9ExploratoryError(
            "Exploratory output directory contains unexpected files: "
            + ", ".join(sorted(unexpected_outputs))
        )
    for filename in OUTPUT_FILENAMES:
        (output_dir / filename).unlink(missing_ok=True)
    fold_path = output_dir / "fold_assignments.csv"
    _write_csv(
        fold_path,
        ["variation_id", "component_hash", "outer_fold"],
        sorted(fold_rows, key=lambda row: int(row["variation_id"])),
    )
    fold_hash_before_fit = sha256_file(fold_path)

    candidate_probabilities: dict[str, np.ndarray] = {}
    candidate_predictions: dict[str, np.ndarray] = {}
    selections: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    for family in (
        "elastic_net_logistic",
        "hist_gradient_boosting",
        "extra_trees",
    ):
        try:
            probabilities, predictions, family_selections = _nested_family_oof(
                family, x, y, groups, weights, outer_splits, config
            )
            candidate_probabilities[family] = probabilities
            candidate_predictions[family] = predictions
            selections[family] = family_selections
        except (ValueError, RuntimeError, FloatingPointError) as exc:
            failures.append({"candidate": family, "error": str(exc)})

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
    candidate_predictions["consequence_only"] = consequence_predictions
    candidate_probabilities["consequence_only"] = consequence_predictions.astype(float)
    majority_predictions = np.zeros(len(y), dtype=int)
    for train, validation in outer_splits:
        positive = float(weights[train][y[train] == 1].sum())
        negative = float(weights[train][y[train] == 0].sum())
        majority_predictions[validation] = int(positive > negative)
    candidate_predictions["majority"] = majority_predictions
    candidate_probabilities["majority"] = majority_predictions.astype(float)
    candidate_predictions["frozen_v8_reference"] = (
        frame["v8_prediction"] == "moved_toward_pathogenic"
    ).to_numpy(dtype=int)
    candidate_probabilities["frozen_v8_reference"] = frame["v8_probability"].to_numpy(
        dtype=float
    )

    metrics = {
        name: _metric_summary(y, candidate_probabilities[name], predictions, weights)
        for name, predictions in candidate_predictions.items()
    }
    for name, summary in metrics.items():
        summary["outer_fold_metrics"] = [
            {
                "fold": fold,
                **_metric_summary(
                    y[validation],
                    candidate_probabilities[name][validation],
                    candidate_predictions[name][validation],
                    _weights(groups[validation]),
                ),
            }
            for fold, (_, validation) in enumerate(outer_splits)
        ]
    rank_eligible = [
        name
        for name in (
            "elastic_net_logistic",
            "hist_gradient_boosting",
            "extra_trees",
            "consequence_only",
            "majority",
        )
        if name in metrics
    ]
    best_primary = max(
        metrics[name]["component_weighted_balanced_accuracy"] for name in rank_eligible
    )
    close = [
        name
        for name in rank_eligible
        if metrics[name]["component_weighted_balanced_accuracy"] >= best_primary - 0.005
    ]
    simplicity = {
        "majority": 0,
        "consequence_only": 1,
        "elastic_net_logistic": 2,
        "hist_gradient_boosting": 3,
        "extra_trees": 4,
    }
    leader = min(
        close,
        key=lambda name: (
            -metrics[name]["macro_f1"],
            -metrics[name]["pathogenic_recall"],
            metrics[name]["brier_score"],
            simplicity[name],
            name,
        ),
    )

    clue_score, clue_directional, clue_predictions = _clue_score(frame, clue_config)
    clue_metrics = (
        _metric_summary(
            y[clue_directional],
            clue_predictions[clue_directional].astype(float),
            clue_predictions[clue_directional],
            _weights(groups[clue_directional]),
        )
        if clue_directional.any()
        else None
    )
    metrics["clue_score_coverage_only"] = {
        "coverage": float(clue_directional.mean()),
        "directional_records": int(clue_directional.sum()),
        "abstained_records": int((~clue_directional).sum()),
        "covered_row_metrics": clue_metrics,
        "rank_eligible": False,
    }

    bootstrap = _component_bootstrap(
        y,
        groups,
        candidate_predictions,
        "frozen_v8_reference",
        int(config["bootstrap_replicates"]),
        int(config["random_state"]),
    )
    calibration_rows = [
        row
        for name, probabilities in candidate_probabilities.items()
        for row in _calibration_rows(name, y, probabilities)
    ]
    prediction_rows = []
    for index, source in frame.iterrows():
        row: dict[str, Any] = {
            "variation_id": source["variation_id"],
            "component_hash": source["component_hash"],
            "actual_outcome": source["dataset_outcome"],
            "outer_fold": int(fold_by_index[index]),
            "clue_score": float(clue_score[index]),
            "clue_score_directional": bool(clue_directional[index]),
        }
        for name in candidate_predictions:
            row[f"{name}_probability"] = float(candidate_probabilities[name][index])
            row[f"{name}_prediction"] = (
                "moved_toward_pathogenic"
                if candidate_predictions[name][index]
                else "moved_toward_benign"
            )
        prediction_rows.append(row)

    metric_rows = [
        {"candidate": name, **value}
        for name, value in metrics.items()
        if name != "clue_score_coverage_only"
    ]
    _write_json(output_dir / "candidate_metrics.json", metrics)
    _write_csv(
        output_dir / "candidate_metrics.csv",
        [
            "candidate",
            "records",
            "component_weighted_balanced_accuracy",
            "balanced_accuracy",
            "accuracy",
            "macro_f1",
            "weighted_f1",
            "benign_recall",
            "pathogenic_recall",
            "roc_auc",
            "average_precision",
            "brier_score",
            "log_loss",
        ],
        metric_rows,
    )
    _write_csv(
        output_dir / "oof_predictions.csv",
        list(prediction_rows[0]),
        prediction_rows,
    )
    _write_csv(
        output_dir / "calibration_bins.csv",
        list(calibration_rows[0]),
        calibration_rows,
    )
    _write_json(output_dir / "bootstrap_intervals.json", bootstrap)
    _write_json(output_dir / "candidate_failures.json", failures)
    _write_json(output_dir / "nested_selections.json", selections)

    final_candidates = (
        dict(_candidate_estimators(leader, config))
        if leader
        in {
            "elastic_net_logistic",
            "hist_gradient_boosting",
            "extra_trees",
        }
        else {}
    )
    if final_candidates:
        full_results = []
        for name, estimator in final_candidates.items():
            raw = _raw_oof(
                estimator,
                x,
                y,
                groups,
                weights,
                int(config["outer_folds"]),
                int(config["random_state"]),
            )
            calibrator = _platt(raw, y, weights)
            calibrated = _calibrate(calibrator, raw)
            threshold = _threshold(y, calibrated, weights, config)
            score = _weighted_balanced_accuracy(y, calibrated >= threshold, weights)
            full_results.append((score, name, estimator, calibrator, threshold))
        _, selected_name, estimator, calibrator, threshold = min(
            full_results, key=lambda item: (-item[0], item[1])
        )
        full_model = _fit(clone(estimator), x, y, weights)
        joblib.dump(
            {
                "status": "exploratory_opened_v8_only",
                "official_v9_winner": None,
                "family": leader,
                "configuration": selected_name,
                "base_model": full_model,
                "calibrator": calibrator,
                "threshold": threshold,
                "feature_names": tuple(feature_names),
            },
            output_dir / "exploratory_leader.joblib",
        )

    if sha256_file(fold_path) != fold_hash_before_fit:
        raise V9ExploratoryError(
            "Frozen outer fold assignments changed during fitting."
        )
    output_files = [
        path
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name not in {"run_manifest.json"}
    ]
    run_manifest = {
        "schema_version": 1,
        "status": "exploratory_opened_v8_only",
        "official_v9_winner": None,
        "exploratory_leader_among_new_candidate_families": leader,
        "strongest_same_record_reference": "frozen_v8_reference",
        "final_test_evaluated": False,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "warning": EXPLORATORY_WARNING,
        "additional_warning": CHERRY_PICKING_WARNING,
        "dataset_records": len(frame),
        "dataset_components": len(set(groups.tolist())),
        "target_counts": {
            "moved_toward_benign": int((y == 0).sum()),
            "moved_toward_pathogenic": int((y == 1).sum()),
        },
        "review_gate_passed": manifest["manual_review_minimum"]["passed"],
        "training_eligible": manifest["training_eligible"],
        "final_test_allowed": manifest["final_test_allowed"],
        "config_sha256": sha256_file(config_path),
        "clue_score_config_sha256": sha256_file(clue_config_path),
        "implementation_hashes": {
            "src/variant_time_machine/v9_exploratory.py": sha256_file(
                root / "src/variant_time_machine/v9_exploratory.py"
            ),
            "scripts/run_v9_exploratory.py": sha256_file(
                root / "scripts/run_v9_exploratory.py"
            ),
        },
        "dataset_sha256": sha256_file(root / "data/processed/v9/v9_messy_dataset.csv"),
        "dataset_manifest_sha256": sha256_file(
            root / "data/processed/v9/v9_dataset_manifest.json"
        ),
        "fold_assignments_sha256": fold_hash_before_fit,
        "feature_names": feature_names,
        "candidate_failures": failures,
        "output_hashes": {path.name: sha256_file(path) for path in output_files},
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "git": _git_state(root),
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)
    return {
        "manifest": run_manifest,
        "metrics": metrics,
        "bootstrap": bootstrap,
        "selections": selections,
    }
