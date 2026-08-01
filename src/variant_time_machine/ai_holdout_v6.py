"""Train and evaluate the frozen 1,000-record AI Holdout V6."""

import csv
import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from variant_time_machine.ai_holdout_v4 import (
    TARGETS,
    _connected_group_keys,
    _document_hash,
    _sha256,
)
from variant_time_machine.ai_holdout_v5 import (
    FEATURE_NAMES,
    _balanced_training_arrays,
    _source_rows,
)
from variant_time_machine.config import (
    AI_HOLDOUT_V6_CONFIG_PATH,
    AI_HOLDOUT_V6_RESULTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)


class AIHoldoutV6Error(ValueError):
    """Raised when the frozen V6 experiment contract is violated."""


def load_ai_holdout_v6_config(
    path: Path = AI_HOLDOUT_V6_CONFIG_PATH,
) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIHoldoutV6Error(f"Could not load AI Holdout V6: {exc}") from exc
    if config.get("experiment_version") != "AI Holdout V6":
        raise AIHoldoutV6Error("AI Holdout V6 configuration is invalid.")
    if config.get("status") != "frozen":
        raise AIHoldoutV6Error("AI Holdout V6 must remain frozen.")
    if tuple(config.get("features", ())) != FEATURE_NAMES:
        raise AIHoldoutV6Error("The frozen V6 feature list changed.")
    if config.get("target") != TARGETS:
        raise AIHoldoutV6Error("The frozen target mapping changed.")
    if config.get("partition", {}).get("holdout_records") != 1000:
        raise AIHoldoutV6Error("AI Holdout V6 requires exactly 1,000 test records.")
    return config


def _verified_previous_groups(
    manifests: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any]
) -> set[str]:
    expected = config["previous_holdout_manifest_sha256"]
    groups: set[str] = set()
    for model_id in ("V4", "V5"):
        manifest = dict(manifests[model_id])
        stored_hash = manifest.pop("manifest_sha256", None)
        if stored_hash != expected[model_id] or _document_hash(manifest) != stored_hash:
            raise AIHoldoutV6Error(f"The frozen {model_id} manifest does not match.")
        groups.update(
            item["group_key"]
            for item in manifest["assignments"]
            if item["partition"] == "test"
        )
    return groups


def build_fresh_1000_partition(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    previous_manifests: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Select 1,000 label-independent groups and exclude all prior test groups."""
    group_keys = _connected_group_keys(rows)
    groups: dict[str, list[str]] = {}
    for row in rows:
        identifier = str(row["variation_id"])
        groups.setdefault(group_keys[identifier], []).append(identifier)
    previous_groups = _verified_previous_groups(previous_manifests, config)
    candidates = sorted(set(groups) - previous_groups)
    count = int(config["partition"]["holdout_records"])
    salt = str(config["partition"]["salt"])
    if len(candidates) < count:
        raise AIHoldoutV6Error(
            f"Only {len(candidates)} fresh groups are available for 1,000 tests."
        )
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
    for row in sorted(rows, key=lambda item: str(item["variation_id"])):
        identifier = str(row["variation_id"])
        group = group_keys[identifier]
        if group in previous_groups:
            partition = "prior_holdout_excluded"
        elif group not in selected_groups:
            partition = "train"
        elif representatives[group] == identifier:
            partition = "test"
        else:
            partition = "quarantine"
        assignments.append(
            {"variation_id": identifier, "group_key": group, "partition": partition}
        )

    by_partition = {
        name: [item for item in assignments if item["partition"] == name]
        for name in ("train", "test", "quarantine", "prior_holdout_excluded")
    }
    train_ids = {item["variation_id"] for item in by_partition["train"]}
    test_ids = {item["variation_id"] for item in by_partition["test"]}
    train_groups = {item["group_key"] for item in by_partition["train"]}
    test_groups = {item["group_key"] for item in by_partition["test"]}
    if len(test_ids) != 1000:
        raise AIHoldoutV6Error("The V6 holdout does not contain exactly 1,000 records.")
    if train_ids & test_ids or train_groups & test_groups:
        raise AIHoldoutV6Error("V6 training and test membership overlap.")
    if (train_groups | test_groups) & previous_groups:
        raise AIHoldoutV6Error("A prior V4/V5 test group entered V6 training or test.")
    return {
        "schema_version": 1,
        "algorithm": config["partition"]["algorithm"],
        "group_rule": config["partition"]["group_rule"],
        "salt": salt,
        "record_count": len(assignments),
        "fresh_group_count": len(candidates),
        "selected_test_group_count": len(test_groups),
        "prior_test_group_count": len(previous_groups),
        "train_count": len(by_partition["train"]),
        "test_count": len(by_partition["test"]),
        "quarantine_count": len(by_partition["quarantine"]),
        "prior_holdout_excluded_count": len(by_partition["prior_holdout_excluded"]),
        "overlap_checks": {
            "train_test_variation_ids": 0,
            "train_test_connected_groups": 0,
            "v6_train_prior_test_groups": 0,
            "v6_test_prior_test_groups": 0,
        },
        "assignments": assignments,
    }


def train_ai_holdout_v6(
    source_database: Path,
    output_dir: Path,
    previous_manifest_paths: Mapping[str, Path],
    *,
    config_path: Path = AI_HOLDOUT_V6_CONFIG_PATH,
) -> dict[str, Any]:
    """Fit V6 only after its 1,000-record partition is fixed."""
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    config_path = Path(config_path).resolve()
    config = load_ai_holdout_v6_config(config_path)
    if output_dir.exists():
        raise FileExistsError(f"AI Holdout V6 outputs exist: {output_dir}")
    source_hash = _sha256(source_database)
    if source_hash != config["source_database_sha256"]:
        raise AIHoldoutV6Error("The V2 source database does not match frozen V6.")
    previous_manifests = {
        model_id: json.loads(Path(path).read_text(encoding="utf-8"))
        for model_id, path in previous_manifest_paths.items()
    }
    rows = _source_rows(source_database)
    manifest = build_fresh_1000_partition(rows, config, previous_manifests)
    manifest.update(
        source_database_sha256=source_hash, config_sha256=_sha256(config_path)
    )
    manifest["manifest_sha256"] = _document_hash(manifest)
    split = {
        item["variation_id"]: item["partition"] for item in manifest["assignments"]
    }
    training = [row for row in rows if split[str(row["variation_id"])] == "train"]
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
        "hidden_test_records": 1000,
        "quarantined_records": manifest["quarantine_count"],
        "prior_holdout_excluded_records": manifest["prior_holdout_excluded_count"],
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
        model_path = temporary / "model.joblib"
        joblib.dump(model, model_path)
        metadata["model_sha256"] = _sha256(model_path)
        (temporary / "partition_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (temporary / "training_summary.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copyfile(config_path, temporary / "ai_holdout_v6.yaml")
        temporary.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return metadata


def _wilson_interval(successes: int, records: int) -> list[float]:
    z = 1.959963984540054
    estimate = successes / records
    denominator = 1 + z**2 / records
    centre = (estimate + z**2 / (2 * records)) / denominator
    half_width = (
        z
        * ((estimate * (1 - estimate) / records + z**2 / (4 * records**2)) ** 0.5)
        / denominator
    )
    return [centre - half_width, centre + half_width]


def test_ai_holdout_v6_once(
    source_database: Path = RESOLVED_DIRECTION_RESULTS_DB_PATH,
    output_dir: Path = AI_HOLDOUT_V6_RESULTS_DIR,
) -> dict[str, Any]:
    """Evaluate the frozen V6 artifact once on its isolated 1,000 records."""
    source_database = Path(source_database).resolve()
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "test_metrics.json"
    if metrics_path.exists():
        raise FileExistsError("The V6 hidden 1,000-record test was already evaluated.")
    config = load_ai_holdout_v6_config(output_dir / "ai_holdout_v6.yaml")
    manifest = json.loads(
        (output_dir / "partition_manifest.json").read_text(encoding="utf-8")
    )
    stored_manifest_hash = manifest.pop("manifest_sha256")
    if _document_hash(manifest) != stored_manifest_hash:
        raise AIHoldoutV6Error("The V6 partition manifest changed after training.")
    manifest["manifest_sha256"] = stored_manifest_hash
    if _sha256(source_database) != manifest["source_database_sha256"]:
        raise AIHoldoutV6Error("The source database changed after V6 training.")
    training = json.loads(
        (output_dir / "training_summary.json").read_text(encoding="utf-8")
    )
    model_path = output_dir / "model.joblib"
    if _sha256(model_path) != training["model_sha256"]:
        raise AIHoldoutV6Error("The V6 model artifact changed after training.")
    test_ids = {
        item["variation_id"]
        for item in manifest["assignments"]
        if item["partition"] == "test"
    }
    train_ids = {
        item["variation_id"]
        for item in manifest["assignments"]
        if item["partition"] == "train"
    }
    if len(test_ids) != 1000 or test_ids & train_ids:
        raise AIHoldoutV6Error("V6 test membership failed its final isolation check.")
    test_rows = [
        row for row in _source_rows(source_database) if row["variation_id"] in test_ids
    ]
    if len(test_rows) != 1000:
        raise AIHoldoutV6Error("The V6 hidden test is not exactly 1,000 records.")
    model = joblib.load(model_path)
    features = np.asarray([row["features"] for row in test_rows], dtype=float)
    targets = np.asarray([row["target"] for row in test_rows], dtype=int)
    probabilities = model.predict_proba(features)[:, 1]
    predictions = (
        probabilities >= float(config["estimator"]["decision_threshold"])
    ).astype(int)
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    precision, recall, class_f1, support = precision_recall_fscore_support(
        targets, predictions, labels=[0, 1], zero_division=0
    )
    correct = int((targets == predictions).sum())
    metrics = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "test_records": 1000,
        "accuracy": float(accuracy_score(targets, predictions)),
        "accuracy_95_percent_wilson_interval": _wilson_interval(correct, 1000),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "macro_f1": float(f1_score(targets, predictions, average="macro")),
        "roc_auc": float(roc_auc_score(targets, probabilities)),
        "average_precision": float(average_precision_score(targets, probabilities)),
        "brier_score": float(brier_score_loss(targets, probabilities)),
        "actual_benign": int((targets == 0).sum()),
        "actual_pathogenic": int((targets == 1).sum()),
        "correct": correct,
        "wrong": int((targets != predictions).sum()),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(class_f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(("benign", "pathogenic"))
        },
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
        "partition_isolation": manifest["overlap_checks"],
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
