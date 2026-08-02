"""Train V7 and seal 2024 temporal predictions before loading 2026 answers."""

import csv
import gzip
import hashlib
import json
import math
import shutil
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from variant_time_machine.ai_holdout_v4 import _connected_group_keys, _sha256
from variant_time_machine.ai_holdout_v5 import FEATURE_NAMES, _source_rows
from variant_time_machine.clue_score import (
    CLUE_SCORE_V1_PATH,
    load_clue_score_config,
    normalize_newer_outcome,
    older_snapshot_from_row,
    score_older_snapshot,
)
from variant_time_machine.config import (
    AI_TEMPORAL_V7_CONFIG_PATH,
    AI_TEMPORAL_V7_RESULTS_DIR,
)
from variant_time_machine.model_registry import compute_binary_metrics

V7_FEATURE_NAMES = (
    *FEATURE_NAMES[:11],
    "log1p_classification_age_days",
    "log1p_maximum_submitter_count",
    "missing_core_field_count",
)


class AITemporalV7Error(ValueError):
    """Raised when the frozen temporal experiment contract is violated."""


def load_ai_temporal_v7_config(
    path: Path = AI_TEMPORAL_V7_CONFIG_PATH,
) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AITemporalV7Error(f"Could not load AI Temporal V7: {exc}") from exc
    if config.get("experiment_version") != "AI Temporal V7":
        raise AITemporalV7Error("AI Temporal V7 configuration is invalid.")
    if config.get("status") != "frozen":
        raise AITemporalV7Error("AI Temporal V7 must remain frozen.")
    if tuple(config.get("features", ())) != V7_FEATURE_NAMES:
        raise AITemporalV7Error("The frozen V7 feature list changed.")
    if config.get("final_test_records") != 1000:
        raise AITemporalV7Error("V7 requires exactly 1,000 primary test records.")
    return config


def _transform_v5_features(features: Sequence[float]) -> tuple[float, ...]:
    values = list(map(float, features))
    values[11] = math.log1p(max(values[11], 0.0))
    values[12] = math.log1p(max(values[12], 0.0))
    return tuple(values)


def _candidate_estimators(config: Mapping[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    seed = int(config["development"]["random_state"])
    for value in config["candidate_models"]["logistic_regression_C"]:
        candidates.append(
            (
                f"logistic_C_{value:g}",
                Pipeline(
                    (
                        ("scale", StandardScaler()),
                        (
                            "model",
                            LogisticRegression(
                                C=float(value),
                                class_weight="balanced",
                                max_iter=3000,
                                random_state=seed,
                            ),
                        ),
                    )
                ),
            )
        )
    for values in config["candidate_models"]["hist_gradient_boosting"]:
        candidates.append(
            (
                "histgb_leaf_"
                f"{values['max_leaf_nodes']}_l2_{values['l2_regularization']:g}",
                HistGradientBoostingClassifier(
                    learning_rate=float(values["learning_rate"]),
                    max_leaf_nodes=int(values["max_leaf_nodes"]),
                    l2_regularization=float(values["l2_regularization"]),
                    max_iter=250,
                    class_weight="balanced",
                    random_state=seed,
                ),
            )
        )
    return candidates


def _fit(
    estimator: Any, features: np.ndarray, targets: np.ndarray, weights: np.ndarray
):
    if isinstance(estimator, Pipeline):
        return estimator.fit(features, targets, model__sample_weight=weights)
    return estimator.fit(features, targets, sample_weight=weights)


def _calibrated_probabilities(
    estimator: Any, calibrator: LogisticRegression, features: np.ndarray
) -> np.ndarray:
    raw = np.clip(estimator.predict_proba(features)[:, 1], 1e-6, 1 - 1e-6)
    logits = np.log(raw / (1 - raw)).reshape(-1, 1)
    return calibrator.predict_proba(logits)[:, 1]


def _select_threshold(targets: np.ndarray, probabilities: np.ndarray) -> float:
    candidates = np.arange(0.2, 0.8001, 0.005)
    scored = [
        (
            balanced_accuracy_score(targets, probabilities >= threshold),
            -abs(threshold - 0.5),
            -threshold,
            threshold,
        )
        for threshold in candidates
    ]
    return float(max(scored)[-1])


def _development_arrays(source_database: Path):
    rows = _source_rows(source_database)
    group_keys = _connected_group_keys(rows)
    groups = np.asarray([group_keys[row["variation_id"]] for row in rows])
    counts = Counter(groups)
    weights = np.asarray([1 / math.sqrt(counts[group]) for group in groups])
    features = np.asarray(
        [_transform_v5_features(row["features"]) for row in rows], dtype=float
    )
    targets = np.asarray([row["target"] for row in rows], dtype=int)
    identifiers = {row["variation_id"] for row in rows}
    return rows, features, targets, groups, weights, identifiers


def _select_and_fit_model(source_database: Path, config: Mapping[str, Any]):
    rows, features, targets, groups, weights, identifiers = _development_arrays(
        source_database
    )
    splitter = StratifiedGroupKFold(
        n_splits=int(config["development"]["folds"]),
        shuffle=True,
        random_state=int(config["development"]["random_state"]),
    )
    splits = list(splitter.split(features, targets, groups))
    results = []
    selected = None
    selected_oof = None
    for name, candidate in _candidate_estimators(config):
        probabilities = np.zeros(len(targets), dtype=float)
        fold_scores = []
        for train_indices, validation_indices in splits:
            fitted = _fit(
                clone(candidate),
                features[train_indices],
                targets[train_indices],
                weights[train_indices],
            )
            probabilities[validation_indices] = fitted.predict_proba(
                features[validation_indices]
            )[:, 1]
            fold_scores.append(
                balanced_accuracy_score(
                    targets[validation_indices],
                    probabilities[validation_indices] >= 0.5,
                )
            )
        score = float(balanced_accuracy_score(targets, probabilities >= 0.5))
        results.append(
            {
                "name": name,
                "pooled_balanced_accuracy": score,
                "mean_fold_balanced_accuracy": float(np.mean(fold_scores)),
                "standard_deviation": float(np.std(fold_scores, ddof=1)),
                "fold_scores": [float(value) for value in fold_scores],
            }
        )
        if selected is None or score > selected[0]:
            selected = (score, name, candidate)
            selected_oof = probabilities
    if selected is None or selected_oof is None:
        raise AITemporalV7Error("No V7 development model was selected.")
    raw = np.clip(selected_oof, 1e-6, 1 - 1e-6)
    logits = np.log(raw / (1 - raw)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1_000_000, max_iter=2000).fit(logits, targets)
    calibrated_oof = calibrator.predict_proba(logits)[:, 1]
    threshold = _select_threshold(targets, calibrated_oof)
    final_model = _fit(clone(selected[2]), features, targets, weights)
    development_metrics = {
        **compute_binary_metrics(
            [
                "moved_toward_pathogenic" if value else "moved_toward_benign"
                for value in targets
            ],
            [
                "moved_toward_pathogenic" if value else "moved_toward_benign"
                for value in calibrated_oof >= threshold
            ],
        ),
        "roc_auc": float(roc_auc_score(targets, calibrated_oof)),
        "average_precision": float(average_precision_score(targets, calibrated_oof)),
        "brier_score": float(brier_score_loss(targets, calibrated_oof)),
    }
    return (
        rows,
        identifiers,
        {
            "base_model": final_model,
            "calibrator": calibrator,
            "threshold": threshold,
            "feature_names": V7_FEATURE_NAMES,
        },
        {
            "candidate_results": results,
            "selected_model": selected[1],
            "selected_threshold": threshold,
            "out_of_fold_metrics": development_metrics,
        },
    )


def _features_from_predictor_row(
    row: Mapping[str, Any], scoring_config: Mapping[str, Any]
) -> tuple[float, ...]:
    prediction = score_older_snapshot(
        older_snapshot_from_row(row),
        config=scoring_config,
        frozen_config_sha256="V7 predictor-only adaptation of frozen V1 clue rules",
    )
    clue_map = {clue.clue: clue for clue in prediction.clues}
    binary = tuple(int(clue_map[name].applied) for name in FEATURE_NAMES[:9])
    age_clue = clue_map["classification_age"]
    age_days = 0
    if age_clue.available:
        age_days = int(
            age_clue.explanation.split(" days", maxsplit=1)[0].rsplit(" ", 1)[-1]
        )
    submitter_text = str(clue_map["multiple_agreeing_submitters"].older_value or "")
    submitters = [
        int(value)
        for value in submitter_text.replace(",", " ").split()
        if value.isdigit()
    ]
    maximum_submitters = max(submitters, default=0)
    completeness = str(clue_map["record_completeness"].older_value or "")
    missing_count = (
        0
        if completeness == "No core older fields missing"
        else len([value for value in completeness.split(",") if value.strip()])
    )
    return (
        *binary,
        int(age_clue.available),
        int(clue_map["record_completeness"].available),
        math.log1p(age_days),
        math.log1p(maximum_submitters),
        float(missing_count),
    )


def _create_prediction_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE predictions (
            variation_id TEXT PRIMARY KEY,
            allele_ids TEXT NOT NULL,
            gene_symbols TEXT,
            pathogenic_probability REAL NOT NULL,
            prediction TEXT NOT NULL,
            features_json TEXT NOT NULL
        );
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    return connection


def train_and_seal_v7_predictions(
    development_database: Path,
    predictor_index: Path,
    output_dir: Path,
    *,
    config_path: Path = AI_TEMPORAL_V7_CONFIG_PATH,
) -> dict[str, Any]:
    """Select V7 on development CV and seal all temporal predictions."""
    development_database = Path(development_database).resolve()
    predictor_index = Path(predictor_index).resolve()
    output_dir = Path(output_dir).resolve()
    config_path = Path(config_path).resolve()
    config = load_ai_temporal_v7_config(config_path)
    if output_dir.exists():
        raise FileExistsError(f"AI Temporal V7 outputs exist: {output_dir}")
    if _sha256(development_database) != config["development_source_database_sha256"]:
        raise AITemporalV7Error("The V7 development database hash does not match.")
    if _sha256(predictor_index) != config["predictor_index_sha256"]:
        raise AITemporalV7Error("The V7 predictor index hash does not match.")

    rows, training_ids, model_bundle, selection = _select_and_fit_model(
        development_database, config
    )
    scoring_config = load_clue_score_config(CLUE_SCORE_V1_PATH)
    scoring_config["prediction_date"] = config["prediction_snapshot_date"]
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        model_path = temporary / "model.joblib"
        joblib.dump(model_bundle, model_path)
        prediction_path = temporary / "sealed_candidate_predictions.sqlite3"
        output = _create_prediction_database(prediction_path)
        source = sqlite3.connect(f"file:{predictor_index}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        query = """
            SELECT current.*
            FROM variant_release AS current
            WHERE current.release_role='newer'
              AND current.clinical_significances='Uncertain significance'
              AND current.origin_simple_values='germline'
              AND current.variation_id GLOB '[0-9]*'
              AND NOT EXISTS (
                  SELECT 1 FROM variant_release AS old
                  WHERE old.release_role='older'
                    AND old.variation_id=current.variation_id
              )
            ORDER BY CAST(current.variation_id AS INTEGER)
        """
        pending: list[tuple[str, str, str | None, tuple[float, ...]]] = []
        candidate_count = 0
        overlap_count = 0

        def flush_predictions() -> None:
            if not pending:
                return
            probabilities = _calibrated_probabilities(
                model_bundle["base_model"],
                model_bundle["calibrator"],
                np.asarray([item[3] for item in pending], dtype=float),
            )
            records = []
            for item, probability in zip(pending, probabilities, strict=True):
                identifier, allele_ids, gene_symbols, features = item
                records.append(
                    (
                        identifier,
                        allele_ids,
                        gene_symbols,
                        float(probability),
                        "pathogenic"
                        if probability >= model_bundle["threshold"]
                        else "benign",
                        json.dumps(features),
                    )
                )
            output.executemany("INSERT INTO predictions VALUES (?,?,?,?,?,?)", records)
            output.commit()
            pending.clear()

        for raw_row in source.execute(query):
            row = dict(raw_row)
            identifier = str(row["variation_id"])
            if identifier in training_ids:
                overlap_count += 1
                continue
            features = _features_from_predictor_row(row, scoring_config)
            pending.append(
                (
                    identifier,
                    row["allele_ids"] or "",
                    row["gene_symbols"],
                    features,
                )
            )
            candidate_count += 1
            if len(pending) >= 5000:
                flush_predictions()
        flush_predictions()
        source.close()
        if overlap_count:
            raise AITemporalV7Error("Temporal candidates overlapped development IDs.")
        metadata = {
            "schema_version": 1,
            "experiment_version": config["experiment_version"],
            "state": "trained_temporal_predictions_sealed_answer_unopened",
            "trained_at_utc": datetime.now(UTC).isoformat(),
            "development_records": len(rows),
            "temporal_candidate_records": candidate_count,
            "development_candidate_variation_id_overlap": 0,
            "selected_model": selection["selected_model"],
            "selected_threshold": selection["selected_threshold"],
            "out_of_fold_metrics": selection["out_of_fold_metrics"],
            "candidate_results": selection["candidate_results"],
            "development_source_database_sha256": _sha256(development_database),
            "predictor_index_sha256": _sha256(predictor_index),
            "config_sha256": _sha256(config_path),
            "model_sha256": _sha256(model_path),
            "sklearn_version": sklearn.__version__,
        }
        for key, value in metadata.items():
            output.execute(
                "INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value))
            )
        output.commit()
        output.execute("VACUUM")
        output.close()
        metadata["sealed_predictions_sha256"] = _sha256(prediction_path)
        (temporary / "training_summary.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copyfile(config_path, temporary / "ai_temporal_v7.yaml")
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return metadata


def _normalised_values(value: str | None) -> set[str]:
    return {
        item.strip()
        for item in (value or "").replace(";", ",").split(",")
        if item.strip() and item.strip() != "-"
    }


def _stream_answers(
    answer_archive: Path, prediction_database: Path, working_database: Path
) -> dict[str, int]:
    shutil.copyfile(prediction_database, working_database)
    connection = sqlite3.connect(working_database)
    connection.executescript(
        """
        CREATE TABLE answer_rows (
            variation_id TEXT NOT NULL,
            allele_id TEXT,
            classification TEXT,
            origin_simple TEXT
        );
        CREATE INDEX answer_rows_id ON answer_rows(variation_id);
        """
    )
    candidate_ids = {
        row[0] for row in connection.execute("SELECT variation_id FROM predictions")
    }
    scanned = matched = 0
    batch = []
    with gzip.open(answer_archive, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"VariationID", "#AlleleID", "ClinicalSignificance", "OriginSimple"}
        if not required.issubset(reader.fieldnames or []):
            raise AITemporalV7Error("The V7 answer archive schema is incompatible.")
        for row in reader:
            scanned += 1
            identifier = row["VariationID"].strip()
            if identifier not in candidate_ids:
                continue
            batch.append(
                (
                    identifier,
                    row["#AlleleID"].strip(),
                    row["ClinicalSignificance"].strip(),
                    row["OriginSimple"].strip(),
                )
            )
            matched += 1
            if len(batch) >= 10000:
                connection.executemany(
                    "INSERT INTO answer_rows VALUES (?,?,?,?)", batch
                )
                connection.commit()
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO answer_rows VALUES (?,?,?,?)", batch)
    connection.commit()
    connection.close()
    return {"answer_rows_scanned": scanned, "candidate_answer_rows": matched}


def evaluate_v7_once(
    answer_archive: Path,
    output_dir: Path = AI_TEMPORAL_V7_RESULTS_DIR,
) -> dict[str, Any]:
    """Attach the frozen July 2026 answer and evaluate the sealed 1,000 once."""
    answer_archive = Path(answer_archive).resolve()
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "test_metrics.json"
    if metrics_path.exists():
        raise FileExistsError("The V7 temporal test was already evaluated.")
    config = load_ai_temporal_v7_config(output_dir / "ai_temporal_v7.yaml")
    if answer_archive.stat().st_size != config["answer_archive"]["expected_size_bytes"]:
        raise AITemporalV7Error("The July 2026 answer archive size does not match.")
    training = json.loads(
        (output_dir / "training_summary.json").read_text(encoding="utf-8")
    )
    prediction_path = output_dir / "sealed_candidate_predictions.sqlite3"
    if _sha256(prediction_path) != training["sealed_predictions_sha256"]:
        raise AITemporalV7Error("The sealed V7 predictions changed before evaluation.")
    working = output_dir / ".answer_working.sqlite3"
    stream_counts = _stream_answers(answer_archive, prediction_path, working)
    connection = sqlite3.connect(working)
    connection.row_factory = sqlite3.Row
    rows = []
    exclusions = Counter()
    matched_candidate_count = int(
        connection.execute(
            "SELECT COUNT(DISTINCT variation_id) FROM answer_rows"
        ).fetchone()[0]
    )
    query = """
        SELECT p.*, GROUP_CONCAT(DISTINCT a.allele_id) AS answer_allele_ids,
               GROUP_CONCAT(DISTINCT a.classification) AS answer_classifications,
               GROUP_CONCAT(DISTINCT a.origin_simple) AS answer_origins
        FROM predictions AS p
        JOIN answer_rows AS a USING (variation_id)
        GROUP BY p.variation_id
    """
    for row in connection.execute(query):
        predictor_alleles = _normalised_values(row["allele_ids"])
        answer_alleles = _normalised_values(row["answer_allele_ids"])
        if not predictor_alleles or predictor_alleles != answer_alleles:
            exclusions["allele_set_changed_or_missing"] += 1
            continue
        if _normalised_values(row["answer_origins"]) != {"germline"}:
            exclusions["answer_not_exclusively_germline"] += 1
            continue
        classifications = _normalised_values(row["answer_classifications"])
        if len(classifications) != 1:
            exclusions["ambiguous_aggregate_classification"] += 1
            continue
        classification = next(iter(classifications))
        outcome = normalize_newer_outcome(classification)
        if not outcome.scorable or outcome.group not in {
            "moved_toward_benign",
            "moved_toward_pathogenic",
        }:
            exclusions[outcome.reason_code] += 1
            continue
        rows.append(
            {
                "variation_id": row["variation_id"],
                "gene_symbols": row["gene_symbols"],
                "pathogenic_probability": float(row["pathogenic_probability"]),
                "prediction": row["prediction"],
                "actual_outcome": outcome.group,
                "answer_classification": classification,
            }
        )
    exclusions["missing_from_answer_snapshot"] = (
        training["temporal_candidate_records"] - matched_candidate_count
    )
    connection.close()
    working.unlink(missing_ok=True)
    if len(rows) < 1000:
        raise AITemporalV7Error(
            f"Only {len(rows)} safe clear temporal outcomes were available."
        )
    salt = config["final_test_salt"]
    selected = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"{salt}:{row['variation_id']}".encode()
        ).hexdigest(),
    )[:1000]
    actual = [row["actual_outcome"] for row in selected]
    predicted = [row["prediction"] for row in selected]
    standardized = compute_binary_metrics(actual, predicted)
    target_values = np.asarray(
        [int(value == "moved_toward_pathogenic") for value in actual]
    )
    probabilities = np.asarray(
        [row["pathogenic_probability"] for row in selected], dtype=float
    )
    metrics = {
        **standardized,
        "experiment_version": config["experiment_version"],
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "test_records": 1000,
        "safe_clear_outcomes_available": len(rows),
        "roc_auc": float(roc_auc_score(target_values, probabilities)),
        "average_precision": float(
            average_precision_score(target_values, probabilities)
        ),
        "brier_score": float(brier_score_loss(target_values, probabilities)),
        "answer_archive_sha256": _sha256(answer_archive),
        "sealed_predictions_sha256": training["sealed_predictions_sha256"],
        "development_test_variation_id_overlap": 0,
        "stream_counts": stream_counts,
        "exclusions": dict(exclusions),
        "design_warning": config["design_warning"],
    }
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "temporal_test_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=tuple(selected[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(selected)
    return metrics
