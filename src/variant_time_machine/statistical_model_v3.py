"""Learn older-only clue weights and evaluate once on a grouped holdout."""

import csv
import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

from variant_time_machine.config import STATISTICAL_MODEL_V3_CONFIG_PATH

FEATURE_NAMES = (
    "loss_of_function_consequence",
    "canonical_splice_consequence",
    "missense_consequence",
    "synonymous_consequence",
    "noncoding_consequence",
    "expert_panel_review",
    "multiple_agreeing_submitters",
    "criteria_without_conflict",
    "conflict_warning",
)
ALLOWED_OUTCOMES = {
    "moved_toward_benign": 0,
    "moved_toward_pathogenic": 1,
}
OUTPUT_FILENAMES = (
    "partition_manifest.json",
    "model.json",
    "held_out_predictions.csv",
    "metric_summary.json",
    "coefficients.csv",
    "statistical_model_v3.yaml",
    "experiment_report.md",
)


class StatisticalModelV3Error(ValueError):
    """Raised when the frozen V3 experiment contract is violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_sha256(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def load_statistical_model_v3_config(
    path: Path = STATISTICAL_MODEL_V3_CONFIG_PATH,
) -> dict[str, Any]:
    """Load and strictly validate the frozen V3 design."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatisticalModelV3Error(
            f"Could not load Statistical Model V3: {exc}"
        ) from exc
    if config.get("experiment_version") != "Statistical Model V3":
        raise StatisticalModelV3Error("Statistical Model V3 configuration is invalid.")
    if config.get("status") != "frozen":
        raise StatisticalModelV3Error("Statistical Model V3 must remain frozen.")
    if tuple(config.get("features", ())) != FEATURE_NAMES:
        raise StatisticalModelV3Error(
            "The frozen older-only feature allowlist changed."
        )
    if config.get("target") != ALLOWED_OUTCOMES:
        raise StatisticalModelV3Error("The frozen binary target mapping changed.")
    if config.get("partition", {}).get("algorithm") != "sha256_connected_gene_group":
        raise StatisticalModelV3Error("The frozen partition algorithm changed.")
    return config


def _gene_tokens(value: str) -> tuple[str, ...]:
    tokens = {
        token.strip().upper()
        for token in re.split(r"[,;|]", value or "")
        if token.strip() and token.strip() not in {"-", "NOT PROVIDED"}
    }
    return tuple(sorted(tokens))


def _read_feature_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        clues = json.loads(row["clues_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise StatisticalModelV3Error(
            f"Variation {row['variation_id']} has invalid older clue JSON."
        ) from exc
    clue_map: dict[str, Mapping[str, Any]] = {}
    for clue in clues:
        name = clue.get("clue")
        if name in clue_map:
            raise StatisticalModelV3Error(
                f"Variation {row['variation_id']} has duplicate clue {name}."
            )
        clue_map[name] = clue
    missing = set(FEATURE_NAMES) - set(clue_map)
    if missing:
        raise StatisticalModelV3Error(
            f"Variation {row['variation_id']} lacks clues: {sorted(missing)}"
        )
    outcome = row["outcome_group"]
    if outcome not in ALLOWED_OUTCOMES:
        raise StatisticalModelV3Error(f"Unsupported V3 outcome: {outcome}")
    return {
        "variation_id": str(row["variation_id"]),
        "gene_tokens": _gene_tokens(row["old_gene_symbols"]),
        "features": tuple(
            int(bool(clue_map[name].get("applied"))) for name in FEATURE_NAMES
        ),
        "target": ALLOWED_OUTCOMES[outcome],
        "outcome_group": outcome,
        "v2_predicted_direction": row["predicted_direction"],
    }


def load_source_rows(source_database: Path) -> list[dict[str, Any]]:
    """Read only the audited columns needed for features, grouping, and evaluation."""
    source_database = Path(source_database).resolve()
    if not source_database.is_file():
        raise FileNotFoundError(
            f"Resolved Direction V2 database is missing: {source_database}"
        )
    uri = f"file:{source_database}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(predictions)")
        }
        required = {
            "variation_id",
            "old_gene_symbols",
            "clues_json",
            "outcome_group",
            "predicted_direction",
        }
        if not required.issubset(columns):
            raise StatisticalModelV3Error(
                f"Resolved Direction V2 schema lacks: {sorted(required - columns)}"
            )
        rows = connection.execute(
            "SELECT variation_id,old_gene_symbols,clues_json,outcome_group,"
            "predicted_direction FROM predictions ORDER BY variation_sort"
        ).fetchall()
    if not rows:
        raise StatisticalModelV3Error("Resolved Direction V2 contains no rows.")
    return [_read_feature_row(row) for row in rows]


def _connected_group_keys(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def root(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = root(left), root(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for row in rows:
        tokens = row["gene_tokens"]
        for token in tokens:
            root(token)
        for token in tokens[1:]:
            union(tokens[0], token)

    members: dict[str, set[str]] = {}
    for token in parent:
        members.setdefault(root(token), set()).add(token)
    result: dict[str, str] = {}
    for row in rows:
        tokens = row["gene_tokens"]
        result[row["variation_id"]] = (
            "gene:" + "|".join(sorted(members[root(tokens[0])]))
            if tokens
            else f"variation:{row['variation_id']}"
        )
    return result


def build_partition(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> dict[str, Any]:
    """Create a deterministic, label-independent connected-gene partition."""
    group_keys = _connected_group_keys(rows)
    partition = config["partition"]
    cutoff = int(float(partition["test_fraction"]) * (1 << 256))
    assignments = []
    for row in sorted(rows, key=lambda item: item["variation_id"]):
        group_key = group_keys[row["variation_id"]]
        value = int(
            hashlib.sha256(f"{partition['salt']}:{group_key}".encode()).hexdigest(),
            16,
        )
        assignments.append(
            {
                "variation_id": row["variation_id"],
                "group_key": group_key,
                "partition": "test" if value < cutoff else "train",
            }
        )
    train_ids = [
        item["variation_id"] for item in assignments if item["partition"] == "train"
    ]
    test_ids = [
        item["variation_id"] for item in assignments if item["partition"] == "test"
    ]
    if not train_ids or not test_ids:
        raise StatisticalModelV3Error("The grouped split produced an empty partition.")
    train_groups = {
        item["group_key"] for item in assignments if item["partition"] == "train"
    }
    test_groups = {
        item["group_key"] for item in assignments if item["partition"] == "test"
    }
    if train_groups & test_groups:
        raise StatisticalModelV3Error("A connected gene group crossed partitions.")
    return {
        "schema_version": 1,
        "algorithm": partition["algorithm"],
        "group_rule": partition["group_rule"],
        "salt": partition["salt"],
        "test_fraction": partition["test_fraction"],
        "record_count": len(assignments),
        "train_count": len(train_ids),
        "test_count": len(test_ids),
        "train_group_count": len(train_groups),
        "test_group_count": len(test_groups),
        "assignments": assignments,
    }


def _fit(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> LogisticRegression:
    features = np.asarray([row["features"] for row in rows], dtype=float)
    targets = np.asarray([row["target"] for row in rows], dtype=int)
    if len(set(targets.tolist())) != 2:
        raise StatisticalModelV3Error("Training partition must contain both outcomes.")
    estimator = config["estimator"]
    model = LogisticRegression(
        C=float(estimator["C"]),
        class_weight=estimator["class_weight"],
        solver=estimator["solver"],
        max_iter=int(estimator["max_iter"]),
        random_state=int(estimator["random_state"]),
    )
    model.fit(features, targets)
    return model


def _metrics(
    targets: np.ndarray, probabilities: np.ndarray, predictions: np.ndarray
) -> dict[str, Any]:
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    return {
        "records": int(len(targets)),
        "actual_benign": int((targets == 0).sum()),
        "actual_pathogenic": int((targets == 1).sum()),
        "predicted_benign": int((predictions == 0).sum()),
        "predicted_pathogenic": int((predictions == 1).sum()),
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "benign_precision": float(
            precision_score(targets, predictions, pos_label=0, zero_division=0)
        ),
        "pathogenic_precision": float(
            precision_score(targets, predictions, pos_label=1, zero_division=0)
        ),
        "benign_recall": float(
            recall_score(targets, predictions, pos_label=0, zero_division=0)
        ),
        "pathogenic_recall": float(
            recall_score(targets, predictions, pos_label=1, zero_division=0)
        ),
        "roc_auc": float(roc_auc_score(targets, probabilities)),
        "average_precision_pathogenic": float(
            average_precision_score(targets, probabilities)
        ),
        "brier_score": float(brier_score_loss(targets, probabilities)),
        "confusion_matrix": {
            "actual_benign": {
                "predicted_benign": int(matrix[0, 0]),
                "predicted_pathogenic": int(matrix[0, 1]),
            },
            "actual_pathogenic": {
                "predicted_benign": int(matrix[1, 0]),
                "predicted_pathogenic": int(matrix[1, 1]),
            },
        },
    }


def _write_outputs(
    output_dir: Path,
    config: Mapping[str, Any],
    config_path: Path,
    manifest: Mapping[str, Any],
    model_document: Mapping[str, Any],
    test_rows: Sequence[Mapping[str, Any]],
    probabilities: np.ndarray,
    predictions: np.ndarray,
    metrics: Mapping[str, Any],
) -> None:
    (output_dir / "partition_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "model.json").write_text(
        json.dumps(model_document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "metric_summary.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(config_path, output_dir / "statistical_model_v3.yaml")
    with (output_dir / "coefficients.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(("feature", "coefficient", "odds_ratio"))
        for feature, coefficient in model_document["coefficients"].items():
            writer.writerow((feature, coefficient, math.exp(coefficient)))
    with (output_dir / "held_out_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "variation_id",
                "actual_outcome",
                "pathogenic_probability",
                "predicted_outcome",
            )
        )
        for row, probability, prediction in zip(
            test_rows, probabilities, predictions, strict=True
        ):
            writer.writerow(
                (
                    row["variation_id"],
                    row["outcome_group"],
                    float(probability),
                    "moved_toward_pathogenic" if prediction else "moved_toward_benign",
                )
            )

    def percent(value: float) -> str:
        return f"{value:.1%}"

    coefficients = sorted(
        model_document["coefficients"].items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    coefficient_lines = "\n".join(
        f"- `{name}`: {value:+.4f} (odds ratio {math.exp(value):.3f})"
        for name, value in coefficients
    )
    report = f"""# Statistical Model V3 Results

Generated: {metrics["completed_at_utc"]}

## Design

Logistic regression learned all clue coefficients from {metrics["train_records"]:,}
training records. A deterministic connected-gene SHA-256 split kept
{metrics["test_records"]:,} records held out until this evaluation. Model inputs are
only binary older-snapshot clue indicators; assigned points, scores, predictions,
newer fields, and outcomes were not model features.

## Held-Out Results

- Accuracy: {percent(metrics["accuracy"])}
- Balanced accuracy: {percent(metrics["balanced_accuracy"])}
- Pathogenic precision: {percent(metrics["pathogenic_precision"])}
- Benign precision: {percent(metrics["benign_precision"])}
- Pathogenic recall: {percent(metrics["pathogenic_recall"])}
- Benign recall: {percent(metrics["benign_recall"])}
- ROC AUC: {metrics["roc_auc"]:.3f}
- Pathogenic average precision: {metrics["average_precision_pathogenic"]:.3f}
- Brier score: {metrics["brier_score"]:.3f}

## Learned Coefficients

Positive coefficients point toward pathogenic resolution and negative coefficients
point toward benign resolution, conditional on the other included indicators.

{coefficient_lines}

## Limitation

This is a conditional internal holdout from the already inspected Version 2 cohort.
It does not predict whether a VUS will resolve and is not independent temporal,
clinical, or medical validation.
"""
    (output_dir / "experiment_report.md").write_text(report, encoding="utf-8")


def run_statistical_model_v3(
    source_database: Path,
    output_dir: Path,
    *,
    config_path: Path = STATISTICAL_MODEL_V3_CONFIG_PATH,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Fit on training groups and evaluate the frozen model on held-out groups."""
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    config_path = Path(config_path).resolve()
    config = load_statistical_model_v3_config(config_path)
    source_hash = _sha256(source_database)
    if source_hash != config["source_database_sha256"]:
        raise StatisticalModelV3Error(
            "Resolved Direction V2 source hash does not match the frozen design."
        )
    if output_dir.exists() and not overwrite:
        raise FileExistsError(f"Statistical Model V3 outputs exist: {output_dir}")

    rows = load_source_rows(source_database)
    manifest = build_partition(rows, config)
    manifest = {
        **manifest,
        "source_database_sha256": source_hash,
        "config_sha256": _sha256(config_path),
    }
    manifest["manifest_sha256"] = _document_sha256(manifest)
    assignment = {
        item["variation_id"]: item["partition"] for item in manifest["assignments"]
    }
    train_rows = [row for row in rows if assignment[row["variation_id"]] == "train"]
    test_rows = [row for row in rows if assignment[row["variation_id"]] == "test"]
    model = _fit(train_rows, config)
    test_features = np.asarray([row["features"] for row in test_rows], dtype=float)
    targets = np.asarray([row["target"] for row in test_rows], dtype=int)
    probabilities = model.predict_proba(test_features)[:, 1]
    threshold = float(config["estimator"]["decision_threshold"])
    predictions = (probabilities >= threshold).astype(int)
    completed = datetime.now(UTC).isoformat()
    metrics = {
        **_metrics(targets, probabilities, predictions),
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "conditional_task": True,
        "train_records": len(train_rows),
        "test_records": len(test_rows),
        "completed_at_utc": completed,
        "source_database_sha256": source_hash,
        "config_sha256": manifest["config_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "design_warning": config["design_warning"],
    }
    model_document = {
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "features": list(FEATURE_NAMES),
        "coefficients": dict(zip(FEATURE_NAMES, model.coef_[0].tolist(), strict=True)),
        "intercept": float(model.intercept_[0]),
        "classes": model.classes_.tolist(),
        "estimator": config["estimator"],
        "sklearn_version": sklearn.__version__,
        "source_database_sha256": source_hash,
        "config_sha256": manifest["config_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "trained_records": len(train_rows),
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        _write_outputs(
            temporary,
            config,
            config_path,
            manifest,
            model_document,
            test_rows,
            probabilities,
            predictions,
            metrics,
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return metrics
