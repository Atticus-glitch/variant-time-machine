"""Train a neural classifier, then test it once on 100 unseen records."""

import csv
import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.neural_network import MLPClassifier

from variant_time_machine.config import (
    AI_HOLDOUT_V4_CONFIG_PATH,
    AI_HOLDOUT_V4_RESULTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)
from variant_time_machine.statistical_model_v3 import _connected_group_keys

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
    "classification_age",
    "record_completeness",
)
TARGETS = {"moved_toward_benign": 0, "moved_toward_pathogenic": 1}


class AIHoldoutV4Error(ValueError):
    """Raised when the frozen V4 training or test contract is violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    content = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(content).hexdigest()


def load_ai_holdout_v4_config(
    path: Path = AI_HOLDOUT_V4_CONFIG_PATH,
) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIHoldoutV4Error(f"Could not load AI Holdout V4: {exc}") from exc
    if config.get("experiment_version") != "AI Holdout V4":
        raise AIHoldoutV4Error("AI Holdout V4 configuration is invalid.")
    if config.get("status") != "frozen":
        raise AIHoldoutV4Error("AI Holdout V4 must remain frozen.")
    if tuple(config.get("features", ())) != FEATURE_NAMES:
        raise AIHoldoutV4Error("The frozen all-hint feature list changed.")
    if config.get("target") != TARGETS:
        raise AIHoldoutV4Error("The frozen target mapping changed.")
    if config.get("partition", {}).get("holdout_records") != 100:
        raise AIHoldoutV4Error("AI Holdout V4 requires exactly 100 test records.")
    return config


def _gene_tokens(value: str) -> tuple[str, ...]:
    cleaned = (value or "").replace(";", ",").replace("|", ",")
    return tuple(
        sorted(
            {
                token.strip().upper()
                for token in cleaned.split(",")
                if token.strip() and token.strip() not in {"-", "NOT PROVIDED"}
            }
        )
    )


def _source_rows(source_database: Path) -> list[dict[str, Any]]:
    uri = f"file:{Path(source_database).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT variation_id,old_gene_symbols,clues_json,outcome_group,"
            "predicted_direction FROM predictions ORDER BY variation_sort"
        ).fetchall()
    result = []
    for row in rows:
        clues = json.loads(row["clues_json"])
        clue_map = {clue["clue"]: clue for clue in clues}
        if set(FEATURE_NAMES) - set(clue_map):
            raise AIHoldoutV4Error(
                f"Variation {row['variation_id']} lacks one or more frozen hints."
            )
        outcome = row["outcome_group"]
        if outcome not in TARGETS:
            raise AIHoldoutV4Error(f"Unsupported outcome: {outcome}")
        result.append(
            {
                "variation_id": str(row["variation_id"]),
                "gene_tokens": _gene_tokens(row["old_gene_symbols"]),
                "features": tuple(
                    int(bool(clue_map[name].get("applied"))) for name in FEATURE_NAMES
                ),
                "target": TARGETS[outcome],
                "outcome_group": outcome,
                "v2_predicted_direction": row["predicted_direction"],
            }
        )
    if not result:
        raise AIHoldoutV4Error("Resolved Direction V2 has no eligible rows.")
    return result


def build_100_record_partition(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> dict[str, Any]:
    """Select exactly 100 test records without consulting any outcome label."""
    group_keys = _connected_group_keys(rows)
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(group_keys[row["variation_id"]], []).append(
            row["variation_id"]
        )
    partition = config["partition"]
    count = int(partition["holdout_records"])
    salt = partition["salt"]
    if len(groups) < count:
        raise AIHoldoutV4Error("There are fewer than 100 independent gene groups.")
    selected_groups = set(
        sorted(
            groups,
            key=lambda group: hashlib.sha256(
                f"{salt}:group:{group}".encode()
            ).hexdigest(),
        )[:count]
    )
    representatives = {
        group: min(
            groups[group],
            key=lambda identifier: hashlib.sha256(
                f"{salt}:record:{group}:{identifier}".encode()
            ).hexdigest(),
        )
        for group in selected_groups
    }
    assignments = []
    for row in sorted(rows, key=lambda item: item["variation_id"]):
        identifier = row["variation_id"]
        group = group_keys[identifier]
        split = (
            "train"
            if group not in selected_groups
            else "test"
            if representatives[group] == identifier
            else "quarantine"
        )
        assignments.append(
            {"variation_id": identifier, "group_key": group, "partition": split}
        )
    test = [item for item in assignments if item["partition"] == "test"]
    train_groups = {
        item["group_key"] for item in assignments if item["partition"] == "train"
    }
    test_groups = {item["group_key"] for item in test}
    if len(test) != count or train_groups & test_groups:
        raise AIHoldoutV4Error("The 100-record holdout contract was violated.")
    return {
        "schema_version": 1,
        "algorithm": partition["algorithm"],
        "group_rule": partition["group_rule"],
        "salt": salt,
        "record_count": len(assignments),
        "train_count": sum(item["partition"] == "train" for item in assignments),
        "test_count": len(test),
        "quarantine_count": sum(
            item["partition"] == "quarantine" for item in assignments
        ),
        "assignments": assignments,
    }


def train_ai_holdout_v4(
    source_database: Path,
    output_dir: Path,
    *,
    config_path: Path = AI_HOLDOUT_V4_CONFIG_PATH,
) -> dict[str, Any]:
    """Train without reading the 100 held-out targets into the estimator."""
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    config_path = Path(config_path).resolve()
    config = load_ai_holdout_v4_config(config_path)
    if output_dir.exists():
        raise FileExistsError(f"AI Holdout V4 outputs exist: {output_dir}")
    source_hash = _sha256(source_database)
    if source_hash != config["source_database_sha256"]:
        raise AIHoldoutV4Error("The V2 source database does not match the frozen hash.")
    rows = _source_rows(source_database)
    manifest = build_100_record_partition(rows, config)
    manifest.update(
        source_database_sha256=source_hash,
        config_sha256=_sha256(config_path),
    )
    manifest["manifest_sha256"] = _document_hash(manifest)
    split = {
        item["variation_id"]: item["partition"] for item in manifest["assignments"]
    }
    training = [row for row in rows if split[row["variation_id"]] == "train"]
    estimator = config["estimator"]
    model = MLPClassifier(
        hidden_layer_sizes=tuple(estimator["hidden_layer_sizes"]),
        activation=estimator["activation"],
        solver=estimator["solver"],
        alpha=float(estimator["alpha"]),
        batch_size=int(estimator["batch_size"]),
        learning_rate_init=float(estimator["learning_rate_init"]),
        max_iter=int(estimator["max_iter"]),
        early_stopping=bool(estimator["early_stopping"]),
        validation_fraction=float(estimator["validation_fraction"]),
        n_iter_no_change=int(estimator["n_iter_no_change"]),
        random_state=int(estimator["random_state"]),
    )
    model.fit(
        np.asarray([row["features"] for row in training], dtype=float),
        np.asarray([row["target"] for row in training], dtype=int),
    )
    trained = datetime.now(UTC).isoformat()
    metadata = {
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "state": "trained_hidden_test_unopened",
        "trained_at_utc": trained,
        "training_records": len(training),
        "hidden_test_records": manifest["test_count"],
        "quarantined_records": manifest["quarantine_count"],
        "feature_count": len(FEATURE_NAMES),
        "features": list(FEATURE_NAMES),
        "training_iterations": int(model.n_iter_),
        "final_training_loss": float(model.loss_),
        "source_database_sha256": source_hash,
        "config_sha256": manifest["config_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "sklearn_version": sklearn.__version__,
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        joblib.dump(model, temporary / "model.joblib")
        (temporary / "partition_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (temporary / "training_summary.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copyfile(config_path, temporary / "ai_holdout_v4.yaml")
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return metadata


def ai_holdout_v4_summary(
    output_dir: Path = AI_HOLDOUT_V4_RESULTS_DIR,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    training_path = output_dir / "training_summary.json"
    if not training_path.is_file():
        return {"available": False, "state": "not_trained"}
    summary = json.loads(training_path.read_text(encoding="utf-8"))
    metrics_path = output_dir / "test_metrics.json"
    if metrics_path.is_file():
        summary.update(json.loads(metrics_path.read_text(encoding="utf-8")))
        summary["state"] = "tested"
    return {"available": True, **summary}


def test_ai_holdout_v4_once(
    source_database: Path = RESOLVED_DIRECTION_RESULTS_DB_PATH,
    output_dir: Path = AI_HOLDOUT_V4_RESULTS_DIR,
) -> dict[str, Any]:
    """Open the hidden 100 once and save the model's untouched-test accuracy."""
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "test_metrics.json"
    if metrics_path.exists():
        raise FileExistsError("The hidden 100-record test has already been evaluated.")
    config = load_ai_holdout_v4_config(output_dir / "ai_holdout_v4.yaml")
    manifest = json.loads(
        (output_dir / "partition_manifest.json").read_text(encoding="utf-8")
    )
    if _sha256(source_database) != manifest["source_database_sha256"]:
        raise AIHoldoutV4Error("The source database changed after training.")
    rows = _source_rows(source_database)
    test_ids = {
        item["variation_id"]
        for item in manifest["assignments"]
        if item["partition"] == "test"
    }
    test_rows = [row for row in rows if row["variation_id"] in test_ids]
    if len(test_rows) != 100:
        raise AIHoldoutV4Error(
            "The hidden test no longer contains exactly 100 records."
        )
    model = joblib.load(output_dir / "model.joblib")
    features = np.asarray([row["features"] for row in test_rows], dtype=float)
    targets = np.asarray([row["target"] for row in test_rows], dtype=int)
    probabilities = model.predict_proba(features)[:, 1]
    predictions = (
        probabilities >= float(config["estimator"]["decision_threshold"])
    ).astype(int)
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    metrics = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "test_records": 100,
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "actual_benign": int((targets == 0).sum()),
        "actual_pathogenic": int((targets == 1).sum()),
        "correct": int((targets == predictions).sum()),
        "wrong": int((targets != predictions).sum()),
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
        "design_warning": config["design_warning"],
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_dir, delete=False
    ) as temporary:
        json.dump(metrics, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(metrics_path)
    with (output_dir / "hidden_test_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(
            ("variation_id", "actual_outcome", "pathogenic_probability", "prediction")
        )
        for row, probability, prediction in zip(
            test_rows, probabilities, predictions, strict=True
        ):
            writer.writerow(
                (
                    row["variation_id"],
                    row["outcome_group"],
                    float(probability),
                    "pathogenic" if prediction else "benign",
                )
            )
    return metrics
