"""Tests for separate AI-assisted V8 review suggestions."""

import json
from collections import Counter
from pathlib import Path

from variant_time_machine.v8_ai_review import (
    ANSWER_ARCHIVE_SHA256,
    QUEUE_SHA256,
    _recommendation,
)

ROOT = Path(__file__).resolve().parents[1]


def _row() -> dict[str, str]:
    return {
        "variation_id": "1",
        "gene": "GENE1",
        "confusion_group": "FN",
        "predicted_class": "moved_toward_benign",
        "normalized_new_outcome": "moved_toward_pathogenic",
        "confidence": "0.9",
        "allele_id": "10",
        "rcv_accessions": "RCV000000001",
        "old_condition_text": "Named condition",
        "old_review_status": "criteria provided, single submitter",
    }


def _answer() -> dict[str, set[str]]:
    return {
        "allele_ids": {"10"},
        "classifications": {"Pathogenic"},
        "origins": {"germline"},
        "rcv_accessions": {"RCV000000001"},
        "conditions": {"Named condition"},
        "review_statuses": {"criteria provided, single submitter"},
        "submitter_counts": {"1"},
    }


def test_recommendation_separates_genuine_scope_and_expert_cases() -> None:
    genuine = _recommendation(_row(), _answer())
    assert genuine["suggested_manual_decision"] == "match_correct_model_wrong"
    assert genuine["suggested_error_category"] == (
        "false_negative_pathogenic_direction"
    )

    ambiguous_answer = _answer()
    ambiguous_answer["rcv_accessions"] = {"RCV000000001|RCV000000002"}
    ambiguous_answer["conditions"] = {"Different named condition"}
    ambiguous_row = {**_row(), "old_condition_text": "not specified"}
    ambiguous = _recommendation(ambiguous_row, ambiguous_answer)
    assert ambiguous["suggested_manual_decision"] == "ambiguous_condition_scope"

    ambiguous_answer["review_statuses"] = {"no assertion criteria provided"}
    expert = _recommendation(ambiguous_row, ambiguous_answer)
    assert expert["suggested_manual_decision"] == "needs_expert_review"


def test_generated_ai_review_covers_every_v8_error_without_touching_manual_notes() -> (
    None
):
    payload = json.loads(
        (ROOT / "outputs/manual_review/v8_ai_review_suggestions.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["records_reviewed"] == 105
    assert payload["confusion_groups"] == {"FN": 31, "FP": 74}
    assert payload["source_hashes"] == {
        "answer_archive": ANSWER_ARCHIVE_SHA256,
        "review_queue": QUEUE_SHA256,
    }
    assert Counter(
        review["suggested_manual_decision"] for review in payload["reviews"]
    ) == {
        "match_correct_model_wrong": 96,
        "ambiguous_condition_scope": 8,
        "needs_expert_review": 1,
    }
    assert all(review["requires_human_confirmation"] for review in payload["reviews"])
    notes = json.loads(
        (ROOT / "outputs/manual_review/v8_review_notes.json").read_text(
            encoding="utf-8"
        )
    )
    assert notes["reviews"] == {}
