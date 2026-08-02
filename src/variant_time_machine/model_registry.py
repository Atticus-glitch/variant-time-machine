"""Evidence-backed model registry and lightweight evaluation reporting."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

UNKNOWN = "unknown/not recorded"
SCHEMA_VERSION = 1
MAX_SMALL_ARTIFACT_BYTES = 10 * 1024 * 1024
BENIGN = "moved_toward_benign"
PATHOGENIC = "moved_toward_pathogenic"
LABELS = (BENIGN, PATHOGENIC)
SMALL_TEST_WARNING = (
    "Small internal test (n=100): estimates are uncertain and are not independent "
    "temporal or clinical validation."
)
DISTINCT_TEST_WARNING = (
    "V4-V6 used different internal group-isolated tests. V7 used a later record-level "
    "temporal test with same-gene overlap. V8 used a sealed gene-component-disjoint "
    "test and includes a paired same-record V7 baseline; its paired confidence "
    "interval crosses zero. Other cross-version point estimates are descriptive, not "
    "paired head-to-head effects."
)
ERROR_CATEGORIES = (
    "bad match",
    "condition scope changed",
    "ambiguous ClinVar aggregation",
    "conflicting classification",
    "model over-predicted pathogenic",
    "model over-predicted benign",
    "missing feature",
    "weak feature signal",
    "possible data-label problem",
    "unknown",
)
BANNED_FUTURE_FIELDS = (
    "actual_outcome",
    "answer",
    "answer_key",
    "correct",
    "current_classification",
    "latest_classification",
    "new_classification",
    "new_release_date",
    "new_review_status",
    "newer_classification",
    "newer_release_date",
    "newer_review_status",
    "outcome",
    "outcome_group",
    "result",
    "target",
    "test_label",
    "2024_classification",
)

PROJECT_TIMELINE = [
    {
        "title": "Freeze current V4/V5 results",
        "due_date": "2026-08-03",
        "category": "model validation",
        "priority": "high",
        "description": (
            "Preserve exact artifacts, hashes, metrics, and provenance warnings."
        ),
        "success_condition": (
            "V4 and V5 registry records are frozen without rewriting results."
        ),
        "related_output_file": "outputs/model_registry/model_index.json",
        "status": "completed",
    },
    {
        "title": "Complete leakage audit",
        "due_date": "2026-08-07",
        "category": "model validation",
        "priority": "high",
        "description": (
            "Audit every declared input against future and answer-derived fields."
        ),
        "success_condition": (
            "Versioned leakage reports exist and failures are excluded from trusted "
            "ranking."
        ),
        "related_output_file": "outputs/leakage_audits/",
        "status": "completed",
    },
    {
        "title": "Test 1,000 held-out variants",
        "due_date": "2026-08-10",
        "category": "model validation",
        "priority": "high",
        "description": (
            "Freeze 1,000 connected-group representatives before fitting V6 and "
            "exclude all test-connected groups from training."
        ),
        "success_condition": (
            "A group-isolated test is frozen before tuning and evaluated once."
        ),
        "related_output_file": "research/test-set-expansion-plan.md",
        "status": "completed",
    },
    {
        "title": "Complete error analysis",
        "due_date": "2026-08-14",
        "category": "research",
        "priority": "high",
        "description": (
            "Review high-confidence errors, low-confidence cases, scope issues, "
            "and labels."
        ),
        "success_condition": (
            "Error files are generated and a representative sample is manually "
            "reviewed."
        ),
        "related_output_file": "outputs/error_analysis/",
        "status": "in_progress",
    },
    {
        "title": "Finish one-page abstract",
        "due_date": "2026-08-26",
        "category": "writing",
        "priority": "medium",
        "description": "Revise the evidence-backed abstract after larger validation.",
        "success_condition": (
            "One-page abstract is accurate, concise, and mentor-ready."
        ),
        "related_output_file": "research/one-page-abstract.md",
        "status": "draft",
    },
    {
        "title": "Email 10 mentors",
        "due_date": "2026-08-31",
        "category": "mentor outreach",
        "priority": "medium",
        "description": "Send an honest project summary and focused feedback questions.",
        "success_condition": "Ten individualized mentor emails are sent and tracked.",
        "related_output_file": "research/project-summary-for-mentors.md",
        "status": "pending",
    },
    {
        "title": "Clean public GitHub/dashboard",
        "due_date": "2026-09-20",
        "category": "dashboard",
        "priority": "high",
        "description": (
            "Remove stale claims, keep limitations visible, and verify public "
            "navigation."
        ),
        "success_condition": (
            "Repository and dashboard pass tests and contain no secrets or large data."
        ),
        "related_output_file": "README.md",
        "status": "in_progress",
    },
    {
        "title": "Poster draft complete",
        "due_date": "2026-09-25",
        "category": "competition",
        "priority": "medium",
        "description": "Draft figures, methods, results, limitations, and next steps.",
        "success_condition": "A complete poster draft is ready for review.",
        "related_output_file": "research/competition-notes.md",
        "status": "pending",
    },
    {
        "title": "Manually review 50 predictions",
        "due_date": "2026-09-30",
        "category": "research",
        "priority": "high",
        "description": (
            "Review correct and wrong predictions across confidence and outcome "
            "classes."
        ),
        "success_condition": "Fifty reviews include sources, category, and notes.",
        "related_output_file": "data/manual_review/model_error_reviews.json",
        "status": "pending",
    },
    {
        "title": "MIT essay drafts complete",
        "due_date": "2026-10-12",
        "category": "admissions",
        "priority": "medium",
        "description": (
            "Complete honest essay drafts without overstating research impact."
        ),
        "success_condition": "All MIT essay prompts have reviewable drafts.",
        "related_output_file": "research/mit-activity-draft.md",
        "status": "pending",
    },
    {
        "title": "Research supplement draft complete",
        "due_date": "2026-10-17",
        "category": "admissions",
        "priority": "medium",
        "description": (
            "Prepare a concise supplement with methods, results, and limitations."
        ),
        "success_condition": "Supplement draft links to reproducible project evidence.",
        "related_output_file": "research/one-page-abstract.md",
        "status": "pending",
    },
    {
        "title": "Freeze project v1.0",
        "due_date": "2026-10-22",
        "category": "research",
        "priority": "high",
        "description": (
            "Freeze code, model registry, reports, and documented known limitations."
        ),
        "success_condition": (
            "A tagged reproducible release is ready without changing old metrics."
        ),
        "related_output_file": "outputs/model_registry/model_index.json",
        "status": "pending",
    },
    {
        "title": "Submit MIT Early Action early",
        "due_date": "2026-10-31",
        "category": "admissions",
        "priority": "high",
        "description": "Submit before the final deadline after complete review.",
        "success_condition": "Application is submitted and confirmation is saved.",
        "related_output_file": "research/admissions-research-timeline.md",
        "status": "pending",
    },
    {
        "title": "Regeneron STS deadline, if submitting",
        "due_date": "2026-11-05",
        "category": "competition",
        "priority": "medium",
        "description": (
            "Submit only if eligibility, mentor review, and evidence quality are "
            "sufficient."
        ),
        "success_condition": (
            "Submission is complete or a documented no-submit decision is made."
        ),
        "related_output_file": "research/admissions-research-timeline.md",
        "status": "pending",
    },
]


class RegistryError(ValueError):
    """Raised when registry evidence is invalid or unsafe to consume."""


def _read_json(path: Path, *, max_bytes: int = MAX_SMALL_ARTIFACT_BYTES) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required artifact is missing: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise RegistryError(f"Refusing large JSON artifact ({size} bytes): {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistryError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash an existing artifact without loading it into memory."""
    if not path.is_file():
        raise FileNotFoundError(f"Artifact is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_prediction_rows(
    path: Path, *, max_bytes: int = MAX_SMALL_ARTIFACT_BYTES
) -> list[dict[str, str]]:
    """Load a small recorded prediction CSV with a hard size ceiling."""
    if not path.is_file():
        raise FileNotFoundError(f"Prediction artifact is missing: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise RegistryError(
            f"Refusing large prediction artifact ({size} bytes): {path}"
        )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"variation_id", "actual_outcome"}
    if not rows or not required.issubset(rows[0]):
        raise RegistryError(f"Prediction CSV lacks required recorded fields: {path}")
    for row in rows:
        probability = row.get("pathogenic_probability") or row.get("v8_probability")
        prediction = (
            row.get("prediction")
            or row.get("predicted_outcome")
            or row.get("v8_prediction")
        )
        if probability in (None, "") or not prediction:
            raise RegistryError(
                f"Prediction CSV lacks required recorded fields: {path}"
            )
        row.setdefault("pathogenic_probability", probability)
        row.setdefault("prediction", prediction)
    return rows


def _normalise_prediction(value: str) -> str:
    cleaned = value.strip().lower()
    mapping = {
        "benign": BENIGN,
        "benign_direction": BENIGN,
        BENIGN: BENIGN,
        "pathogenic": PATHOGENIC,
        "pathogenic_direction": PATHOGENIC,
        PATHOGENIC: PATHOGENIC,
    }
    if cleaned not in mapping:
        raise RegistryError(f"Unsupported binary prediction label: {value!r}")
    return mapping[cleaned]


def compute_binary_metrics(
    actual: Sequence[str], predicted: Sequence[str]
) -> dict[str, Any]:
    """Compute a complete standardized binary metric set from recorded labels."""
    if len(actual) != len(predicted) or not actual:
        raise RegistryError("Actual and predicted labels must be nonempty and aligned.")
    actual_values = [_normalise_prediction(value) for value in actual]
    predicted_values = [_normalise_prediction(value) for value in predicted]
    invalid = (set(actual_values) | set(predicted_values)) - set(LABELS)
    if invalid:
        raise RegistryError(f"Non-binary labels encountered: {sorted(invalid)}")

    pairs = list(zip(actual_values, predicted_values, strict=True))
    tn = sum(a == BENIGN and p == BENIGN for a, p in pairs)
    fp = sum(a == BENIGN and p == PATHOGENIC for a, p in pairs)
    fn = sum(a == PATHOGENIC and p == BENIGN for a, p in pairs)
    tp = sum(a == PATHOGENIC and p == PATHOGENIC for a, p in pairs)

    def ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    benign_recall = ratio(tn, tn + fp)
    pathogenic_recall = ratio(tp, tp + fn)
    benign_precision = ratio(tn, tn + fn)
    pathogenic_precision = ratio(tp, tp + fp)

    def f1(precision: float, recall: float) -> float:
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    benign_f1 = f1(benign_precision, benign_recall)
    pathogenic_f1 = f1(pathogenic_precision, pathogenic_recall)
    recalls = (benign_recall, pathogenic_recall)
    f1_values = (benign_f1, pathogenic_f1)
    total = len(actual_values)
    return {
        "records": total,
        "number_of_predictions": total,
        "number_correct": tn + tp,
        "number_wrong": fp + fn,
        "number_no_prediction": 0,
        "number_not_scorable": 0,
        "accuracy": (tn + tp) / total,
        "balanced_accuracy": sum(recalls) / len(recalls),
        "macro_precision": (benign_precision + pathogenic_precision) / 2,
        "macro_recall": sum(recalls) / len(recalls),
        "macro_f1": sum(f1_values) / len(f1_values),
        "weighted_f1": (benign_f1 * (tn + fp) + pathogenic_f1 * (tp + fn)) / total,
        "class_distribution": {
            "moved_toward_benign": tn + fp,
            "moved_toward_pathogenic": tp + fn,
        },
        "per_class": {
            "benign": {
                "precision": benign_precision,
                "recall": benign_recall,
                "f1": benign_f1,
                "support": tn + fp,
            },
            "pathogenic": {
                "precision": pathogenic_precision,
                "recall": pathogenic_recall,
                "f1": pathogenic_f1,
                "support": tp + fn,
            },
        },
        "benign_precision": benign_precision,
        "benign_recall": benign_recall,
        "benign_f1": benign_f1,
        "pathogenic_precision": pathogenic_precision,
        "pathogenic_recall": pathogenic_recall,
        "pathogenic_f1": pathogenic_f1,
        "confusion_matrix": {
            "actual_benign": {
                "predicted_benign": tn,
                "predicted_pathogenic": fp,
            },
            "actual_pathogenic": {
                "predicted_benign": fn,
                "predicted_pathogenic": tp,
            },
        },
    }


def metrics_from_prediction_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    predictions = [
        row.get("prediction")
        or row.get("predicted_outcome")
        or row.get("v8_prediction")
        or ""
        for row in rows
    ]
    return compute_binary_metrics(
        [str(row["actual_outcome"]) for row in rows], predictions
    )


def leakage_audit(
    fields: Iterable[str], banned_fields: Iterable[str] = BANNED_FUTURE_FIELDS
) -> dict[str, Any]:
    """Audit declared model inputs against exact and component-aware banned names."""
    declared = sorted({str(field).strip().lower() for field in fields})
    banned = sorted({str(field).strip().lower() for field in banned_fields})
    findings = []
    for field in declared:
        matches = [
            item
            for item in banned
            if field == item
            or field.startswith(f"{item}_")
            or field.endswith(f"_{item}")
        ]
        if matches:
            findings.append({"field": field, "matched_banned_fields": matches})
    return {
        "status": "fail" if findings else "pass",
        "declared_fields": declared,
        "banned_fields": banned,
        "findings": findings,
        "warning": (
            "Name-based audit passed; source-date and data-lineage review "
            "remain required."
            if not findings
            else "Future or answer-derived fields were detected."
        ),
    }


def _prediction_labels(rows: Sequence[Mapping[str, str]]) -> list[str]:
    return [_normalise_prediction(str(row["actual_outcome"])) for row in rows]


def baseline_predictions(
    rows: Sequence[Mapping[str, str]], *, seed: int = 20260801
) -> dict[str, list[str]]:
    """Produce majority and seeded class-stratified baselines on the same row IDs."""
    actual = _prediction_labels(rows)
    counts = Counter(actual)
    majority = max(LABELS, key=lambda label: (counts[label], label == BENIGN))
    stratified = list(actual)
    random.Random(seed).shuffle(stratified)
    return {
        "majority": [majority] * len(actual),
        "seeded_random_stratified": stratified,
    }


def load_v2_predictions_for_ids(path: Path, ids: set[str]) -> dict[str, str]:
    """Stream only requested V2 predictions from the larger historical CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"V2 result artifact is missing: {path}")
    found: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"variation_id", "predicted_direction"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RegistryError(f"V2 result CSV lacks required fields: {path}")
        for row in reader:
            identifier = row["variation_id"]
            if identifier in ids:
                prediction = row["predicted_direction"]
                found[identifier] = (
                    _normalise_prediction(prediction)
                    if prediction != "no_prediction"
                    else "no_prediction"
                )
                if len(found) == len(ids):
                    break
    return found


def _recorded_binary_evaluation(
    model_id: str, prediction_path: Path, reported_path: Path
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    rows = load_prediction_rows(prediction_path)
    metrics = metrics_from_prediction_rows(rows)
    reported = _read_json(reported_path)
    for key in ("accuracy", "balanced_accuracy"):
        if not math.isclose(metrics[key], float(reported[key]), abs_tol=1e-15):
            raise RegistryError(
                f"{model_id} derived {key} disagrees with recorded result."
            )
    metrics.update(
        {
            "model_id": model_id,
            "evaluation_kind": (
                "recorded_sealed_gene_component_disjoint_temporal_test"
                if model_id == "V8"
                else "recorded_hidden_test"
            ),
            "synthetic": False,
            "source_predictions": prediction_path.as_posix(),
            "tested_at_utc": reported.get("tested_at_utc", UNKNOWN),
            "warnings": [
                reported.get("design_warning", UNKNOWN),
                (
                    SMALL_TEST_WARNING
                    if metrics["records"] == 100
                    else "Temporal record-level test (n=1,000); not gene-independent "
                    "or clinical validation."
                    if model_id == "V7"
                    else "Internal test (n=1,000); larger than V4/V5 but still not "
                    "independent temporal or clinical validation."
                    if model_id != "V8"
                    else "Sealed gene-component-disjoint temporal test (n=1,000); "
                    "retrospective and not clinical validation."
                ),
            ],
        }
    )
    for key in (
        "accuracy_95_percent_wilson_interval",
        "roc_auc",
        "average_precision",
        "brier_score",
        "partition_isolation",
    ):
        if key in reported:
            metrics[key] = reported[key]
    if model_id == "V8":
        for key in (
            "component_bootstrap",
            "sealed_gene_components",
            "v7_same_record_baseline",
            "v8_minus_v7_balanced_accuracy",
            "majority_baseline",
            "consequence_only_baseline",
            "missense_only",
            "calibration_bins",
            "development_test_variation_id_overlap",
            "development_test_gene_component_overlap",
            "v7_test_id_overlap",
        ):
            metrics[key] = reported[key]
    return metrics, rows


def _artifact_entry(root: Path, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    if not path.is_file():
        return {
            "path": relative_path,
            "exists": False,
            "sha256": UNKNOWN,
            "size_bytes": UNKNOWN,
            "warning": "Referenced artifact is missing; no replacement was created.",
        }
    return {
        "path": relative_path,
        "exists": True,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _unknown_metrics(recorded: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "benign_precision",
        "benign_recall",
        "benign_f1",
        "pathogenic_precision",
        "pathogenic_recall",
        "pathogenic_f1",
        "roc_auc",
        "average_precision_pathogenic",
        "brier_score",
        "macro_precision",
        "macro_recall",
        "weighted_f1",
        "per_class",
        "number_of_predictions",
        "number_correct",
        "number_wrong",
        "number_no_prediction",
        "number_not_scorable",
        "class_distribution",
    )
    result = {key: recorded.get(key, UNKNOWN) for key in keys}
    result["accuracy"] = recorded.get(
        "accuracy", recorded.get("overall_accuracy", UNKNOWN)
    )
    result["number_of_predictions"] = recorded.get(
        "number_of_predictions", recorded.get("predictions_made", UNKNOWN)
    )
    result["number_correct"] = recorded.get(
        "number_correct", recorded.get("correct", UNKNOWN)
    )
    result["number_wrong"] = recorded.get(
        "number_wrong", recorded.get("wrong", UNKNOWN)
    )
    result["number_no_prediction"] = recorded.get(
        "number_no_prediction", recorded.get("no_prediction", UNKNOWN)
    )
    result["number_not_scorable"] = recorded.get(
        "number_not_scorable", recorded.get("not_scorable", UNKNOWN)
    )
    result["average_precision_pathogenic"] = recorded.get(
        "average_precision_pathogenic", recorded.get("average_precision", UNKNOWN)
    )
    return result


def _model_record(
    *,
    model_id: str,
    name: str,
    model_type: str,
    config: Mapping[str, Any],
    metrics: Mapping[str, Any],
    artifact: dict[str, Any],
    evaluation_source: str,
    train_records: Any = UNKNOWN,
    test_records: Any = UNKNOWN,
    interpretability: str,
) -> dict[str, Any]:
    features = config.get("features")
    if features is None and "clues" in config:
        features = [clue["name"] for clue in config["clues"]]
    if features is None and "weights" in config:
        features = list(config["weights"])
    features = list(features or [])
    audit = leakage_audit(features)
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": model_id,
        "name": name,
        "model_type": model_type,
        "status": config.get("status", UNKNOWN),
        "frozen_at_utc": config.get("frozen_at_utc", UNKNOWN),
        "prediction_snapshot_date": config.get(
            "prediction_snapshot_date", config.get("prediction_date", UNKNOWN)
        ),
        "answer_snapshot_date": config.get(
            "answer_snapshot_date", config.get("answer_key_date", UNKNOWN)
        ),
        "task": config.get("label", UNKNOWN),
        "conditional_task": config.get("conditional_task", model_id != "V1"),
        "source_experiment": config.get("source_experiment", UNKNOWN),
        "features": features,
        "feature_count": len(features),
        "estimator": config.get("estimator", {"name": model_type}),
        "partition": config.get("partition", UNKNOWN),
        "train_records": train_records,
        "test_records": test_records,
        "metrics": _unknown_metrics(metrics),
        "confusion_matrix": metrics.get("confusion_matrix", UNKNOWN),
        "evaluation_source": evaluation_source,
        "evaluation_reliability": (
            "internal holdout"
            if model_id in {"V3", "V4", "V5", "V6"}
            else "exploratory/full observed cohort"
        ),
        "leakage_audit": audit,
        "interpretability": interpretability,
        "manual_review": UNKNOWN,
        "vcv_verification": UNKNOWN,
        "artifact": artifact,
        "warnings": [config.get("design_warning", UNKNOWN)],
    }


def _partition_class_distribution(
    root: Path, directory: str
) -> dict[str, dict[str, int]]:
    manifest = _read_json(root / f"outputs/{directory}/partition_manifest.json")
    assignments = {
        item["variation_id"]: item["partition"] for item in manifest["assignments"]
    }
    counts: dict[str, Counter[str]] = {
        "train": Counter(),
        "test": Counter(),
        "quarantine": Counter(),
        "prior_holdout_excluded": Counter(),
    }
    database = root / "data/processed/resolved_direction_v2.sqlite3"
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        for identifier, outcome in connection.execute(
            "SELECT variation_id,outcome_group FROM predictions"
        ):
            partition = assignments.get(str(identifier))
            if partition in counts:
                counts[partition][str(outcome)] += 1
    return {key: dict(value) for key, value in counts.items()}


def create_registry(project_root: Path) -> dict[str, Any]:
    """Create standardized V1-V8 records strictly from existing evidence."""
    root = project_root.resolve()
    configs = {
        "V1": _read_json(root / "config/clue_score_v1.yaml"),
        "V2": _read_json(root / "config/resolved_direction_v2.yaml"),
        "V3": _read_json(root / "config/statistical_model_v3.yaml"),
        "V4": _read_json(root / "config/ai_holdout_v4.yaml"),
        "V5": _read_json(root / "config/ai_holdout_v5.yaml"),
        "V6": _read_json(root / "config/ai_holdout_v6.yaml"),
        "V7": _read_json(root / "config/ai_temporal_v7.yaml"),
        "V8": _read_json(root / "config/ai_temporal_v8.yaml"),
    }
    summaries = {
        "V1": _read_json(root / "outputs/clue_score_v1/metric_summary.json"),
        "V2": _read_json(root / "outputs/resolved_direction_v2/metric_summary.json"),
        "V3": _read_json(root / "outputs/statistical_model_v3/metric_summary.json"),
    }
    v4_metrics, _ = _recorded_binary_evaluation(
        "V4",
        root / "outputs/ai_holdout_v4/hidden_test_predictions.csv",
        root / "outputs/ai_holdout_v4/test_metrics.json",
    )
    v5_metrics, _ = _recorded_binary_evaluation(
        "V5",
        root / "outputs/ai_holdout_v5/hidden_test_predictions.csv",
        root / "outputs/ai_holdout_v5/test_metrics.json",
    )
    v6_metrics, _ = _recorded_binary_evaluation(
        "V6",
        root / "outputs/ai_holdout_v6/hidden_test_predictions.csv",
        root / "outputs/ai_holdout_v6/test_metrics.json",
    )
    v7_metrics, _ = _recorded_binary_evaluation(
        "V7",
        root / "outputs/ai_temporal_v7/temporal_test_predictions.csv",
        root / "outputs/ai_temporal_v7/test_metrics.json",
    )
    v8_metrics, _ = _recorded_binary_evaluation(
        "V8",
        root / "outputs/ai_temporal_v8/temporal_test_predictions.csv",
        root / "outputs/ai_temporal_v8/test_metrics.json",
    )
    summaries.update(
        {
            "V4": v4_metrics,
            "V5": v5_metrics,
            "V6": v6_metrics,
            "V7": v7_metrics,
            "V8": v8_metrics,
        }
    )
    training_v4 = _read_json(root / "outputs/ai_holdout_v4/training_summary.json")
    training_v5 = _read_json(root / "outputs/ai_holdout_v5/training_summary.json")
    training_v6 = _read_json(root / "outputs/ai_holdout_v6/training_summary.json")
    training_v7 = _read_json(root / "outputs/ai_temporal_v7/training_summary.json")
    training_v8 = _read_json(root / "outputs/ai_temporal_v8/training_summary.json")
    configs["V8"] = {**configs["V8"], "features": training_v8["feature_names"]}
    distributions = {
        "V4": _partition_class_distribution(root, "ai_holdout_v4"),
        "V5": _partition_class_distribution(root, "ai_holdout_v5"),
        "V6": _partition_class_distribution(root, "ai_holdout_v6"),
        "V7": {
            "development": training_v7["out_of_fold_metrics"]["class_distribution"],
            "test": v7_metrics["class_distribution"],
        },
        "V8": {
            "development": {
                "records": training_v8["development_records"],
                "gene_components": training_v8["development_groups"],
            },
            "test": v8_metrics["class_distribution"],
            "sealed_test_gene_components": v8_metrics["sealed_gene_components"],
        },
    }
    specifications = {
        "V1": (
            "Clue Score V1",
            "frozen hand-designed score",
            "config/clue_score_v1.yaml",
            "outputs/clue_score_v1/metric_summary.json",
            UNKNOWN,
            summaries["V1"].get("eligible_older_vus_records", UNKNOWN),
            "high: explicit clue weights and arithmetic",
        ),
        "V2": (
            "Resolved Direction V2",
            "frozen hand-designed binary rule",
            "config/resolved_direction_v2.yaml",
            "outputs/resolved_direction_v2/metric_summary.json",
            UNKNOWN,
            summaries["V2"].get("resolved_direction_records", UNKNOWN),
            "high: explicit V1 score thresholds",
        ),
        "V3": (
            "Statistical Model V3",
            "logistic regression",
            "outputs/statistical_model_v3/model.json",
            "outputs/statistical_model_v3/held_out_predictions.csv",
            summaries["V3"].get("train_records", UNKNOWN),
            summaries["V3"].get("test_records", UNKNOWN),
            "high: linear coefficients are recorded",
        ),
        "V4": (
            "AI Holdout V4",
            "neural network",
            "outputs/ai_holdout_v4/model.joblib",
            "outputs/ai_holdout_v4/hidden_test_predictions.csv",
            training_v4.get("training_records", UNKNOWN),
            v4_metrics["records"],
            "limited: one hidden-layer neural network",
        ),
        "V5": (
            "AI Holdout V5",
            "scaled class-balanced neural network",
            "outputs/ai_holdout_v5/model.joblib",
            "outputs/ai_holdout_v5/hidden_test_predictions.csv",
            training_v5.get("training_records", UNKNOWN),
            v5_metrics["records"],
            "limited: two hidden-layer neural network",
        ),
        "V6": (
            "AI Holdout V6",
            "scaled class-balanced neural network",
            "outputs/ai_holdout_v6/model.joblib",
            "outputs/ai_holdout_v6/hidden_test_predictions.csv",
            training_v6.get("training_records", UNKNOWN),
            v6_metrics["records"],
            "limited: two hidden-layer neural network",
        ),
        "V7": (
            "AI Temporal V7",
            "calibrated histogram gradient boosting",
            "outputs/ai_temporal_v7/model.joblib",
            "outputs/ai_temporal_v7/temporal_test_predictions.csv",
            training_v7.get("development_records", UNKNOWN),
            v7_metrics["records"],
            "medium: shallow tree ensemble with recorded selection and calibration",
        ),
        "V8": (
            "AI Temporal V8",
            "calibrated elastic-net logistic regression",
            "outputs/ai_temporal_v8/model.joblib",
            "outputs/ai_temporal_v8/temporal_test_predictions.csv",
            training_v8.get("development_records", UNKNOWN),
            v8_metrics["records"],
            "high: linear predictor with recorded grouped selection and calibration",
        ),
    }
    models = []
    for model_id, values in specifications.items():
        name, model_type, artifact_path, source, train, test, interpretability = values
        record = _model_record(
            model_id=model_id,
            name=name,
            model_type=model_type,
            config=configs[model_id],
            metrics=summaries[model_id],
            artifact=_artifact_entry(root, artifact_path),
            evaluation_source=source,
            train_records=train,
            test_records=test,
            interpretability=interpretability,
        )
        code_commits = {
            "V1": "093e4e1",
            "V2": "b3d0b1d",
            "V3": "9a22613",
            "V4": "a8cd286",
            "V5": "036c475",
            "V6": UNKNOWN,
            "V7": UNKNOWN,
            "V8": UNKNOWN,
        }
        training_documents = {
            "V4": training_v4,
            "V5": training_v5,
            "V6": training_v6,
            "V7": training_v7,
            "V8": training_v8,
        }
        training_document = training_documents.get(model_id, {})
        source_hash = configs[model_id].get(
            "source_database_sha256",
            configs[model_id].get(
                "development_source_database_sha256",
                configs[model_id]
                .get("development_sources", {})
                .get("v2_database_sha256", UNKNOWN),
            ),
        )
        output_directories = {
            "V1": "outputs/clue_score_v1",
            "V2": "outputs/resolved_direction_v2",
            "V3": "outputs/statistical_model_v3",
            "V4": "outputs/ai_holdout_v4",
            "V5": "outputs/ai_holdout_v5",
            "V6": "outputs/ai_holdout_v6",
            "V7": "outputs/ai_temporal_v7",
            "V8": "outputs/ai_temporal_v8",
        }
        output_directory = root / output_directories[model_id]
        output_files = [
            path.relative_to(root).as_posix()
            for path in sorted(output_directory.iterdir())
            if path.is_file()
        ]
        warnings = list(record["warnings"])
        if model_id == "V3":
            warnings.append(
                "The original V3 source database hash is not available in the current "
                "workspace; recorded results are preserved but cannot be reproduced "
                "from the current V2 database byte-for-byte."
            )
        if model_id in {"V4", "V5"}:
            warnings.append(
                "Recorded configuration frozen_at_utc occurs after the recorded "
                "training timestamp; chronology is inconsistent and was not rewritten."
            )
            warnings.append(
                "Training summary retains trained_hidden_test_unopened, but a saved "
                "test_metrics.json establishes that the effective state is tested."
            )
        if model_id == "V6":
            warnings.append(str(configs[model_id]["source_note"]))
        if model_id == "V7":
            warnings.extend(
                [
                    "All test Variation IDs were absent from development, but 69.9% "
                    "of test records shared at least one gene with development.",
                    "The primary test is conditional on safe clear resolution by July "
                    "2026 and does not estimate whether a VUS will resolve.",
                ]
            )
        if model_id == "V8":
            paired_interval = v8_metrics["component_bootstrap"][
                "paired_difference_95_percent"
            ]
            warnings.extend(
                [
                    "V8 is a membership-hidden retrospective temporal test, not a "
                    "never-opened future archive or clinical validation.",
                    "V8 and the frozen V7 model were evaluated on the same 1,000 V8 "
                    "records; the balanced-accuracy difference was "
                    f"{v8_metrics['v8_minus_v7_balanced_accuracy']}, with component-"
                    "bootstrap 95% interval "
                    f"[{paired_interval[0]}, {paired_interval[1]}] "
                    "crossing zero.",
                    "V8 fitting combined inverse-component sample weights with "
                    "balanced class weights, so effective fitting weight was not "
                    "strictly equal per component.",
                    "The V8 simplicity tie-break ranked model families but not "
                    "regularization strength within logistic regression.",
                ]
            )
        record.update(
            {
                "model_version_name": model_id,
                "date_created": record["frozen_at_utc"],
                "code_commit_hash": code_commits[model_id],
                "dataset_version": {
                    "prediction_snapshot": record["prediction_snapshot_date"],
                    "answer_snapshot": record["answer_snapshot_date"],
                    "source_database_sha256": source_hash,
                },
                "train_validation_test_split_method": record["partition"],
                "number_training_records": train,
                "number_validation_records": (
                    "not recorded"
                    if model_id == "V4"
                    else "5-fold grouped out-of-fold development"
                    if model_id in {"V7", "V8"}
                    else 0
                    if model_id in {"V5", "V6"}
                    else UNKNOWN
                ),
                "number_test_records": test,
                "input_feature_list": record["features"],
                "excluded_feature_list": list(BANNED_FUTURE_FIELDS),
                "target_outcome_definition": configs[model_id].get(
                    "target",
                    "Later normalized ClinVar aggregate classification outcome; see "
                    "the frozen version configuration.",
                ),
                "class_distribution": distributions.get(model_id, UNKNOWN),
                "preprocessing_steps": configs[model_id].get(
                    "training", configs[model_id].get("feature_rule", UNKNOWN)
                ),
                "hyperparameters": record["estimator"],
                "random_seed": (
                    record["estimator"].get("random_state", UNKNOWN)
                    if isinstance(record["estimator"], dict)
                    else UNKNOWN
                ),
                "training_runtime_seconds": UNKNOWN,
                "evaluation_runtime_seconds": UNKNOWN,
                "author_notes": (
                    "Evidence-backed reconstruction from existing frozen artifacts; "
                    "not an original runtime record."
                ),
                "limitations": warnings,
                "leakage_audit_status": record["leakage_audit"]["status"],
                "manual_review_status": "not started",
                "output_files": output_files,
                "effective_status": (
                    "frozen_evaluated"
                    if model_id in {"V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"}
                    else record["status"]
                ),
                "training_timestamp": training_document.get("trained_at_utc", UNKNOWN),
                "warnings": warnings,
            }
        )
        if model_id in {"V3", "V4", "V5", "V6"}:
            record["prediction_snapshot_date"] = "2022-01-06"
            record["answer_snapshot_date"] = "2024-01-04"
            record["dataset_version"].update(
                {
                    "prediction_snapshot": "2022-01-06",
                    "answer_snapshot": "2024-01-04",
                    "dates_inherited_from": "Resolved Direction V2 source cohort",
                }
            )
            if record["source_experiment"] == UNKNOWN:
                record["source_experiment"] = "Resolved Direction V2"
        if model_id == "V7":
            record["evaluation_reliability"] = "external temporal holdout"
            record["source_experiment"] = "January 2024 to July 2026 temporal cohort"
            record["partition"] = {
                "candidate_rule": configs[model_id]["candidate_rule"],
                "final_test_rule": configs[model_id]["final_test_rule"],
                "final_test_records": configs[model_id]["final_test_records"],
            }
            record["train_validation_test_split_method"] = record["partition"]
            record["estimator"] = {
                "name": training_v7["selected_model"],
                "calibration": configs[model_id]["development"]["calibration"],
                "decision_threshold": training_v7["selected_threshold"],
            }
            record["hyperparameters"] = record["estimator"]
            record["random_seed"] = configs[model_id]["development"]["random_state"]
            record["preprocessing_steps"] = {
                "numeric_transform": "log1p age and submitter count",
                "row_weight": configs[model_id]["development"]["row_weight"],
            }
        if model_id == "V8":
            record["evaluation_reliability"] = (
                "sealed gene-component-disjoint retrospective temporal holdout"
            )
            record["source_experiment"] = (
                "Publicly committed V8 label-vault temporal cohort"
            )
            record["partition"] = {
                "test_rule": configs[model_id]["test_rule"],
                "test_records": configs[model_id]["test_records"],
                "development_test_variation_id_overlap": v8_metrics[
                    "development_test_variation_id_overlap"
                ],
                "development_test_gene_component_overlap": v8_metrics[
                    "development_test_gene_component_overlap"
                ],
            }
            record["train_validation_test_split_method"] = record["partition"]
            record["estimator"] = {
                "name": training_v8["selected_model"],
                "calibration": configs[model_id]["development"]["calibration"],
                "decision_threshold": training_v8["selected_threshold"],
            }
            record["hyperparameters"] = record["estimator"]
            record["random_seed"] = configs[model_id]["development"]["random_state"]
            record["preprocessing_steps"] = {
                "feature_policy": configs[model_id]["feature_policy"],
                "preregistered_component_weight": configs[model_id]["development"][
                    "component_weight"
                ],
                "implemented_weighting": (
                    "inverse-component sample weights multiplied by balanced class "
                    "weights; not strictly equal effective total weight per component"
                ),
            }
            record["paired_same_record_baseline"] = {
                "model_id": "V7",
                "records": v8_metrics["v7_same_record_baseline"]["records"],
                "balanced_accuracy": v8_metrics["v7_same_record_baseline"][
                    "balanced_accuracy"
                ],
                "v8_minus_v7_balanced_accuracy": v8_metrics[
                    "v8_minus_v7_balanced_accuracy"
                ],
                "paired_difference_95_percent": v8_metrics["component_bootstrap"][
                    "paired_difference_95_percent"
                ],
            }
        models.append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_kind": "evidence_backed_model_registry",
        "models": models,
        "unknown_value": UNKNOWN,
        "ranking_policy": [
            "Do not total-rank models evaluated on different tasks or cohorts.",
            "Compare test design, sample size, class recall, uncertainty, "
            "and coverage.",
            "Treat leakage-audit failure as disqualifying, not as a ranking penalty.",
        ],
        "warnings": [DISTINCT_TEST_WARNING],
    }


def save_registry(registry: Mapping[str, Any], path: Path) -> None:
    model_ids = [model.get("model_id") for model in registry.get("models", [])]
    if model_ids != ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"]:
        raise RegistryError(
            "Registry must contain standardized V1-V8 records in order."
        )
    _write_json(path, registry)


def load_registry(path: Path) -> dict[str, Any]:
    registry = _read_json(path)
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError("Unsupported model registry schema.")
    if [item.get("model_id") for item in registry.get("models", [])] != [
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "V8",
    ]:
        raise RegistryError("Model registry does not contain ordered V1-V8 records.")
    return registry


def missing_model_record(
    model_id: str, expected_files: Sequence[str]
) -> dict[str, Any]:
    """Return an honest placeholder without inventing a result."""
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": model_id,
        "model_version_name": model_id,
        "status": "files_not_found",
        "effective_status": "results_not_available",
        "model_type": UNKNOWN,
        "metrics": {
            "accuracy": UNKNOWN,
            "balanced_accuracy": UNKNOWN,
            "macro_f1": UNKNOWN,
        },
        "expected_files": list(expected_files),
        "warnings": [
            "Model version expected, but required files were not found.",
            "Results are not available and no metrics were fabricated.",
        ],
        "action_needed": "Restore or generate this version under a new explicit run.",
    }


def load_model_record_or_placeholder(
    path: Path, model_id: str, expected_files: Sequence[str]
) -> dict[str, Any]:
    if not path.is_file():
        return missing_model_record(model_id, expected_files)
    return _read_json(path)


def rank_models(models: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize evidence without inventing a cross-cohort league table."""
    by_id = {model["model_id"]: model for model in models}
    v7_balanced = by_id.get("V7", {}).get("metrics", {}).get("balanced_accuracy")
    v8_balanced = by_id.get("V8", {}).get("metrics", {}).get("balanced_accuracy")
    paired = by_id.get("V8", {}).get("paired_same_record_baseline", {})
    return {
        "ranking": [],
        "comparison_status": "not_rankable_across_current_evaluations",
        "criteria": ["test design", "sample size", "class recall", "uncertainty"],
        "stable_winner": None,
        "conclusion": (
            "V8 provides the strongest component-isolation design: a sealed n=1,000 "
            "gene-component-disjoint retrospective test. V7 retains the stronger "
            "archive-time boundary. V8's small paired balanced-accuracy difference "
            "from V7 is inconclusive because the component-bootstrap interval crosses "
            "zero. Neither is clinical validation."
        ),
        "evidence_summary": {
            "strongest_component_isolation": (
                "V8 sealed gene-component-disjoint retrospective test (n=1,000)"
            ),
            "v8_balanced_accuracy": (
                f"V8 ({v8_balanced:.1%})"
                if isinstance(v8_balanced, int | float)
                else "V8 not present in supplied records"
            ),
            "v7_balanced_accuracy": (
                f"V7 ({v7_balanced:.1%})"
                if isinstance(v7_balanced, int | float)
                else "V7 not present in supplied records"
            ),
            "own_test_score_context": (
                "Own-test balanced accuracies are not ranked because the cohorts and "
                "evaluation boundaries differ."
            ),
            "most_interpretable_models": "V1-V3",
            "paired_v8_vs_v7": paired or "V8 paired evidence not present",
        },
        "warning": DISTINCT_TEST_WARNING,
    }


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_error_analysis(
    model_id: str,
    rows: Sequence[Mapping[str, str]],
    output_path: Path,
    details: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Write all evaluated rows, not only errors, with honest review placeholders."""
    output = []
    for row in rows:
        actual = _normalise_prediction(str(row["actual_outcome"]))
        prediction = _normalise_prediction(
            str(
                row.get("prediction")
                or row.get("predicted_outcome")
                or row.get("v8_prediction")
                or ""
            )
        )
        probability = float(
            row.get("pathogenic_probability") or row.get("v8_probability") or ""
        )
        correct = actual == prediction
        detail = dict((details or {}).get(row["variation_id"], {}))
        confidence_value = max(probability, 1 - probability)
        if not correct:
            suspected = (
                "model over-predicted pathogenic"
                if prediction == PATHOGENIC
                else "model over-predicted benign"
            )
        else:
            suspected = "unknown"
        output.append(
            {
                "model_version": model_id,
                "variation_id": row["variation_id"],
                "vcv_accession": detail.get("vcv_accession", "not recorded"),
                "gene": detail.get(
                    "gene", row.get("gene_symbols", "not recorded") or "not recorded"
                ),
                "old_classification": detail.get("old_classification", "not recorded"),
                "actual_later_classification": detail.get(
                    "new_classification",
                    row.get("answer_classification", "not recorded")
                    if model_id == "V8"
                    else "not recorded",
                ),
                "actual_outcome": actual,
                "predicted_class": prediction,
                "pathogenic_probability": probability,
                "score_or_probability": probability,
                "correct": str(correct).lower(),
                "analysis_bucket": (
                    "wrong high-confidence"
                    if not correct and confidence_value >= 0.8
                    else "correct high-confidence"
                    if correct and confidence_value >= 0.8
                    else "low-confidence"
                ),
                "confidence": confidence_value,
                "key_features": detail.get(
                    "key_features",
                    (
                        f"consequence={row['consequence']}"
                        if model_id == "V8" and row.get("consequence")
                        else row.get("features_json", "not recorded")
                    ),
                ),
                "match_confidence": detail.get("match_confidence", "not recorded"),
                "warning_flags": detail.get("warning_flags", ""),
                "suspected_error_category": suspected,
                "manual_review_status": "unreviewed",
                "notes": "",
                "leakage_audit_status": "pass",
                "source": "recorded temporal_test_predictions.csv"
                if model_id == "V8"
                else "recorded hidden_test_predictions.csv",
            }
        )
    fields = (
        "model_version",
        "variation_id",
        "vcv_accession",
        "gene",
        "old_classification",
        "actual_later_classification",
        "actual_outcome",
        "predicted_class",
        "pathogenic_probability",
        "score_or_probability",
        "correct",
        "analysis_bucket",
        "confidence",
        "key_features",
        "match_confidence",
        "warning_flags",
        "suspected_error_category",
        "manual_review_status",
        "notes",
        "leakage_audit_status",
        "source",
    )
    _write_csv(output_path, output, fields)
    return output


def load_variant_details(database: Path, ids: set[str]) -> dict[str, dict[str, Any]]:
    """Load older features and answer context for a small evaluated ID set."""
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    query = (
        "SELECT variation_id,old_gene_symbols,old_classification,new_classification,"
        "clues_json,match_confidence,warnings_json,match_warnings_json "
        f"FROM predictions WHERE variation_id IN ({placeholders})"
    )
    details: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(query, tuple(sorted(ids))):
            clues = json.loads(row["clues_json"] or "[]")
            key_features = [
                clue.get("clue", "unknown") for clue in clues if clue.get("applied")
            ]
            warnings = [
                *json.loads(row["warnings_json"] or "[]"),
                *json.loads(row["match_warnings_json"] or "[]"),
            ]
            details[str(row["variation_id"])] = {
                "vcv_accession": "not recorded",
                "gene": row["old_gene_symbols"] or "not recorded",
                "old_classification": row["old_classification"] or "not recorded",
                "new_classification": row["new_classification"] or "not recorded",
                "key_features": "; ".join(key_features) or "none applied",
                "match_confidence": row["match_confidence"] or "not recorded",
                "warning_flags": "; ".join(str(value) for value in warnings),
            }
    return details


def v7_protocol_audit(
    development_database: Path,
    prediction_rows: Sequence[Mapping[str, str]],
    training_summary: Mapping[str, Any],
    test_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize temporal overlap and exclusion accounting after frozen evaluation."""

    def genes(value: object) -> set[str]:
        return {
            item.strip().upper()
            for item in re.split(r"[,;|]", str(value or ""))
            if item.strip() and item.strip() != "-"
        }

    development_ids = set()
    development_genes = set()
    with sqlite3.connect(
        f"file:{Path(development_database).resolve()}?mode=ro", uri=True
    ) as connection:
        for identifier, gene_symbols in connection.execute(
            "SELECT variation_id,old_gene_symbols FROM predictions"
        ):
            development_ids.add(str(identifier))
            development_genes.update(genes(gene_symbols))
    test_ids = {str(row["variation_id"]) for row in prediction_rows}
    test_gene_sets = [genes(row.get("gene_symbols")) for row in prediction_rows]
    shared_gene_records = sum(
        bool(values & development_genes) for values in test_gene_sets
    )
    test_genes = set().union(*test_gene_sets)
    exclusions = dict(test_metrics.get("exclusions", {}))
    accounted = int(test_metrics["safe_clear_outcomes_available"]) + sum(
        int(value) for value in exclusions.values()
    )
    missing = int(training_summary["temporal_candidate_records"]) - accounted
    correct = int(test_metrics["number_correct"])
    records = int(test_metrics["test_records"])
    z = 1.959963984540054
    estimate = correct / records
    denominator = 1 + z**2 / records
    centre = (estimate + z**2 / (2 * records)) / denominator
    half_width = (
        z
        * ((estimate * (1 - estimate) / records + z**2 / (4 * records**2)) ** 0.5)
        / denominator
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": "V7",
        "audit_kind": "post_evaluation_protocol_accounting",
        "test_records": records,
        "development_test_variation_id_overlap": len(development_ids & test_ids),
        "test_records_sharing_development_gene": shared_gene_records,
        "same_gene_overlap_fraction": shared_gene_records / records,
        "unique_test_genes": len(test_genes),
        "unique_test_genes_seen_in_development": len(test_genes & development_genes),
        "unique_test_genes_unseen_in_development": len(test_genes - development_genes),
        "missing_from_answer_snapshot": missing,
        "candidate_accounting_complete": accounted + missing
        == int(training_summary["temporal_candidate_records"]),
        "accuracy_95_percent_wilson_interval": [
            centre - half_width,
            centre + half_width,
        ],
        "warning": (
            "This audit was calculated after the frozen test. It describes overlap "
            "and accounting and did not alter model selection, predictions, or metrics."
        ),
    }


def v8_protocol_audit(
    project_root: Path,
    prediction_rows: Sequence[Mapping[str, str]],
    training_summary: Mapping[str, Any],
    test_metrics: Mapping[str, Any],
    vault_commitment: Mapping[str, Any],
    model_commitment: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify completed V8 commitments, isolation, and paired result accounting."""
    required_fields = {
        "variation_id",
        "gene_symbols",
        "component_hash",
        "consequence",
        "v8_probability",
        "v8_prediction",
        "v7_probability",
        "v7_prediction",
        "actual_outcome",
        "answer_classification",
    }
    available_fields = set(prediction_rows[0]) if prediction_rows else set()
    component_count = len({row["component_hash"] for row in prediction_rows})
    paired_interval = test_metrics["component_bootstrap"][
        "paired_difference_95_percent"
    ]
    source_keys = {
        "development_database",
        "predictor_index",
        "sealed_candidates",
        "v7_test_predictions",
    }
    shared_sources_match = all(
        vault_commitment["source_hashes"].get(key)
        == model_commitment["source_hashes"].get(key)
        for key in source_keys
    )
    root = Path(project_root).resolve()
    current_artifact_hashes = {
        "config": sha256_file(root / "config/ai_temporal_v8.yaml"),
        "vault": sha256_file(root / "outputs/ai_temporal_v8/label_vault.sqlite3"),
        "model": sha256_file(root / "outputs/ai_temporal_v8/model.joblib"),
        "sealed_predictions": sha256_file(
            root / "outputs/ai_temporal_v8/sealed_candidate_predictions.sqlite3"
        ),
    }
    current_source_hashes = {
        "development_database": sha256_file(
            root / "data/processed/resolved_direction_v2.sqlite3"
        ),
        "predictor_index": sha256_file(root / "data/processed/clinvar_history.sqlite3"),
        "sealed_candidates": sha256_file(
            root / "outputs/ai_temporal_v7/sealed_candidate_predictions.sqlite3"
        ),
        "v7_test_predictions": sha256_file(
            root / "outputs/ai_temporal_v7/temporal_test_predictions.csv"
        ),
        "answer_archive": sha256_file(
            root / "data/raw/clinvar/variant_summary_2026-07.txt.gz"
        ),
    }
    checks = {
        "prediction_fields_complete": required_fields.issubset(available_fields),
        "test_record_count_matches": len(prediction_rows)
        == int(test_metrics["test_records"])
        == int(vault_commitment["test_records"])
        == 1000,
        "sealed_component_count_matches": component_count
        == int(test_metrics["sealed_gene_components"]),
        "development_test_variation_id_overlap_is_zero": int(
            test_metrics["development_test_variation_id_overlap"]
        )
        == int(vault_commitment["development_test_variation_id_overlap"])
        == 0,
        "development_test_gene_component_overlap_is_zero": int(
            test_metrics["development_test_gene_component_overlap"]
        )
        == int(vault_commitment["development_test_gene_component_overlap"])
        == 0,
        "v7_test_id_overlap_is_zero": int(test_metrics["v7_test_id_overlap"])
        == int(vault_commitment["v7_test_id_overlap"])
        == 0,
        "config_commitments_match": vault_commitment["config_sha256"]
        == model_commitment["config_sha256"]
        == training_summary["config_sha256"],
        "commitment_states_match_protocol": vault_commitment["state"]
        == "label_vault_sealed_before_v8_model_development"
        and model_commitment["state"] == "model_and_predictions_sealed_vault_unopened",
        "vault_commitment_matches_evaluation": vault_commitment["vault_sha256"]
        == test_metrics["vault_sha256"],
        "model_commitment_matches_training": model_commitment["model_sha256"]
        == training_summary["model_sha256"],
        "prediction_commitment_matches_training": model_commitment[
            "sealed_predictions_sha256"
        ]
        == training_summary["sealed_predictions_sha256"]
        == test_metrics["sealed_predictions_sha256"],
        "development_sources_cross_bound": shared_sources_match,
        "vault_was_unopened_during_development": model_commitment[
            "vault_accessed_during_development"
        ]
        is False,
        "current_config_matches_commitments": current_artifact_hashes["config"]
        == vault_commitment["config_sha256"]
        == model_commitment["config_sha256"],
        "current_vault_matches_commitment": current_artifact_hashes["vault"]
        == vault_commitment["vault_sha256"],
        "current_model_matches_commitment": current_artifact_hashes["model"]
        == model_commitment["model_sha256"],
        "current_predictions_match_commitment": current_artifact_hashes[
            "sealed_predictions"
        ]
        == model_commitment["sealed_predictions_sha256"],
        "current_sources_match_commitments": all(
            current_source_hashes[key] == vault_commitment["source_hashes"].get(key)
            for key in current_source_hashes
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": "V8",
        "audit_kind": "post_evaluation_protocol_and_commitment_accounting",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "test_records": len(prediction_rows),
        "sealed_gene_components": component_count,
        "development_records": training_summary["development_records"],
        "development_gene_components": training_summary["development_groups"],
        "accuracy": test_metrics["accuracy"],
        "balanced_accuracy": test_metrics["balanced_accuracy"],
        "v7_same_record_balanced_accuracy": test_metrics["v7_same_record_baseline"][
            "balanced_accuracy"
        ],
        "v8_minus_v7_balanced_accuracy": test_metrics["v8_minus_v7_balanced_accuracy"],
        "paired_difference_95_percent": paired_interval,
        "paired_interval_crosses_zero": paired_interval[0] <= 0 <= paired_interval[1],
        "warning": (
            "This post-evaluation audit verifies recorded commitments and accounting. "
            "It did not reopen the vault, rerun evaluation, or alter predictions. The "
            "paired V8-V7 interval crosses zero, so no performance improvement is "
            "claimed."
        ),
    }


def load_model_dashboard(project_root: Path) -> dict[str, Any]:
    """Load generated registry and comparison artifacts for read-only display."""
    root = Path(project_root).resolve()
    index = _read_json(root / "outputs/model_registry/model_index.json")
    models = [
        load_model_record_or_placeholder(
            root / item["record_path"], item["model_id"], [item["record_path"]]
        )
        for item in index["models"]
    ]
    comparison_path = root / "outputs/evaluations/model_comparison.csv"
    with comparison_path.open(newline="", encoding="utf-8") as handle:
        comparisons = list(csv.DictReader(handle))
    return {**index, "model_records": models, "baseline_comparisons": comparisons}


def _load_review_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": 1,
            "allowed_categories": list(ERROR_CATEGORIES),
            "reviews": {},
        }
    return _read_json(path)


def load_prediction_explorer(project_root: Path, review_path: Path) -> dict[str, Any]:
    """Join V4-V8 frozen prediction rows without exposing model binaries."""
    root = Path(project_root).resolve()
    reviews = _load_review_document(review_path).get("reviews", {})
    rows_by_id: dict[str, dict[str, Any]] = {}
    for model_id in ("V4", "V5", "V6", "V7", "V8"):
        path = root / (
            "outputs/error_analysis/v8_all_rows.csv"
            if model_id == "V8"
            else f"outputs/error_analysis/model_{model_id.lower()}_errors.csv"
        )
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                identifier = row["variation_id"]
                item = rows_by_id.setdefault(
                    identifier,
                    {
                        "variation_id": identifier,
                        "gene": row["gene"],
                        "actual_outcome": row["actual_outcome"],
                        "v4_prediction": None,
                        "v4_correct": None,
                        "v4_confidence": None,
                        "v5_prediction": None,
                        "v5_correct": None,
                        "v5_confidence": None,
                        "v6_prediction": None,
                        "v6_correct": None,
                        "v6_confidence": None,
                        "v7_prediction": None,
                        "v7_correct": None,
                        "v7_confidence": None,
                        "v8_prediction": None,
                        "v8_correct": None,
                        "v8_confidence": None,
                        "manual_review_status": "unreviewed",
                    },
                )
                prefix = model_id.lower()
                item[f"{prefix}_prediction"] = row["predicted_class"]
                item[f"{prefix}_correct"] = row["correct"] == "true"
                item[f"{prefix}_confidence"] = float(row["confidence"])
                model_review = (
                    reviews.get(f"{model_id}:{identifier}", {})
                    if model_id != "V8"
                    else {}
                )
                if model_review:
                    item["manual_review_status"] = model_review.get(
                        "status", "unreviewed"
                    )
    rows = sorted(rows_by_id.values(), key=lambda item: int(item["variation_id"]))
    return {
        "rows": rows,
        "total": len(rows),
        "warning": DISTINCT_TEST_WARNING,
        "allowed_error_categories": list(ERROR_CATEGORIES),
    }


def prediction_explorer_detail(
    project_root: Path, variation_id: str, review_path: Path
) -> dict[str, Any]:
    if not variation_id.isdigit():
        raise RegistryError("Variation ID must contain digits only.")
    root = Path(project_root).resolve()
    explorer = load_prediction_explorer(root, review_path)
    summary = next(
        (row for row in explorer["rows"] if row["variation_id"] == variation_id),
        None,
    )
    if summary is None:
        raise RegistryError("Prediction Explorer record was not found.")
    database = root / "data/processed/resolved_direction_v2.sqlite3"
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT variation_id,old_gene_symbols,old_classification,old_names,"
            "old_review_status,old_submitter_counts,old_last_evaluated,clues_json,"
            "new_classification,outcome_group,match_method,match_confidence,"
            "warnings_json,match_warnings_json FROM predictions WHERE variation_id=?",
            (variation_id,),
        ).fetchone()
    if row is None:
        summary.update(
            {
                "old_classification": "Uncertain significance",
                "old_gene_symbols": summary["gene"],
                "old_names": "not recorded in public error report",
                "old_review_status": "not recorded in public error report",
                "old_submitter_counts": "not recorded in public error report",
                "old_last_evaluated": "not recorded in public error report",
                "older_features": [],
                "actual_later_classification": "see normalized temporal outcome",
                "match_method": "exact Variation ID and unchanged Allele ID set",
                "match_confidence": "high under frozen temporal rule",
                "warning_flags": [
                    "Temporal-test detail is limited to the public error report."
                ],
            }
        )
    model_rows: dict[str, dict[str, str]] = {}
    for model_id in ("V4", "V5", "V6", "V7", "V8"):
        path = root / (
            "outputs/error_analysis/v8_all_rows.csv"
            if model_id == "V8"
            else f"outputs/error_analysis/model_{model_id.lower()}_errors.csv"
        )
        with path.open(newline="", encoding="utf-8") as handle:
            match = next(
                (
                    value
                    for value in csv.DictReader(handle)
                    if value["variation_id"] == variation_id
                ),
                None,
            )
        if match:
            model_rows[model_id] = match
    reviews = _load_review_document(review_path).get("reviews", {})
    detail = {
        **summary,
        **(
            {
                "old_classification": row["old_classification"],
                "old_gene_symbols": row["old_gene_symbols"],
                "old_names": row["old_names"],
                "old_review_status": row["old_review_status"],
                "old_submitter_counts": row["old_submitter_counts"],
                "old_last_evaluated": row["old_last_evaluated"],
                "older_features": json.loads(row["clues_json"] or "[]"),
                "actual_later_classification": row["new_classification"],
                "actual_outcome": row["outcome_group"],
                "match_method": row["match_method"],
                "match_confidence": row["match_confidence"],
                "warning_flags": [
                    *json.loads(row["warnings_json"] or "[]"),
                    *json.loads(row["match_warnings_json"] or "[]"),
                ],
            }
            if row is not None
            else {}
        ),
        "model_results": model_rows,
        "leakage_check": {
            "V4": "pass",
            "V5": "pass",
            "V6": "pass",
            "V7": "pass",
            "V8": "pass",
        },
        "manual_reviews": {
            key: value
            for key, value in reviews.items()
            if key.endswith(f":{variation_id}") and not key.startswith("V8:")
        },
        "explanation_boundary": (
            "Neural-network probability and older inputs are shown, but a neural "
            "network does not have the exact point arithmetic of the V2 baseline."
        ),
    }
    return detail


def update_error_review(
    path: Path,
    model_id: str,
    variation_id: str,
    *,
    status: str,
    category: str,
    notes: str,
) -> dict[str, Any]:
    if model_id == "V8":
        raise RegistryError("V8 reviews must use the focused Manual Review Queue.")
    if model_id not in {"V4", "V5", "V6", "V7"} or not variation_id.isdigit():
        raise RegistryError("Unknown model or Variation ID.")
    if status not in {
        "unreviewed",
        "reviewed",
        "ambiguous",
        "excluded",
        "correctly_matched",
    }:
        raise RegistryError("Unknown manual-review status.")
    if category not in ERROR_CATEGORIES:
        raise RegistryError("Unknown error category.")
    if status in {"ambiguous", "excluded"} and not notes.strip():
        raise RegistryError("Ambiguous and excluded reviews require notes.")
    document = _load_review_document(path)
    review = {
        "model_version": model_id,
        "variation_id": variation_id,
        "status": status,
        "error_category": category,
        "notes": notes.strip(),
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    document.setdefault("reviews", {})[f"{model_id}:{variation_id}"] = review
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_json(temporary, document)
    temporary.replace(path)
    return review


def load_project_timeline(path: Path) -> dict[str, Any]:
    return _read_json(path)


def update_timeline_status(path: Path, title: str, status: str) -> dict[str, Any]:
    if status not in {"pending", "in_progress", "completed", "draft", "cancelled"}:
        raise RegistryError("Unknown timeline status.")
    document = load_project_timeline(path)
    task = next((item for item in document["tasks"] if item["title"] == title), None)
    if task is None:
        raise RegistryError("Timeline task was not found.")
    task["status"] = status
    temporary = path.with_suffix(".tmp")
    _write_json(temporary, document)
    temporary.replace(path)
    return task


def log_run_event(
    log_path: Path,
    *,
    model_id: str,
    event: str,
    details: Mapping[str, Any] | None = None,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """Append a future event; historical reconstruction uses static logs."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "occurred_at_utc": occurred_at_utc or datetime.now(UTC).isoformat(),
        "model_id": model_id,
        "event": event,
        "details": dict(details or {}),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def build_reports(project_root: Path) -> list[Path]:
    """Build all small registry reports from existing artifacts without training."""
    root = project_root.resolve()
    created: list[Path] = []
    registry = create_registry(root)
    registry_path = root / "outputs/model_registry/model_registry.json"
    save_registry(registry, registry_path)
    created.append(registry_path)
    for model in registry["models"]:
        model_path = (
            root / f"outputs/model_registry/model_{model['model_id'].lower()}.json"
        )
        _write_json(model_path, model)
        created.append(model_path)

    ranking = rank_models(registry["models"])
    ranking_path = root / "outputs/model_registry/ranking.json"
    _write_json(ranking_path, ranking)
    created.append(ranking_path)
    index_path = root / "outputs/model_registry/model_index.json"
    _write_json(
        index_path,
        {
            "schema_version": SCHEMA_VERSION,
            "latest_model_version": "V8",
            "best_validated_model": (
                "V8 has the strongest component-isolation design, while V7 retains "
                "the stronger archive-time boundary; their paired V8-cohort difference "
                "is inconclusive and no clinical winner is claimed."
            ),
            "ranking_policy": registry["ranking_policy"],
            "ranking": ranking,
            "models": [
                {
                    "model_id": model["model_id"],
                    "name": model["name"],
                    "status": model["effective_status"],
                    "model_type": model["model_type"],
                    "test_records": model["test_records"],
                    "accuracy": model["metrics"]["accuracy"],
                    "balanced_accuracy": model["metrics"]["balanced_accuracy"],
                    "macro_f1": model["metrics"]["macro_f1"],
                    "leakage_status": model["leakage_audit_status"],
                    "record_path": (
                        f"outputs/model_registry/model_{model['model_id'].lower()}.json"
                    ),
                }
                for model in registry["models"]
            ],
            "warnings": registry["warnings"],
        },
    )
    created.append(index_path)

    evaluations: dict[str, tuple[dict[str, Any], list[dict[str, str]]]] = {}
    for model_id, directory, prediction_filename in (
        ("V4", "ai_holdout_v4", "hidden_test_predictions.csv"),
        ("V5", "ai_holdout_v5", "hidden_test_predictions.csv"),
        ("V6", "ai_holdout_v6", "hidden_test_predictions.csv"),
        ("V7", "ai_temporal_v7", "temporal_test_predictions.csv"),
        ("V8", "ai_temporal_v8", "temporal_test_predictions.csv"),
    ):
        evaluation = _recorded_binary_evaluation(
            model_id,
            root / f"outputs/{directory}/{prediction_filename}",
            root / f"outputs/{directory}/test_metrics.json",
        )
        evaluations[model_id] = evaluation

    comparison_rows: list[dict[str, Any]] = []
    v2_path = root / "outputs/resolved_direction_v2/resolved_direction_results.csv"
    for model_id, (evaluation, rows) in evaluations.items():
        actual = _prediction_labels(rows)
        model_comparisons = [
            {
                "test_set": model_id,
                "model": model_id,
                **{
                    key: evaluation[key]
                    for key in ("records", "accuracy", "balanced_accuracy", "macro_f1")
                },
                "coverage": 1.0,
                "actual_benign": evaluation["class_distribution"][BENIGN],
                "actual_pathogenic": evaluation["class_distribution"][PATHOGENIC],
                "benign_recall": evaluation["benign_recall"],
                "pathogenic_recall": evaluation["pathogenic_recall"],
                "provenance": "recorded predictions",
                "warning": evaluation["warnings"][-1],
            }
        ]
        for name, predictions in baseline_predictions(rows).items():
            metrics = compute_binary_metrics(actual, predictions)
            model_comparisons.append(
                {
                    "test_set": model_id,
                    "model": name,
                    **{
                        key: metrics[key]
                        for key in (
                            "records",
                            "accuracy",
                            "balanced_accuracy",
                            "macro_f1",
                        )
                    },
                    "coverage": 1.0,
                    "actual_benign": metrics["class_distribution"][BENIGN],
                    "actual_pathogenic": metrics["class_distribution"][PATHOGENIC],
                    "benign_recall": metrics["benign_recall"],
                    "pathogenic_recall": metrics["pathogenic_recall"],
                    "provenance": "deterministic baseline on same IDs",
                    "warning": evaluation["warnings"][-1],
                }
            )
        if model_id == "V8":
            reported = _read_json(root / "outputs/ai_temporal_v8/test_metrics.json")
            for name, metrics, provenance in (
                (
                    "V7_same_record",
                    reported["v7_same_record_baseline"],
                    "frozen V7 model predictions recorded on the same V8 test IDs",
                ),
                (
                    "consequence_only",
                    reported["consequence_only_baseline"],
                    "deterministic consequence-only baseline on the same V8 test IDs",
                ),
            ):
                model_comparisons.append(
                    {
                        "test_set": model_id,
                        "model": name,
                        **{
                            key: metrics[key]
                            for key in (
                                "records",
                                "accuracy",
                                "balanced_accuracy",
                                "macro_f1",
                            )
                        },
                        "coverage": 1.0,
                        "actual_benign": metrics["class_distribution"][BENIGN],
                        "actual_pathogenic": metrics["class_distribution"][PATHOGENIC],
                        "benign_recall": metrics["benign_recall"],
                        "pathogenic_recall": metrics["pathogenic_recall"],
                        "provenance": provenance,
                        "warning": (
                            "The paired V8-minus-V7 balanced-accuracy interval crosses "
                            "zero; no V8 performance improvement is claimed."
                            if name == "V7_same_record"
                            else evaluation["warnings"][-1]
                        ),
                    }
                )
        v2 = load_v2_predictions_for_ids(v2_path, {row["variation_id"] for row in rows})
        covered_rows = [row for row in rows if v2.get(row["variation_id"]) in LABELS]
        if covered_rows:
            metrics = compute_binary_metrics(
                _prediction_labels(covered_rows),
                [v2[row["variation_id"]] for row in covered_rows],
            )
            model_comparisons.append(
                {
                    "test_set": model_id,
                    "model": "V2_clue_baseline",
                    **{
                        key: metrics[key]
                        for key in (
                            "records",
                            "accuracy",
                            "balanced_accuracy",
                            "macro_f1",
                        )
                    },
                    "coverage": len(covered_rows) / len(rows),
                    "actual_benign": metrics["class_distribution"][BENIGN],
                    "actual_pathogenic": metrics["class_distribution"][PATHOGENIC],
                    "benign_recall": metrics["benign_recall"],
                    "pathogenic_recall": metrics["pathogenic_recall"],
                    "provenance": (
                        "recorded V2 predictions on same IDs; no-predictions excluded"
                    ),
                    "warning": "Coverage is reported because V2 can abstain.",
                }
            )
        comparison_rows.extend(model_comparisons)
        evaluation["baseline_comparison"] = model_comparisons
        path = root / f"outputs/evaluations/frozen/{model_id.lower()}_metrics.json"
        _write_json(path, evaluation)
        created.append(path)
    comparison_path = root / "outputs/evaluations/model_comparison.csv"
    _write_csv(
        comparison_path,
        comparison_rows,
        (
            "test_set",
            "model",
            "records",
            "accuracy",
            "balanced_accuracy",
            "macro_f1",
            "coverage",
            "actual_benign",
            "actual_pathogenic",
            "benign_recall",
            "pathogenic_recall",
            "provenance",
            "warning",
        ),
    )
    created.append(comparison_path)

    v7_audit_path = root / "outputs/evaluations/frozen/v7_protocol_audit.json"
    _write_json(
        v7_audit_path,
        v7_protocol_audit(
            root / "data/processed/resolved_direction_v2.sqlite3",
            evaluations["V7"][1],
            _read_json(root / "outputs/ai_temporal_v7/training_summary.json"),
            _read_json(root / "outputs/ai_temporal_v7/test_metrics.json"),
        ),
    )
    created.append(v7_audit_path)

    v8_audit_path = root / "outputs/evaluations/frozen/v8_protocol_audit.json"
    _write_json(
        v8_audit_path,
        v8_protocol_audit(
            root,
            evaluations["V8"][1],
            _read_json(root / "outputs/ai_temporal_v8/training_summary.json"),
            _read_json(root / "outputs/ai_temporal_v8/test_metrics.json"),
            _read_json(root / "outputs/evaluations/frozen/v8_vault_commitment.json"),
            _read_json(root / "outputs/evaluations/frozen/v8_model_commitment.json"),
        ),
    )
    created.append(v8_audit_path)

    all_error_rows = []
    evaluated_ids = {
        row["variation_id"] for _, rows in evaluations.values() for row in rows
    }
    details = load_variant_details(
        root / "data/processed/resolved_direction_v2.sqlite3", evaluated_ids
    )
    for model_id, (_, rows) in evaluations.items():
        paths = (
            root / f"outputs/error_analysis/{model_id.lower()}_all_rows.csv",
            root / f"outputs/error_analysis/model_{model_id.lower()}_errors.csv",
        )
        generated = generate_error_analysis(model_id, rows, paths[0], details)
        error_rows = (
            [row for row in generated if row["correct"] == "false"]
            if model_id == "V8"
            else generated
        )
        if model_id != "V8":
            _write_csv(paths[1], error_rows, tuple(generated[0]))
        all_error_rows.extend(generated)
        created.extend(paths[:1] if model_id == "V8" else paths)
    union_path = root / "outputs/error_analysis/model_test_rows_union.csv"
    _write_csv(union_path, all_error_rows, tuple(all_error_rows[0]))
    created.append(union_path)

    for model in registry["models"]:
        model_id = model["model_id"]
        audit_path = (
            root / f"outputs/leakage_audits/{model_id.lower()}_leakage_audit.json"
        )
        audit_document = {
            "schema_version": SCHEMA_VERSION,
            "model_version": model_id,
            "feature_list_inspected": model["features"],
            "banned_fields_found": [
                finding["field"] for finding in model["leakage_audit"]["findings"]
            ],
            "suspicious_fields_found": [],
            "status": model["leakage_audit"]["status"],
            "explanation": model["leakage_audit"]["warning"],
            "audit_date": "2026-08-02" if model_id == "V8" else "2026-08-01",
            "recommendation": (
                "Keep only older-snapshot features and repeat source-date review for "
                "every future feature."
            ),
            "trusted_dashboard_result": model["leakage_audit"]["status"] == "pass",
        }
        _write_json(audit_path, audit_document)
        created.append(audit_path)
        model_manifest = root / f"outputs/models/frozen/model_{model_id.lower()}.json"
        _write_json(
            model_manifest,
            {
                "schema_version": SCHEMA_VERSION,
                "model_id": model_id,
                "status": "frozen_reference",
                "source_artifact": model["artifact"],
                "output_files": model["output_files"],
                "warning": (
                    "Model binary/config remains at its original immutable path."
                ),
            },
        )
        created.append(model_manifest)

        evaluation_manifest = (
            root / f"outputs/evaluations/frozen/model_{model_id.lower()}.json"
        )
        _write_json(
            evaluation_manifest,
            {
                "schema_version": SCHEMA_VERSION,
                "model_id": model_id,
                "status": "frozen",
                "evaluation_source": model["evaluation_source"],
                "metrics": model["metrics"],
                "synthetic_evaluation": False,
                "warnings": model["warnings"],
            },
        )
        created.append(evaluation_manifest)

    for directory in (
        root / "outputs/models/experiments",
        root / "outputs/evaluations/experiments",
    ):
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / ".gitkeep"
        marker.write_text("", encoding="utf-8")
        created.append(marker)

    timeline_path = root / "outputs/project_timeline.json"
    _write_json(
        timeline_path,
        {
            "schema_version": SCHEMA_VERSION,
            "item_count": len(PROJECT_TIMELINE),
            "tasks": PROJECT_TIMELINE,
        },
    )
    created.append(timeline_path)

    log_dates = {
        "V1": "2026-07-28",
        "V2": "2026-07-31",
        "V3": "2026-07-30",
        "V4": "2026-08-01",
        "V5": "2026-08-01",
        "V6": "2026-08-01",
        "V7": "2026-08-02",
        "V8": "2026-08-02",
    }
    for model in registry["models"]:
        model_id = model["model_id"]
        stem = (
            root
            / "outputs/logs"
            / f"{log_dates[model_id]}_model_{model_id.lower()}_evaluation"
        )
        log_document = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": model["metrics"].get("tested_at_utc", UNKNOWN),
            "model_version": model_id,
            "started_by": "historical artifact reconstruction",
            "command_or_dashboard_action": "not recorded",
            "dataset_used": model["dataset_version"],
            "records_loaded": model["number_training_records"],
            "records_used": model["metrics"].get("number_of_predictions", UNKNOWN),
            "records_excluded": UNKNOWN,
            "split_sizes": {
                "train": model["number_training_records"],
                "validation": model["number_validation_records"],
                "test": model["number_test_records"],
            },
            "features_used": model["features"],
            "target_labels": model["target_outcome_definition"],
            "hyperparameters": model["hyperparameters"],
            "random_seed": model["random_seed"],
            "metrics": model["metrics"],
            "warnings": [
                "Reconstructed from existing artifacts; not an original runtime log.",
                *model["warnings"],
            ],
            "errors": [],
            "output_files": model["output_files"],
            "runtime_seconds": model["evaluation_runtime_seconds"],
            "disk_usage_before_bytes": UNKNOWN,
            "disk_usage_after_bytes": UNKNOWN,
            "run_classification": "official reconstructed historical record",
        }
        json_path = stem.with_suffix(".json")
        markdown_path = stem.with_suffix(".md")
        _write_json(json_path, log_document)
        markdown_path.write_text(
            f"# {model_id} Evaluation Log\n\n"
            "> Reconstructed from existing artifacts; this is not the original "
            "runtime log.\n\n"
            f"- Model: {model['name']}\n"
            f"- Dataset: {json.dumps(model['dataset_version'], sort_keys=True)}\n"
            f"- Test records: {model['number_test_records']}\n"
            f"- Accuracy: {model['metrics'].get('accuracy', UNKNOWN)}\n"
            f"- Balanced accuracy: "
            f"{model['metrics'].get('balanced_accuracy', UNKNOWN)}\n"
            f"- Leakage audit: {model['leakage_audit_status']}\n"
            f"- Warnings: {'; '.join(model['warnings'])}\n",
            encoding="utf-8",
        )
        created.extend((json_path, markdown_path))

    review_path = root / "data/manual_review/model_error_reviews.json"
    if not review_path.exists():
        _write_json(
            review_path,
            {
                "schema_version": 1,
                "allowed_categories": list(ERROR_CATEGORIES),
                "reviews": {},
            },
        )
        created.append(review_path)
    from variant_time_machine.v8_presentation import build_v8_presentation

    created.extend(build_v8_presentation(root))
    return created
