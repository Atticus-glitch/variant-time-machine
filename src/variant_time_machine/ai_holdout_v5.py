"""Train a richer neural classifier with a fresh 100-record holdout."""

import csv
import hashlib
import json
import re
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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from variant_time_machine.ai_holdout_v4 import (
    TARGETS,
    _connected_group_keys,
    _document_hash,
    _gene_tokens,
    _sha256,
)
from variant_time_machine.config import (
    AI_HOLDOUT_V5_CONFIG_PATH,
    AI_HOLDOUT_V5_RESULTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)

CLUE_NAMES = (
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
FEATURE_NAMES = (
    *CLUE_NAMES[:9],
    "classification_age_available",
    "record_completeness_available",
    "classification_age_days",
    "maximum_submitter_count",
    "missing_core_field_count",
)


class AIHoldoutV5Error(ValueError):
    """Raised when the frozen V5 experiment contract is violated."""


def load_ai_holdout_v5_config(
    path: Path = AI_HOLDOUT_V5_CONFIG_PATH,
) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIHoldoutV5Error(f"Could not load AI Holdout V5: {exc}") from exc
    if config.get("experiment_version") != "AI Holdout V5":
        raise AIHoldoutV5Error("AI Holdout V5 configuration is invalid.")
    if config.get("status") != "frozen":
        raise AIHoldoutV5Error("AI Holdout V5 must remain frozen.")
    if tuple(config.get("features", ())) != FEATURE_NAMES:
        raise AIHoldoutV5Error("The frozen richer feature list changed.")
    if config.get("target") != TARGETS:
        raise AIHoldoutV5Error("The frozen target mapping changed.")
    if config.get("partition", {}).get("holdout_records") != 100:
        raise AIHoldoutV5Error("AI Holdout V5 requires exactly 100 test records.")
    return config


def _numeric_features(clue_map: Mapping[str, Mapping[str, Any]]) -> tuple[float, ...]:
    age_clue = clue_map["classification_age"]
    age_match = re.search(r"(\d+) days", str(age_clue.get("explanation", "")))
    age_days = float(age_match.group(1)) if age_match else 0.0
    submitter_text = str(
        clue_map["multiple_agreeing_submitters"].get("older_value", "")
    )
    submitters = [int(value) for value in re.findall(r"\d+", submitter_text)]
    maximum_submitters = float(max(submitters)) if submitters else 0.0
    completeness = str(clue_map["record_completeness"].get("older_value", ""))
    missing_count = (
        0.0
        if completeness == "No core older fields missing"
        else float(len([value for value in completeness.split(",") if value.strip()]))
    )
    return age_days, maximum_submitters, missing_count


def _source_rows(source_database: Path) -> list[dict[str, Any]]:
    uri = f"file:{Path(source_database).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT variation_id,old_gene_symbols,clues_json,outcome_group "
            "FROM predictions ORDER BY variation_sort"
        ).fetchall()
    result = []
    for row in rows:
        clues = json.loads(row["clues_json"])
        clue_map = {clue["clue"]: clue for clue in clues}
        if set(CLUE_NAMES) - set(clue_map):
            raise AIHoldoutV5Error(f"Variation {row['variation_id']} lacks V5 hints.")
        outcome = row["outcome_group"]
        if outcome not in TARGETS:
            raise AIHoldoutV5Error(f"Unsupported outcome: {outcome}")
        binary = tuple(int(bool(clue_map[name].get("applied"))) for name in CLUE_NAMES)
        result.append(
            {
                "variation_id": str(row["variation_id"]),
                "gene_tokens": _gene_tokens(row["old_gene_symbols"]),
                "features": (*binary, *_numeric_features(clue_map)),
                "target": TARGETS[outcome],
                "outcome_group": outcome,
            }
        )
    return result


def build_fresh_100_partition(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    previous_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Select a fresh exact 100 without labels or prior test-group reuse."""
    if (
        previous_manifest.get("manifest_sha256")
        != config["previous_holdout_manifest_sha256"]
    ):
        raise AIHoldoutV5Error("The frozen V4 holdout manifest does not match.")
    group_keys = _connected_group_keys(rows)
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(group_keys[row["variation_id"]], []).append(
            row["variation_id"]
        )
    previous_test_groups = {
        item["group_key"]
        for item in previous_manifest["assignments"]
        if item["partition"] == "test"
    }
    partition = config["partition"]
    maximum_size = int(partition["maximum_holdout_group_size"])
    candidates = [
        group
        for group, identifiers in groups.items()
        if len(identifiers) <= maximum_size and group not in previous_test_groups
    ]
    count = int(partition["holdout_records"])
    salt = partition["salt"]
    if len(candidates) < count:
        raise AIHoldoutV5Error("There are fewer than 100 eligible fresh groups.")
    selected_groups = set(
        sorted(
            candidates,
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
    test_groups = {item["group_key"] for item in test}
    if len(test) != 100 or test_groups & previous_test_groups:
        raise AIHoldoutV5Error("The fresh 100-record holdout contract was violated.")
    return {
        "schema_version": 1,
        "algorithm": partition["algorithm"],
        "group_rule": partition["group_rule"],
        "salt": salt,
        "record_count": len(assignments),
        "train_count": sum(item["partition"] == "train" for item in assignments),
        "test_count": 100,
        "quarantine_count": sum(
            item["partition"] == "quarantine" for item in assignments
        ),
        "previous_test_group_count": len(previous_test_groups),
        "assignments": assignments,
    }


def _balanced_training_arrays(
    rows: Sequence[Mapping[str, Any]], random_state: int
) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray([row["features"] for row in rows], dtype=float)
    targets = np.asarray([row["target"] for row in rows], dtype=int)
    indices = [np.flatnonzero(targets == value) for value in (0, 1)]
    if not all(len(value) for value in indices):
        raise AIHoldoutV5Error("V5 training requires both outcomes.")
    maximum = max(len(value) for value in indices)
    generator = np.random.default_rng(random_state)
    balanced = np.concatenate(
        [generator.choice(value, size=maximum, replace=True) for value in indices]
    )
    generator.shuffle(balanced)
    return features[balanced], targets[balanced]


def train_ai_holdout_v5(
    source_database: Path,
    output_dir: Path,
    previous_manifest_path: Path,
    *,
    config_path: Path = AI_HOLDOUT_V5_CONFIG_PATH,
) -> dict[str, Any]:
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    config_path = Path(config_path).resolve()
    config = load_ai_holdout_v5_config(config_path)
    if output_dir.exists():
        raise FileExistsError(f"AI Holdout V5 outputs exist: {output_dir}")
    source_hash = _sha256(source_database)
    if source_hash != config["source_database_sha256"]:
        raise AIHoldoutV5Error("The V2 source database does not match V5.")
    previous_manifest = json.loads(
        Path(previous_manifest_path).read_text(encoding="utf-8")
    )
    rows = _source_rows(source_database)
    manifest = build_fresh_100_partition(rows, config, previous_manifest)
    manifest.update(
        source_database_sha256=source_hash, config_sha256=_sha256(config_path)
    )
    manifest["manifest_sha256"] = _document_hash(manifest)
    split = {
        item["variation_id"]: item["partition"] for item in manifest["assignments"]
    }
    training = [row for row in rows if split[row["variation_id"]] == "train"]
    estimator = config["estimator"]
    features, targets = _balanced_training_arrays(
        training, int(estimator["random_state"])
    )
    model = Pipeline(
        (
            ("scale", StandardScaler()),
            (
                "network",
                MLPClassifier(
                    hidden_layer_sizes=tuple(estimator["hidden_layer_sizes"]),
                    activation=estimator["activation"],
                    solver=estimator["solver"],
                    alpha=float(estimator["alpha"]),
                    batch_size=int(estimator["batch_size"]),
                    learning_rate_init=float(estimator["learning_rate_init"]),
                    max_iter=int(estimator["max_iter"]),
                    early_stopping=bool(estimator["early_stopping"]),
                    random_state=int(estimator["random_state"]),
                ),
            ),
        )
    )
    model.fit(features, targets)
    network = model.named_steps["network"]
    metadata = {
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "state": "trained_hidden_test_unopened",
        "trained_at_utc": datetime.now(UTC).isoformat(),
        "training_records": len(training),
        "effective_balanced_training_rows": len(targets),
        "hidden_test_records": 100,
        "quarantined_records": manifest["quarantine_count"],
        "feature_count": len(FEATURE_NAMES),
        "features": list(FEATURE_NAMES),
        "training_iterations": int(network.n_iter_),
        "final_training_loss": float(network.loss_),
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
        shutil.copyfile(config_path, temporary / "ai_holdout_v5.yaml")
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return metadata


def ai_holdout_v5_summary(
    output_dir: Path = AI_HOLDOUT_V5_RESULTS_DIR,
) -> dict[str, Any]:
    training_path = Path(output_dir) / "training_summary.json"
    if not training_path.is_file():
        return {"available": False, "state": "not_trained"}
    summary = json.loads(training_path.read_text(encoding="utf-8"))
    metrics_path = Path(output_dir) / "test_metrics.json"
    if metrics_path.is_file():
        summary.update(json.loads(metrics_path.read_text(encoding="utf-8")))
        summary["state"] = "tested"
    return {"available": True, **summary}


def test_ai_holdout_v5_once(
    source_database: Path = RESOLVED_DIRECTION_RESULTS_DB_PATH,
    output_dir: Path = AI_HOLDOUT_V5_RESULTS_DIR,
) -> dict[str, Any]:
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "test_metrics.json"
    if metrics_path.exists():
        raise FileExistsError("The V5 hidden 100-record test was already evaluated.")
    config = load_ai_holdout_v5_config(output_dir / "ai_holdout_v5.yaml")
    manifest = json.loads(
        (output_dir / "partition_manifest.json").read_text(encoding="utf-8")
    )
    if _sha256(source_database) != manifest["source_database_sha256"]:
        raise AIHoldoutV5Error("The source database changed after V5 training.")
    test_ids = {
        item["variation_id"]
        for item in manifest["assignments"]
        if item["partition"] == "test"
    }
    test_rows = [
        row for row in _source_rows(source_database) if row["variation_id"] in test_ids
    ]
    if len(test_rows) != 100:
        raise AIHoldoutV5Error(
            "The V5 hidden test does not contain exactly 100 records."
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
    temporary = output_dir / ".test_metrics.tmp"
    temporary.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(metrics_path)
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
