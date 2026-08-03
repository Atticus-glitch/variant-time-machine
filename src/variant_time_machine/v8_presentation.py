"""Read-only V8 presentation data and separate manual-review persistence."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DECISIONS: tuple[str, ...] = (
    "not_reviewed",
    "match_correct_model_wrong",
    "match_correct_model_right",
    "ambiguous_condition_scope",
    "ambiguous_aggregation",
    "bad_match",
    "possible_label_problem",
    "conflicting_classification_scope",
    "missing_critical_fields",
    "exclude_non_germline_or_wrong_scope",
    "duplicate_or_related_record_problem",
    "uncertain_manual_review",
    "needs_expert_review",
)
ERROR_CATEGORIES: tuple[str, ...] = (
    "genuine_model_error",
    "false_positive_pathogenic_direction",
    "false_negative_pathogenic_direction",
    "condition_scope_changed",
    "aggregate_label_ambiguous",
    "poor_match",
    "missing_features",
    "misleading_consequence",
    "weak_old_evidence",
    "review_status_shift",
    "gene_or_component_generalization_failure",
    "label_noise",
    "non_germline_scope",
    "unknown",
)
REVIEWER_CONFIDENCES = ("high", "medium", "low")
PREDICTOR_INDEX_SHA256 = (
    "a9e0fe334d5286e176dd8367aa5f37f2fe9114b3a6f081cb5aab516c3845dfa4"
)
NOTE_REQUIRED = {
    "bad_match",
    "possible_label_problem",
    "uncertain_manual_review",
    "needs_expert_review",
}
MAX_NOTE_LENGTH = 5000
CASE_STUDY_SALT = "v8-case-studies-2026-08-02"
CORRECT_SAMPLE_SALT = "v8-review-correct-sample-v2-2026-08-02"
LOW_CONFIDENCE_SAMPLE_SALT = "v8-review-low-confidence-v2-2026-08-02"
CORRECT_SAMPLE_SIZE_PER_GROUP = 25
LOW_CONFIDENCE_SAMPLE_SIZE = 25
HIGH_CONFIDENCE_THRESHOLD = 0.8
LOW_CONFIDENCE_THRESHOLD = 0.6
FROZEN_SOURCE_HASHES = {
    "outputs/ai_temporal_v8/temporal_test_predictions.csv": (
        "13d366749fa913accbced30ac574232fd9f56c695691b96e64b11d2a59427f54"
    ),
    "outputs/error_analysis/v8_all_rows.csv": (
        "5c0046d942342f8e12296baf4fe4cecf9caa70a29c18a541f6e9d42249e9d74e"
    ),
    "outputs/evaluations/frozen/v8_metrics.json": (
        "eaba198cfe74a316c7b8aa89aee516a3cb59922522de92b1264225684ebe5974"
    ),
    "outputs/evaluations/frozen/v8_protocol_audit.json": (
        "1e6c0682c427776e195aa58ea2b8fb3a55cf6207666cd661e29e10ce63dd4551"
    ),
    "outputs/ai_temporal_v8/model.joblib": (
        "295e3bc9218df672764fa9819d797acdfbf074326b6a2e5468b24d5b77b6f4e8"
    ),
}
PUBLIC_WARNING = (
    "V8 is a retrospective historical model using public ClinVar aggregate data. "
    "It is not medical advice, not clinical validation, and not a tool for "
    "interpreting patient variants. It does not support clinical use."
)
STRONGEST_TRUTHFUL_CLAIM = (
    "In a retrospective historical ClinVar experiment, Variant Time Machine "
    "predicted later resolved classification direction for older VUS records using "
    "only older-snapshot features. V8 achieved 89.5% accuracy and 87.1% balanced "
    "accuracy on a 1,000-record gene-component-disjoint retrospective test. However, "
    "a paired same-record comparison with V7 showed no statistically clear overall "
    "superiority, so the result supports V8 as a strong simplified retrospective "
    "model, not as a clinically validated predictor."
)
SUGGESTED_CATEGORIES = (
    "possible condition-scope issue",
    "possible match ambiguity",
    "possible aggregate-classification ambiguity",
    "possible missing consequence",
    "possible weak feature signal",
    "predicted benign but later pathogenic",
    "predicted pathogenic but later benign",
)
ERROR_FIELDS = (
    "model_version",
    "variation_id",
    "vcv_accession",
    "gene",
    "actual_outcome",
    "predicted_class",
    "pathogenic_probability",
    "confidence",
    "high_confidence",
    "error_type",
    "old_classification",
    "actual_later_classification",
    "review_status",
    "manual_review_status",
    "consequence",
    "key_features",
    "match_confidence",
    "warning_flags",
    "notes",
    "suggested_category",
    "suggestion_status",
    "leakage_audit_status",
    "source",
    "source_predictions_sha256",
)
QUEUE_FIELDS = (
    "queue_order",
    "priority",
    "priority_score",
    "reasons",
    "model_version",
    "variation_id",
    "vcv_accession",
    "allele_id",
    "rcv_accessions",
    "gene",
    "component_hash",
    "old_snapshot_date",
    "new_snapshot_date",
    "old_classification_text",
    "new_classification_text",
    "normalized_old_outcome",
    "normalized_new_outcome",
    "actual_outcome",
    "predicted_class",
    "v8_probability",
    "confidence",
    "high_confidence",
    "correct",
    "confusion_group",
    "error_type",
    "v7_prediction",
    "v7_probability",
    "v8_v7_disagreement",
    "correct_sample",
    "low_confidence_sample",
    "old_classification",
    "actual_later_classification",
    "match_method",
    "old_condition_text",
    "new_condition_text",
    "old_review_status",
    "new_review_status",
    "review_status",
    "manual_review_status",
    "consequence",
    "old_consequence_fields",
    "key_features",
    "feature_values_used_by_v8",
    "feature_contributions",
    "model_explanation",
    "match_confidence",
    "warning_flags",
    "automatic_review_flags",
    "official_source_links",
    "field_provenance",
    "suggested_category",
    "suggestion_status",
    "source",
    "source_predictions_sha256",
)
_NOTES_LOCK = threading.RLock()


class V8PresentationError(ValueError):
    """Raised when presentation data or a review update is invalid."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one source artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _direction(value: str) -> str:
    if value.startswith("moved_toward_"):
        return value
    return f"moved_toward_{value}"


def _row_values(row: dict[str, str]) -> tuple[str, str, float, float, bool, str]:
    actual = _direction(row["actual_outcome"])
    predicted = _direction(row.get("v8_prediction", row.get("predicted_class", "")))
    probability = float(
        row.get("v8_probability", row.get("pathogenic_probability", "0"))
    )
    confidence = probability if predicted.endswith("pathogenic") else 1 - probability
    correct = actual == predicted
    group = (
        "TP"
        if correct and actual.endswith("pathogenic")
        else "TN"
        if correct
        else "FP"
        if actual.endswith("benign")
        else "FN"
    )
    return actual, predicted, probability, confidence, correct, group


def _suggested_category(
    group: str,
    consequence: str,
    confidence: float,
    context: dict[str, str] | None = None,
) -> str:
    context = context or {}
    warning_text = " ".join(
        (context.get("warning_flags", ""), context.get("notes", ""))
    ).casefold()
    match_confidence = context.get("match_confidence", "not recorded").casefold()
    if "condition" in warning_text or "scope" in warning_text:
        return "possible condition-scope issue"
    if match_confidence not in {"high", "not recorded", ""} or "match" in warning_text:
        return "possible match ambiguity"
    if "aggregate" in warning_text or "conflict" in warning_text:
        return "possible aggregate-classification ambiguity"
    if consequence == "unrecognized":
        return "possible missing consequence"
    if confidence < HIGH_CONFIDENCE_THRESHOLD:
        return "possible weak feature signal"
    if group == "FP":
        return "predicted pathogenic but later benign"
    if group == "FN":
        return "predicted benign but later pathogenic"
    return "possible weak feature signal"


def _context(contexts: dict[str, dict[str, str]], identifier: str) -> dict[str, str]:
    return contexts.get(identifier, {})


def _old_classification(context: dict[str, str]) -> str:
    value = context.get("old_classification", "").strip()
    return value if value and value != "not recorded" else "Uncertain significance"


def build_error_rows(
    rows: list[dict[str, str]],
    contexts: dict[str, dict[str, str]],
    predictions_sha256: str,
) -> list[dict[str, str]]:
    """Transform recorded wrong predictions into a stable public error table."""
    errors: list[dict[str, str]] = []
    for row in rows:
        actual, predicted, probability, confidence, correct, group = _row_values(row)
        if correct:
            continue
        context = _context(contexts, row["variation_id"])
        consequence = row.get("consequence") or context.get(
            "consequence", "not recorded"
        )
        errors.append(
            {
                "model_version": "V8",
                "variation_id": row["variation_id"],
                "vcv_accession": context.get("vcv_accession", "not recorded"),
                "gene": row.get("gene_symbols", row.get("gene", "not recorded")),
                "actual_outcome": actual,
                "predicted_class": predicted,
                "pathogenic_probability": str(probability),
                "confidence": str(confidence),
                "high_confidence": str(confidence >= HIGH_CONFIDENCE_THRESHOLD).lower(),
                "error_type": group,
                "old_classification": _old_classification(context),
                "actual_later_classification": row.get(
                    "answer_classification",
                    context.get("actual_later_classification", "not recorded"),
                ),
                "review_status": context.get("review_status", "not recorded"),
                "manual_review_status": context.get(
                    "manual_review_status", "unreviewed"
                ),
                "consequence": consequence,
                "key_features": context.get(
                    "key_features", f"consequence={consequence}"
                ),
                "match_confidence": context.get("match_confidence", "not recorded"),
                "warning_flags": context.get("warning_flags", ""),
                "notes": "",
                "suggested_category": _suggested_category(
                    group, consequence, confidence, context
                ),
                "suggestion_status": "unverified",
                "leakage_audit_status": "pass",
                "source": "outputs/ai_temporal_v8/temporal_test_predictions.csv",
                "source_predictions_sha256": predictions_sha256,
            }
        )
    return errors


def _predictor_contexts(
    database: Path, rows: list[dict[str, str]], model_path: Path
) -> dict[str, dict[str, str]]:
    """Rejoin committed predictor-time evidence and explain frozen V8 inputs."""
    import joblib

    from variant_time_machine.ai_temporal_v8 import V8_FEATURE_NAMES, v8_features

    if not database.is_file() or not model_path.is_file():
        raise V8PresentationError(
            "V8 predictor evidence or frozen model is unavailable."
        )
    if sha256_file(database) != PREDICTOR_INDEX_SHA256:
        raise V8PresentationError(
            "Committed V8 predictor index hash changed; refusing review generation."
        )
    artifact = joblib.load(model_path)
    pipeline = artifact["base_model"]
    scaler = pipeline.named_steps["scale"]
    classifier = pipeline.named_steps["model"]
    coefficients = classifier.coef_[0]
    contexts: dict[str, dict[str, str]] = {}
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for prediction in rows:
            source_row = connection.execute(
                "SELECT * FROM variant_release "
                "WHERE release_role='newer' AND variation_id=?",
                (prediction["variation_id"],),
            ).fetchone()
            if source_row is None:
                raise V8PresentationError(
                    "A V8 test ID is missing from the committed predictor index: "
                    f"{prediction['variation_id']}"
                )
            source = dict(source_row)
            values = v8_features(source, str(source["release_date"]))
            standardized = scaler.transform([values])[0]
            contributions = [
                {
                    "feature": name,
                    "value": float(value),
                    "coefficient": float(coefficient),
                    "standardized_logit_contribution": float(scaled * coefficient),
                }
                for name, value, scaled, coefficient in zip(
                    V8_FEATURE_NAMES,
                    values,
                    standardized,
                    coefficients,
                    strict=True,
                )
            ]
            top = sorted(
                contributions,
                key=lambda item: abs(item["standardized_logit_contribution"]),
                reverse=True,
            )[:10]
            explanation = "; ".join(
                f"{item['feature']} ({item['standardized_logit_contribution']:+.3f})"
                for item in top[:5]
            )
            rcv_values = str(source.get("rcv_accessions") or "not recorded")
            links = [
                {
                    "label": "Official ClinVar variation",
                    "url": (
                        "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
                        f"{prediction['variation_id']}/"
                    ),
                }
            ]
            first_rcv = re.search(r"RCV\d+", rcv_values)
            if first_rcv:
                links.append(
                    {
                        "label": "Official ClinVar RCV record",
                        "url": (
                            "https://www.ncbi.nlm.nih.gov/clinvar/"
                            f"{first_rcv.group(0)}/"
                        ),
                    }
                )
            contexts[prediction["variation_id"]] = {
                "vcv_accession": "not recorded",
                "allele_id": str(source.get("allele_ids") or "not recorded"),
                "rcv_accessions": rcv_values,
                "old_snapshot_date": str(source["release_date"]),
                "new_snapshot_date": "2026-07",
                "old_classification": str(
                    source.get("clinical_significances") or "not recorded"
                ),
                "old_condition_text": str(source.get("phenotypes") or "not recorded"),
                "new_condition_text": "not recorded",
                "old_review_status": str(
                    source.get("review_statuses") or "not recorded"
                ),
                "new_review_status": "not recorded",
                "review_status": str(source.get("review_statuses") or "not recorded"),
                "match_method": "exact Variation ID and unchanged Allele ID set",
                "match_confidence": "high under frozen temporal rule",
                "origins": str(source.get("origin_simple_values") or "not recorded"),
                "coordinates": str(source.get("coordinates") or "not recorded"),
                "old_consequence_fields": json.dumps(
                    {
                        "derived_consequence": prediction.get(
                            "consequence", "not recorded"
                        ),
                        "names": source.get("names") or "not recorded",
                        "variant_types": source.get("variant_types") or "not recorded",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "feature_values_used_by_v8": json.dumps(
                    dict(zip(V8_FEATURE_NAMES, values, strict=True)),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "feature_contributions": json.dumps(
                    top, sort_keys=True, separators=(",", ":")
                ),
                "model_explanation": (
                    "Largest standardized base-logit contributions: "
                    f"{explanation}. The displayed V8 probability was subsequently "
                    "calibrated, so these are directional explanations rather than "
                    "additive contributions to the final probability."
                ),
                "official_source_links": json.dumps(
                    links, sort_keys=True, separators=(",", ":")
                ),
                "field_provenance": json.dumps(
                    {
                        "predictor_fields": (
                            "rejoined from committed January 2024 predictor index"
                        ),
                        "prediction_and_outcome": (
                            "frozen V8 temporal_test_predictions.csv"
                        ),
                        "unavailable_later_fields": "not recorded",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
    return contexts


def _automatic_flags(
    row: dict[str, str],
    context: dict[str, str],
    *,
    confidence: float,
    correct: bool,
    disagreement: bool,
    component_size: int,
) -> list[str]:
    """Return conservative computer suggestions, never manual conclusions."""
    flags: list[str] = []
    if context.get("vcv_accession") in {"", "not recorded", None}:
        flags.append("vcv_missing")
    if not row.get("gene_symbols"):
        flags.append("gene_missing")
    if context.get("coordinates") in {"", "not recorded", None}:
        flags.append("coordinates_missing")
    if "high" not in context.get("match_confidence", "").casefold():
        flags.append("match_confidence_below_high")
    classification = row.get("answer_classification", "").casefold()
    if "conflict" in classification:
        flags.append("classification_contains_conflicting")
    origins = context.get("origins", "").casefold()
    if origins and origins != "not recorded" and "germline" not in origins:
        flags.append("possible_non_germline_scope")
    if row.get("consequence", "") in {"", "unrecognized"}:
        flags.append("consequence_missing_or_unrecognized")
    if not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        flags.append("v8_high_confidence_wrong")
    if disagreement:
        flags.append("v8_v7_disagreement")
    if component_size > 1:
        flags.append("possible_related_component_group")
    return flags


def build_review_queue(
    rows: list[dict[str, str]],
    contexts: dict[str, dict[str, str]],
    predictions_sha256: str,
) -> list[dict[str, str]]:
    """Build the deterministic error, disagreement, warning, and control queue."""
    component_sizes: dict[str, int] = {}
    for row in rows:
        component = row.get("component_hash", "")
        component_sizes[component] = component_sizes.get(component, 0) + 1

    correct_sample_ids: set[str] = set()
    for group in ("TN", "TP"):
        pool = [row for row in rows if _row_values(row)[5] == group]
        pool.sort(
            key=lambda row: hashlib.sha256(
                f"{CORRECT_SAMPLE_SALT}:{group}:{row['variation_id']}".encode()
            ).hexdigest()
        )
        correct_sample_ids.update(
            row["variation_id"] for row in pool[:CORRECT_SAMPLE_SIZE_PER_GROUP]
        )

    low_confidence_pool = [
        row for row in rows if _row_values(row)[3] < LOW_CONFIDENCE_THRESHOLD
    ]
    low_confidence_pool.sort(
        key=lambda row: hashlib.sha256(
            f"{LOW_CONFIDENCE_SAMPLE_SALT}:{row['variation_id']}".encode()
        ).hexdigest()
    )
    low_confidence_ids = {
        row["variation_id"] for row in low_confidence_pool[:LOW_CONFIDENCE_SAMPLE_SIZE]
    }

    candidates: list[tuple[float, int, dict[str, str], list[str]]] = []
    for row in rows:
        actual, predicted, probability, confidence, correct, group = _row_values(row)
        v7 = _direction(row.get("v7_prediction", ""))
        disagreement = bool(row.get("v7_prediction")) and v7 != predicted
        context = _context(contexts, row["variation_id"])
        flags = _automatic_flags(
            row,
            context,
            confidence=confidence,
            correct=correct,
            disagreement=disagreement,
            component_size=component_sizes.get(row.get("component_hash", ""), 1),
        )
        reasons: list[str] = []
        if group == "FN":
            reasons.append("false negative")
            score = 1000 + confidence * 100
        elif group == "FP":
            reasons.append("false positive")
            score = 800 + confidence * 100
        elif disagreement:
            score = 600 + confidence * 50
        elif flags:
            score = 400 + confidence * 25
        elif row["variation_id"] in correct_sample_ids:
            score = 200 + confidence * 10
        elif row["variation_id"] in low_confidence_ids:
            score = 100 + (1 - confidence) * 10
        else:
            continue
        if not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD:
            reasons.append("high-confidence wrong")
            score += 25
        if disagreement:
            reasons.append("V8/V7 disagreement")
        if flags:
            reasons.append("automatic review flags")
        if row["variation_id"] in correct_sample_ids:
            reasons.append(f"seeded correct {group} sample")
        if row["variation_id"] in low_confidence_ids:
            reasons.append("seeded low-confidence sample")
        candidates.append((score, int(row["variation_id"]), row, flags))
    candidates.sort(key=lambda item: (-item[0], item[1]))

    queue: list[dict[str, str]] = []
    for order, (score, _, row, flags) in enumerate(candidates, start=1):
        actual, predicted, probability, confidence, correct, group = _row_values(row)
        context = _context(contexts, row["variation_id"])
        consequence = row.get("consequence") or context.get(
            "consequence", "not recorded"
        )
        v7 = _direction(row.get("v7_prediction", ""))
        disagreement = bool(row.get("v7_prediction")) and v7 != predicted
        reason_labels: list[str] = []
        if group == "FN":
            reason_labels.append("false negative")
        elif group == "FP":
            reason_labels.append("false positive")
        if not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD:
            reason_labels.append("high-confidence wrong")
        if disagreement:
            reason_labels.append("V8/V7 disagreement")
        if flags:
            reason_labels.append("automatic review flags")
        if row["variation_id"] in correct_sample_ids:
            reason_labels.append(f"seeded correct {group} sample")
        if row["variation_id"] in low_confidence_ids:
            reason_labels.append("seeded low-confidence sample")
        queue.append(
            {
                "queue_order": str(order),
                "priority": "high" if group in {"FN", "FP"} else "medium",
                "priority_score": f"{score:.6f}",
                "reasons": "; ".join(reason_labels),
                "model_version": "V8",
                "variation_id": row["variation_id"],
                "vcv_accession": context.get("vcv_accession", "not recorded"),
                "allele_id": context.get("allele_id", "not recorded"),
                "rcv_accessions": context.get("rcv_accessions", "not recorded"),
                "gene": row.get("gene_symbols", row.get("gene", "not recorded")),
                "component_hash": row.get("component_hash", "not recorded"),
                "old_snapshot_date": context.get("old_snapshot_date", "not recorded"),
                "new_snapshot_date": context.get("new_snapshot_date", "not recorded"),
                "old_classification_text": _old_classification(context),
                "new_classification_text": row.get(
                    "answer_classification", "not recorded"
                ),
                "normalized_old_outcome": "uncertain",
                "normalized_new_outcome": actual,
                "actual_outcome": actual,
                "predicted_class": predicted,
                "v8_probability": str(probability),
                "confidence": str(confidence),
                "high_confidence": str(
                    not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD
                ).lower(),
                "correct": str(correct).lower(),
                "confusion_group": group,
                "error_type": "" if correct else group,
                "v7_prediction": v7,
                "v7_probability": row.get("v7_probability", ""),
                "v8_v7_disagreement": str(disagreement).lower(),
                "correct_sample": str(
                    row["variation_id"] in correct_sample_ids
                ).lower(),
                "low_confidence_sample": str(
                    row["variation_id"] in low_confidence_ids
                ).lower(),
                "old_classification": _old_classification(context),
                "actual_later_classification": row.get(
                    "answer_classification",
                    context.get("actual_later_classification", "not recorded"),
                ),
                "match_method": context.get("match_method", "not recorded"),
                "old_condition_text": context.get("old_condition_text", "not recorded"),
                "new_condition_text": context.get("new_condition_text", "not recorded"),
                "old_review_status": context.get("old_review_status", "not recorded"),
                "new_review_status": context.get("new_review_status", "not recorded"),
                "review_status": context.get("review_status", "not recorded"),
                "manual_review_status": context.get(
                    "manual_review_status", "unreviewed"
                ),
                "consequence": consequence,
                "old_consequence_fields": context.get("old_consequence_fields", "{}"),
                "key_features": context.get(
                    "key_features", f"consequence={consequence}"
                ),
                "feature_values_used_by_v8": context.get(
                    "feature_values_used_by_v8", "{}"
                ),
                "feature_contributions": context.get("feature_contributions", "[]"),
                "model_explanation": context.get("model_explanation", "not recorded"),
                "match_confidence": context.get("match_confidence", "not recorded"),
                "warning_flags": json.dumps(flags, separators=(",", ":")),
                "automatic_review_flags": json.dumps(flags, separators=(",", ":")),
                "official_source_links": context.get("official_source_links", "[]"),
                "field_provenance": context.get("field_provenance", "{}"),
                "suggested_category": _suggested_category(
                    group, consequence, confidence, context
                ),
                "suggestion_status": "unverified",
                "source": "outputs/ai_temporal_v8/temporal_test_predictions.csv",
                "source_predictions_sha256": predictions_sha256,
            }
        )
    return queue


def build_case_studies(
    rows: list[dict[str, str]],
    contexts: dict[str, dict[str, str]],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Select up to five stable cases from each confusion group."""
    grouped: dict[str, list[dict[str, str]]] = {
        key: [] for key in ("TN", "TP", "FP", "FN")
    }
    for row in rows:
        grouped[_row_values(row)[5]].append(row)
    selected_ids: dict[str, list[str]] = {}
    cases: list[dict[str, Any]] = []
    for group in ("TN", "TP", "FP", "FN"):
        selected = sorted(
            grouped[group],
            key=lambda row: hashlib.sha256(
                f"{CASE_STUDY_SALT}:{row['variation_id']}".encode()
            ).hexdigest(),
        )[:5]
        selected_ids[group] = [row["variation_id"] for row in selected]
        for row in selected:
            actual, predicted, probability, confidence, correct, _ = _row_values(row)
            context = _context(contexts, row["variation_id"])
            consequence = row.get("consequence") or context.get(
                "consequence", "not recorded"
            )
            cases.append(
                {
                    "variation_id": row["variation_id"],
                    "vcv_accession": context.get("vcv_accession", "not recorded"),
                    "gene": row.get("gene_symbols", row.get("gene", "not recorded")),
                    "old_classification": _old_classification(context),
                    "later_classification": row.get(
                        "answer_classification",
                        context.get("actual_later_classification", "not recorded"),
                    ),
                    "actual_direction": actual,
                    "predicted_direction": predicted,
                    "v8_probability": probability,
                    "confidence": confidence,
                    "correct": correct,
                    "confusion_group": group,
                    "consequence": consequence,
                    "key_features": context.get(
                        "key_features", f"consequence={consequence}"
                    ),
                    "match_confidence": context.get("match_confidence", "not recorded"),
                    "review_status": context.get("review_status", "not recorded"),
                    "warnings": [PUBLIC_WARNING],
                    "source_links": [
                        {
                            "label": "ClinVar Variation ID",
                            "url": (
                                "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
                                f"{row['variation_id']}/"
                            ),
                        }
                    ],
                    "manual_status": context.get("manual_review_status", "unreviewed"),
                }
            )
    return {
        "schema_version": 1,
        "model_id": "V8",
        "case_studies": cases,
        "selection": {
            "method": (
                "Within each frozen confusion group, rank Variation IDs by ascending "
                "SHA-256(salt + ':' + variation_id) and take the first five."
            ),
            "salt": CASE_STUDY_SALT,
            "random_at_page_load": False,
            "count_per_group": 5,
            "selected_ids": selected_ids,
        },
        "provenance": provenance,
        "warning": PUBLIC_WARNING,
    }


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V8PresentationError(f"Expected a JSON object in {path}")
    return value


def build_public_summary(
    metrics: dict[str, Any], audit: dict[str, Any], provenance: dict[str, Any]
) -> dict[str, Any]:
    """Build the exact public aggregate from frozen metrics and audit fields."""
    matrix = metrics["confusion_matrix"]
    summary_matrix = {
        "TN": int(matrix["actual_benign"]["predicted_benign"]),
        "FP": int(matrix["actual_benign"]["predicted_pathogenic"]),
        "FN": int(matrix["actual_pathogenic"]["predicted_benign"]),
        "TP": int(matrix["actual_pathogenic"]["predicted_pathogenic"]),
    }
    expected = {"TN": 740, "FP": 74, "FN": 31, "TP": 155}
    if summary_matrix != expected or audit.get("status") != "pass":
        raise V8PresentationError("Frozen V8 metrics or protocol audit changed.")
    paired_interval = audit["paired_difference_95_percent"]
    if not paired_interval[0] <= 0 <= paired_interval[1]:
        raise V8PresentationError(
            "The recorded V8/V7 paired interval no longer crosses zero."
        )
    v7 = metrics["v7_same_record_baseline"]
    return {
        "schema_version": 1,
        "model_id": "V8",
        "model_type": "calibrated elastic-net logistic regression",
        "evaluation": "sealed_gene_component_disjoint_retrospective_temporal_test",
        "n": int(metrics["records"]),
        "accuracy": metrics["accuracy"],
        "balanced_accuracy": metrics["balanced_accuracy"],
        "macro_f1": metrics["macro_f1"],
        "recalls": {
            "benign": metrics["benign_recall"],
            "pathogenic": metrics["pathogenic_recall"],
        },
        "confusion_matrix": summary_matrix,
        "correct": int(metrics["number_correct"]),
        "wrong": int(metrics["number_wrong"]),
        "sealed_gene_components": int(metrics["sealed_gene_components"]),
        "leakage_audit": {
            "status": "pass",
            "scope": "Recorded V8 protocol, artifact-hash, and overlap checks.",
        },
        "v7_same_record": {
            "n": int(v7["records"]),
            "accuracy": v7["accuracy"],
            "balanced_accuracy": v7["balanced_accuracy"],
            "macro_f1": v7["macro_f1"],
            "recalls": {
                "benign": v7["benign_recall"],
                "pathogenic": v7["pathogenic_recall"],
            },
            "v8_minus_v7_balanced_accuracy": metrics["v8_minus_v7_balanced_accuracy"],
            "paired_difference_95_percent": paired_interval,
            "interval_crosses_zero": True,
            "claim": "No V8 performance improvement over V7 is claimed.",
        },
        "strongest_claim": STRONGEST_TRUTHFUL_CLAIM,
        "warning": PUBLIC_WARNING,
        "caveats": [
            (
                "The test is outcome-selected: it scores records with a safe clear "
                "later direction, not whether a VUS will resolve."
            ),
            (
                "The 1,000 records span 559 predictor-time gene components and are "
                "not 1,000 independent gene samples."
            ),
            (
                "The July 2026 archive had already been accessed for V7, and V8 "
                "membership is reconstructible from the published salt and archive."
            ),
            (
                "Combined component and class weighting was not strictly equal in "
                "total per component."
            ),
            (
                "The simplicity tie-break did not rank regularization strengths "
                "within the selected model family."
            ),
            (
                "Grouped out-of-fold labels were reused for selection, calibration, "
                "and threshold choice."
            ),
        ],
        "provenance": provenance,
    }


def build_v8_presentation(project_root: Path) -> list[Path]:
    """Build presentation derivatives without altering source artifacts or notes."""
    root = project_root.resolve()
    predictions_path = (
        root / "outputs" / "ai_temporal_v8" / "temporal_test_predictions.csv"
    )
    all_rows_path = root / "outputs" / "error_analysis" / "v8_all_rows.csv"
    metrics_path = root / "outputs" / "evaluations" / "frozen" / "v8_metrics.json"
    audit_path = root / "outputs" / "evaluations" / "frozen" / "v8_protocol_audit.json"
    for relative, expected_hash in FROZEN_SOURCE_HASHES.items():
        actual_hash = sha256_file(root / relative)
        if actual_hash != expected_hash:
            raise V8PresentationError(
                f"Frozen V8 presentation source hash changed: {relative}"
            )
    with predictions_path.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    with all_rows_path.open(encoding="utf-8", newline="") as input_file:
        base_contexts = {
            row["variation_id"]: row
            for row in csv.DictReader(input_file)
            if row.get("variation_id")
        }
    review_contexts = {
        identifier: dict(context) for identifier, context in base_contexts.items()
    }
    predictor_contexts = _predictor_contexts(
        root / "data" / "processed" / "clinvar_history.sqlite3",
        rows,
        root / "outputs" / "ai_temporal_v8" / "model.joblib",
    )
    for identifier, predictor_context in predictor_contexts.items():
        review_contexts.setdefault(identifier, {}).update(predictor_context)
    digest = sha256_file(predictions_path)
    provenance = {
        "generation_method": (
            "Deterministic transformation of recorded frozen artifacts; no model "
            "was trained, evaluated, or altered."
        ),
        "source_artifacts": [
            {"path": str(predictions_path.relative_to(root)), "sha256": digest},
            {
                "path": str(all_rows_path.relative_to(root)),
                "sha256": sha256_file(all_rows_path),
            },
            {
                "path": str(metrics_path.relative_to(root)),
                "sha256": sha256_file(metrics_path),
            },
            {
                "path": str(audit_path.relative_to(root)),
                "sha256": sha256_file(audit_path),
            },
        ],
    }
    errors_path = root / "outputs" / "error_analysis" / "model_v8_errors.csv"
    queue_path = root / "outputs" / "manual_review" / "v8_review_queue.csv"
    queue_manifest_path = (
        root / "outputs" / "manual_review" / "v8_review_queue_manifest.json"
    )
    cases_path = root / "outputs" / "case_studies" / "v8_case_studies.json"
    summary_path = (
        root / "outputs" / "evaluations" / "frozen" / "v8_public_summary.json"
    )
    _write_csv(errors_path, ERROR_FIELDS, build_error_rows(rows, base_contexts, digest))
    queue_rows = build_review_queue(rows, review_contexts, digest)
    _write_csv(queue_path, QUEUE_FIELDS, queue_rows)
    queue_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_version": "V8",
                "queue_rows": len(queue_rows),
                "queue_sha256": sha256_file(queue_path),
                "source_predictions_sha256": digest,
                "evidence_sources": {
                    "predictor_index_sha256": PREDICTOR_INDEX_SHA256,
                    "frozen_model_sha256": FROZEN_SOURCE_HASHES[
                        "outputs/ai_temporal_v8/model.joblib"
                    ],
                },
                "selection": {
                    "correct_sample_salt": CORRECT_SAMPLE_SALT,
                    "correct_sample_size_per_group": CORRECT_SAMPLE_SIZE_PER_GROUP,
                    "low_confidence_sample_salt": LOW_CONFIDENCE_SAMPLE_SALT,
                    "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
                    "low_confidence_sample_size": LOW_CONFIDENCE_SAMPLE_SIZE,
                    "correct_sample_ids": [
                        row["variation_id"]
                        for row in queue_rows
                        if row["correct_sample"] == "true"
                    ],
                    "low_confidence_sample_ids": [
                        row["variation_id"]
                        for row in queue_rows
                        if row["low_confidence_sample"] == "true"
                    ],
                    "random_at_build_time": False,
                },
                "priority_rule": (
                    "False negatives first (confidence within group), then false "
                    "positives, disagreements, automatic flags, and seeded controls."
                ),
                "warning": (
                    "Computer suggestions are queue aids, not manual conclusions."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(
        json.dumps(
            build_case_studies(rows, base_contexts, provenance),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            build_public_summary(
                _read_json(metrics_path), _read_json(audit_path), provenance
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    created = [
        errors_path,
        queue_path,
        queue_manifest_path,
        cases_path,
        summary_path,
    ]

    notes_path = root / "outputs" / "manual_review" / "v8_review_notes.json"
    if not notes_path.exists():
        notes_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "store_kind": "v8_manual_review_decisions",
                    "allowed_decisions": list(DECISIONS),
                    "allowed_error_categories": list(ERROR_CATEGORIES),
                    "reviewer_confidence_options": list(REVIEWER_CONFIDENCES),
                    "provenance": {
                        **provenance,
                        "generator": "scripts/build_v8_presentation.py",
                    },
                    "reviews": {},
                    "review_history": {},
                    "warning": "Manual decisions only; this file is never overwritten.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        created.append(notes_path)
    return created


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from a regular file."""
    if not path.is_file() or path.is_symlink():
        raise V8PresentationError(f"V8 presentation file is unavailable: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V8PresentationError(f"Expected a JSON object in {path}")
    return value


def load_summary(path: Path) -> dict[str, Any]:
    """Load and sanity-check the frozen public summary."""
    summary = load_json_object(path)
    matrix = summary.get("confusion_matrix")
    if not isinstance(matrix, dict) or any(
        not isinstance(matrix.get(key), int) for key in ("TN", "FP", "FN", "TP")
    ):
        raise V8PresentationError("V8 summary has an invalid confusion matrix.")
    if matrix["FP"] + matrix["FN"] != summary.get("wrong"):
        raise V8PresentationError("V8 summary wrong count does not match FP + FN.")
    if matrix["TN"] + matrix["TP"] != summary.get("correct"):
        raise V8PresentationError("V8 summary correct count does not match TN + TP.")
    if summary.get("correct", 0) + summary.get("wrong", 0) != summary.get("n"):
        raise V8PresentationError("V8 summary accounting does not equal test size.")
    if sum(matrix.values()) != summary.get("n"):
        raise V8PresentationError("V8 confusion matrix does not equal test size.")
    return summary


def load_case_studies(path: Path) -> dict[str, Any]:
    """Load stable case studies and require all four confusion groups."""
    payload = load_json_object(path)
    cases = payload.get("case_studies")
    if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
        raise V8PresentationError("V8 case studies must be a JSON list of objects.")
    group_counts = {
        group: sum(case.get("confusion_group") == group for case in cases)
        for group in ("TN", "FP", "FN", "TP")
    }
    if group_counts != {"TN": 5, "FP": 5, "FN": 5, "TP": 5}:
        raise V8PresentationError("V8 case studies must include five of each group.")
    return payload


def _read_queue(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise V8PresentationError(f"V8 review queue is unavailable: {path}")
    with path.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    if not rows or any(not row.get("variation_id") for row in rows):
        raise V8PresentationError("V8 review queue is empty or invalid.")
    return rows


def load_review_notes(path: Path) -> dict[str, Any]:
    """Load the separate notes store, or create its in-memory empty shape."""
    if not path.exists():
        return {
            "schema_version": 1,
            "store_kind": "v8_manual_review_decisions",
            "allowed_decisions": list(DECISIONS),
            "reviews": {},
            "review_history": {},
            "warning": "Manual decisions only; predictions are never modified.",
        }
    payload = load_json_object(path)
    if not isinstance(payload.get("reviews"), dict):
        raise V8PresentationError("V8 review notes has an invalid reviews object.")
    return payload


def review_state(review: dict[str, Any] | None) -> str:
    """Return the UI state implied by one saved decision."""
    decision = (review or {}).get("manual_decision") or (review or {}).get("decision")
    if not decision or decision == "not_reviewed":
        return "unreviewed"
    if decision in {
        "ambiguous_condition_scope",
        "ambiguous_aggregation",
        "uncertain_manual_review",
    }:
        return "ambiguous"
    if (review or {}).get("exclude_from_v9_clean_dataset"):
        return "excluded"
    if decision == "needs_expert_review":
        return "needs_expert_review"
    return "reviewed"


def list_review_queue(
    queue_path: Path,
    notes_path: Path,
    *,
    confusion_group: str = "",
    disagreement: bool = False,
    high_confidence: bool = False,
    gene: str = "",
    consequence: str = "",
    match_warning: bool = False,
    status: str = "",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Return the queue in CSV order after applying optional review filters."""
    rows = _read_queue(queue_path)
    queue_ids = {row["variation_id"] for row in rows}
    notes = load_review_notes(notes_path).get("reviews", {})
    assert isinstance(notes, dict)
    normalized_group = confusion_group.upper()
    normalized_gene = gene.strip().casefold()
    normalized_consequence = consequence.strip().casefold()
    normalized_status = status.strip().casefold()
    allowed_statuses = {
        "",
        "unreviewed",
        "reviewed",
        "ambiguous",
        "excluded",
        "needs_expert_review",
    }
    if normalized_group not in {"", "FP", "FN"}:
        raise V8PresentationError("confusion_group must be FP or FN.")
    if normalized_status not in allowed_statuses:
        raise V8PresentationError("Unknown review status filter.")
    if page < 1 or page_size < 1 or page_size > 100:
        raise V8PresentationError("Review pagination is outside the allowed range.")

    filtered: list[dict[str, Any]] = []
    for row in rows:
        identifier = row["variation_id"]
        review = notes.get(identifier, {})
        if not isinstance(review, dict):
            review = {}
        state = review_state(review)
        warning_text = " ".join(
            (row.get("warning_flags", ""), row.get("match_confidence", ""))
        ).strip()
        has_match_warning = bool(warning_text) and warning_text.casefold() not in {
            "not recorded"
        }
        if (
            normalized_group
            and row.get("confusion_group", "").upper() != normalized_group
        ):
            continue
        if disagreement and row.get("v8_v7_disagreement", "").casefold() != "true":
            continue
        if high_confidence and row.get("high_confidence", "").casefold() != "true":
            continue
        if normalized_gene and normalized_gene not in row.get("gene", "").casefold():
            continue
        if (
            normalized_consequence
            and normalized_consequence not in row.get("consequence", "").casefold()
        ):
            continue
        if match_warning and not has_match_warning:
            continue
        if normalized_status and state != normalized_status:
            continue
        filtered.append({**row, "review_state": state, "review": review})

    filtered_total = len(filtered)
    page_count = max(1, (filtered_total + page_size - 1) // page_size)
    if page > page_count:
        page = page_count
    start = (page - 1) * page_size
    reviewed_rows = [
        row
        for row in rows
        if review_state(notes.get(row["variation_id"], {})) != "unreviewed"
    ]
    progress = {
        "total_queued": len(rows),
        "reviewed": len(reviewed_rows),
        "remaining": len(rows) - len(reviewed_rows),
        "false_negatives_reviewed": sum(
            row.get("confusion_group") == "FN" for row in reviewed_rows
        ),
        "false_positives_reviewed": sum(
            row.get("confusion_group") == "FP" for row in reviewed_rows
        ),
        "disagreements_reviewed": sum(
            row.get("v8_v7_disagreement") == "true" for row in reviewed_rows
        ),
        "excluded_from_clean": sum(
            bool(
                notes.get(row["variation_id"], {}).get("exclude_from_v9_clean_dataset")
            )
            for row in rows
        ),
        "included_in_clean": sum(
            bool(notes.get(row["variation_id"], {}).get("include_in_v9_clean_dataset"))
            for row in rows
        ),
        "needs_expert_review": sum(
            notes.get(row["variation_id"], {}).get("manual_decision")
            == "needs_expert_review"
            for row in rows
        ),
    }
    return {
        "rows": filtered[start : start + page_size],
        "total": len(rows),
        "filtered_total": filtered_total,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "completed_review_count": progress["reviewed"],
        "orphaned_review_count": sum(
            identifier not in queue_ids for identifier in notes
        ),
        "allowed_decisions": list(DECISIONS),
        "allowed_error_categories": list(ERROR_CATEGORIES),
        "reviewer_confidence_options": list(REVIEWER_CONFIDENCES),
        "progress": progress,
        "note_max_length": MAX_NOTE_LENGTH,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise V8PresentationError("Refusing to replace an unsafe review notes path.")
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked_review_store(path: Path):
    """Serialize the full review transaction across threads and processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _NOTES_LOCK:
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def update_review_decision(
    queue_path: Path,
    notes_path: Path,
    variation_id: str,
    values: object,
) -> dict[str, Any]:
    """Validate and atomically save one decision without touching predictions."""
    queue_rows = {row["variation_id"]: row for row in _read_queue(queue_path)}
    if variation_id not in queue_rows:
        raise V8PresentationError(
            "Variation ID does not belong to the V8 review queue."
        )
    if not isinstance(values, dict):
        raise V8PresentationError("Review update must be a JSON object.")
    decision = values.get("manual_decision")
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise V8PresentationError(
            "Decision is not one of the allowed V8 review decisions."
        )
    category = values.get("manual_error_category", "unknown")
    if not isinstance(category, str) or category not in ERROR_CATEGORIES:
        raise V8PresentationError("Unknown manual error category.")
    reviewer = values.get("reviewer", "")
    if not isinstance(reviewer, str) or len(reviewer.strip()) > 200:
        raise V8PresentationError("Reviewer must be text limited to 200 characters.")
    reviewer = reviewer.strip()
    reviewer_confidence = values.get("reviewer_confidence", "")
    if reviewer_confidence not in {*REVIEWER_CONFIDENCES, ""}:
        raise V8PresentationError("Unknown reviewer confidence.")
    if decision != "not_reviewed" and (not reviewer or not reviewer_confidence):
        raise V8PresentationError(
            "Reviewer and reviewer confidence are required for a completed review."
        )
    boolean_fields = (
        "exclude_from_v9_clean_dataset",
        "include_in_v9_messy_dataset",
        "include_in_v9_clean_dataset",
    )
    if any(not isinstance(values.get(field), bool) for field in boolean_fields):
        raise V8PresentationError("V9 inclusion and exclusion values must be booleans.")
    exclude_clean = values["exclude_from_v9_clean_dataset"]
    include_messy = values["include_in_v9_messy_dataset"]
    include_clean = values["include_in_v9_clean_dataset"]
    if exclude_clean and include_clean:
        raise V8PresentationError(
            "A review cannot include and exclude the same record from the clean "
            "dataset."
        )
    corrected_outcome = values.get("corrected_outcome", "")
    if corrected_outcome not in {
        "",
        "moved_toward_benign",
        "moved_toward_pathogenic",
    }:
        raise V8PresentationError("Unknown corrected outcome.")
    if decision == "not_reviewed" and corrected_outcome:
        raise V8PresentationError(
            "An unreviewed record cannot carry a corrected outcome."
        )
    note = values.get("note", "")
    if not isinstance(note, str):
        raise V8PresentationError("Review note must be text.")
    cleaned_note = note.strip()
    if len(cleaned_note) > MAX_NOTE_LENGTH:
        raise V8PresentationError(
            f"Review note is limited to {MAX_NOTE_LENGTH} characters."
        )
    if (
        decision in NOTE_REQUIRED or corrected_outcome or exclude_clean
    ) and not cleaned_note:
        raise V8PresentationError("A note is required for this review decision.")

    row = queue_rows[variation_id]

    def decoded(name: str, fallback: object) -> object:
        try:
            return json.loads(row.get(name, ""))
        except json.JSONDecodeError:
            return fallback

    automatic_flags = decoded("automatic_review_flags", [])
    cleared_flags = values.get("cleared_automatic_flags", [])
    if (
        not isinstance(cleared_flags, list)
        or any(not isinstance(flag, str) for flag in cleared_flags)
        or not set(cleared_flags) <= set(automatic_flags)
    ):
        raise V8PresentationError(
            "Cleared automatic flags must be selected from this queue row."
        )
    if cleared_flags and not cleaned_note:
        raise V8PresentationError(
            "A note is required when clearing an automatic review flag."
        )
    expected_revision = values.get("expected_revision")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        raise V8PresentationError("Expected review revision must be an integer.")

    with _locked_review_store(notes_path):
        payload = load_review_notes(notes_path)
        reviews = payload["reviews"]
        assert isinstance(reviews, dict)
        previous = reviews.get(variation_id)
        if previous is not None and not isinstance(previous, dict):
            raise V8PresentationError("Existing review record is invalid.")
        current_revision = int((previous or {}).get("revision", 0))
        if expected_revision != current_revision:
            raise V8PresentationError(
                "Review changed in another session; reload before saving."
            )
        reviewed_at = datetime.now(UTC).isoformat()
        review = {
            "review_id": f"V8:{variation_id}",
            "reviewed_at": reviewed_at,
            "reviewer": reviewer,
            "model_version": "V8",
            "variation_id": variation_id,
            "vcv_accession": row.get("vcv_accession", "not recorded"),
            "allele_id": row.get("allele_id", "not recorded"),
            "gene": row.get("gene", "not recorded"),
            "old_snapshot_date": row.get("old_snapshot_date", "not recorded"),
            "new_snapshot_date": row.get("new_snapshot_date", "not recorded"),
            "old_classification_text": row.get(
                "old_classification_text", "not recorded"
            ),
            "new_classification_text": row.get(
                "new_classification_text", "not recorded"
            ),
            "normalized_old_outcome": row.get("normalized_old_outcome", "uncertain"),
            "normalized_new_outcome": row.get("normalized_new_outcome", "not recorded"),
            "v8_prediction": row.get("predicted_class", "not recorded"),
            "v8_probability": float(row.get("v8_probability", "0")),
            "v8_confidence": float(row.get("confidence", "0")),
            "v8_correctness": row.get("correct", "false") == "true",
            "v7_prediction": row.get("v7_prediction", "not recorded"),
            "match_method": row.get("match_method", "not recorded"),
            "match_confidence": row.get("match_confidence", "not recorded"),
            "old_condition_text": row.get("old_condition_text", "not recorded"),
            "new_condition_text": row.get("new_condition_text", "not recorded"),
            "old_review_status": row.get("old_review_status", "not recorded"),
            "new_review_status": row.get("new_review_status", "not recorded"),
            "old_consequence_fields": decoded("old_consequence_fields", {}),
            "feature_values_used_by_v8": decoded("feature_values_used_by_v8", {}),
            "official_source_links": decoded("official_source_links", []),
            "automatic_warning_flags": automatic_flags,
            "cleared_automatic_flags": sorted(set(cleared_flags)),
            "manual_decision": decision,
            "manual_error_category": category,
            "exclude_from_v9_clean_dataset": exclude_clean,
            "include_in_v9_messy_dataset": include_messy,
            "include_in_v9_clean_dataset": include_clean,
            "label_correction": bool(corrected_outcome),
            "corrected_outcome": corrected_outcome or None,
            "note": cleaned_note,
            "reviewer_confidence": reviewer_confidence or None,
            "revision": current_revision + 1,
            "updated_at_utc": reviewed_at,
        }
        history = payload.setdefault("review_history", {})
        if not isinstance(history, dict):
            raise V8PresentationError("Existing review history is invalid.")
        if previous:
            previous_versions = history.setdefault(variation_id, [])
            if not isinstance(previous_versions, list):
                raise V8PresentationError("Existing review history entry is invalid.")
            previous_versions.append({**previous, "superseded_at_utc": reviewed_at})
        reviews[variation_id] = review
        payload["allowed_decisions"] = list(DECISIONS)
        payload["allowed_error_categories"] = list(ERROR_CATEGORIES)
        payload["reviewer_confidence_options"] = list(REVIEWER_CONFIDENCES)
        payload["warning"] = "Manual decisions only; predictions are never modified."
        _atomic_write_json(notes_path, payload)
    return {**review, "review_state": review_state(review)}
