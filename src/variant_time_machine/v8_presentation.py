"""Read-only V8 presentation data and separate manual-review persistence."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DECISIONS: tuple[str, ...] = (
    "match correct",
    "match ambiguous",
    "classification-scope problem",
    "model genuinely wrong",
    "exclude from final analysis",
)
NOTE_REQUIRED = {
    "match ambiguous",
    "classification-scope problem",
    "exclude from final analysis",
}
MAX_NOTE_LENGTH = 5000
CASE_STUDY_SALT = "v8-case-studies-2026-08-02"
CORRECT_SAMPLE_SALT = "v8-review-correct-sample-2026-08-02"
CORRECT_SAMPLE_SIZE = 20
HIGH_CONFIDENCE_THRESHOLD = 0.8
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
    "reasons",
    "model_version",
    "variation_id",
    "vcv_accession",
    "gene",
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
    "old_classification",
    "actual_later_classification",
    "review_status",
    "manual_review_status",
    "consequence",
    "key_features",
    "match_confidence",
    "warning_flags",
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


def build_review_queue(
    rows: list[dict[str, str]],
    contexts: dict[str, dict[str, str]],
    predictions_sha256: str,
) -> list[dict[str, str]]:
    """Build the deterministic union of errors, disagreements, and correct samples."""
    candidates: list[tuple[int, float, int, dict[str, str]]] = []
    correct_pool: list[dict[str, str]] = []
    for row in rows:
        actual, predicted, probability, confidence, correct, group = _row_values(row)
        v7 = _direction(row.get("v7_prediction", ""))
        disagreement = bool(row.get("v7_prediction")) and v7 != predicted
        if correct:
            correct_pool.append(row)
            if not disagreement:
                continue
        if not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD:
            bucket = 0
        elif not correct and group == "FN":
            bucket = 1
        elif not correct:
            bucket = 2
        else:
            bucket = 3
        candidates.append((bucket, -confidence, int(row["variation_id"]), row))
    selected_ids = {item[3]["variation_id"] for item in candidates}
    correct_pool.sort(
        key=lambda row: hashlib.sha256(
            f"{CORRECT_SAMPLE_SALT}:{row['variation_id']}".encode()
        ).hexdigest()
    )
    correct_sample = correct_pool[:CORRECT_SAMPLE_SIZE]
    correct_sample_ids = {row["variation_id"] for row in correct_sample}
    for row in correct_sample:
        if row["variation_id"] not in selected_ids:
            candidates.append((4, 0.0, int(row["variation_id"]), row))
    candidates.sort(key=lambda item: item[:3])

    queue: list[dict[str, str]] = []
    for order, (bucket, _, _, row) in enumerate(candidates, start=1):
        actual, predicted, probability, confidence, correct, group = _row_values(row)
        context = _context(contexts, row["variation_id"])
        consequence = row.get("consequence") or context.get(
            "consequence", "not recorded"
        )
        v7 = _direction(row.get("v7_prediction", ""))
        disagreement = bool(row.get("v7_prediction")) and v7 != predicted
        reasons = []
        if not correct and confidence >= HIGH_CONFIDENCE_THRESHOLD:
            reasons.append("high-confidence wrong")
        if not correct:
            reasons.append("false negative" if group == "FN" else "false positive")
        if disagreement:
            reasons.append("V8/V7 disagreement")
        if row["variation_id"] in correct_sample_ids:
            reasons.append("stable correct sample")
        queue.append(
            {
                "queue_order": str(order),
                "priority": (
                    "high" if bucket <= 1 else "medium" if bucket <= 3 else "low"
                ),
                "reasons": "; ".join(reasons),
                "model_version": "V8",
                "variation_id": row["variation_id"],
                "vcv_accession": context.get("vcv_accession", "not recorded"),
                "gene": row.get("gene_symbols", row.get("gene", "not recorded")),
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
        contexts = {
            row["variation_id"]: row
            for row in csv.DictReader(input_file)
            if row.get("variation_id")
        }
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
    cases_path = root / "outputs" / "case_studies" / "v8_case_studies.json"
    summary_path = (
        root / "outputs" / "evaluations" / "frozen" / "v8_public_summary.json"
    )
    _write_csv(errors_path, ERROR_FIELDS, build_error_rows(rows, contexts, digest))
    _write_csv(queue_path, QUEUE_FIELDS, build_review_queue(rows, contexts, digest))
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(
        json.dumps(
            build_case_studies(rows, contexts, provenance), indent=2, sort_keys=True
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
    created = [errors_path, queue_path, cases_path, summary_path]

    notes_path = root / "outputs" / "manual_review" / "v8_review_notes.json"
    if not notes_path.exists():
        notes_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "store_kind": "v8_manual_review_decisions",
                    "allowed_decisions": list(DECISIONS),
                    "provenance": {
                        **provenance,
                        "generator": "scripts/build_v8_presentation.py",
                    },
                    "reviews": {},
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
            "warning": "Manual decisions only; predictions are never modified.",
        }
    payload = load_json_object(path)
    if not isinstance(payload.get("reviews"), dict):
        raise V8PresentationError("V8 review notes has an invalid reviews object.")
    return payload


def review_state(review: dict[str, Any] | None) -> str:
    """Return the UI state implied by one saved decision."""
    decision = (review or {}).get("decision")
    if not decision:
        return "unreviewed"
    if decision == "match ambiguous":
        return "ambiguous"
    if decision == "exclude from final analysis":
        return "excluded"
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
    allowed_statuses = {"", "unreviewed", "reviewed", "ambiguous", "excluded"}
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
    return {
        "rows": filtered[start : start + page_size],
        "total": len(rows),
        "filtered_total": filtered_total,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "completed_review_count": sum(
            review_state(value if isinstance(value, dict) else {}) != "unreviewed"
            for identifier, value in notes.items()
            if identifier in queue_ids
        ),
        "orphaned_review_count": sum(
            identifier not in queue_ids for identifier in notes
        ),
        "allowed_decisions": list(DECISIONS),
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


def update_review_decision(
    queue_path: Path,
    notes_path: Path,
    variation_id: str,
    decision: object,
    note: object,
) -> dict[str, Any]:
    """Validate and atomically save one decision without touching predictions."""
    identifiers = {row["variation_id"] for row in _read_queue(queue_path)}
    if variation_id not in identifiers:
        raise V8PresentationError(
            "Variation ID does not belong to the V8 review queue."
        )
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise V8PresentationError(
            "Decision is not one of the allowed V8 review decisions."
        )
    if not isinstance(note, str):
        raise V8PresentationError("Review note must be text.")
    cleaned_note = note.strip()
    if len(cleaned_note) > MAX_NOTE_LENGTH:
        raise V8PresentationError(
            f"Review note is limited to {MAX_NOTE_LENGTH} characters."
        )
    if decision in NOTE_REQUIRED and not cleaned_note:
        raise V8PresentationError("A note is required for this review decision.")

    with _NOTES_LOCK:
        payload = load_review_notes(notes_path)
        reviews = payload["reviews"]
        assert isinstance(reviews, dict)
        review = {
            "decision": decision,
            "note": cleaned_note,
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
        reviews[variation_id] = review
        payload["allowed_decisions"] = list(DECISIONS)
        payload["warning"] = "Manual decisions only; predictions are never modified."
        _atomic_write_json(notes_path, payload)
    return {**review, "review_state": review_state(review)}
