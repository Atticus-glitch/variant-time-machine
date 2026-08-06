"""Tests for the public V8 result and separate manual-review presentation."""

import hashlib
import json
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from website.dashboard.app import create_app

ROOT = Path(__file__).parents[1]


def _review_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "reviewer": "test-reviewer",
        "manual_decision": "match_correct_model_wrong",
        "manual_error_category": "genuine_model_error",
        "exclude_from_v9_clean_dataset": False,
        "include_in_v9_messy_dataset": True,
        "include_in_v9_clean_dataset": True,
        "corrected_outcome": "",
        "cleared_automatic_flags": [],
        "reviewer_confidence": "high",
        "note": "Checked source record.",
        "expected_revision": 0,
    }
    payload.update(updates)
    return payload


@pytest.fixture
def v8_app(tmp_path: Path) -> Flask:
    notes = tmp_path / "v8_review_notes.json"
    notes.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "store_kind": "v8_manual_review_decisions",
                "reviews": {},
            }
        ),
        encoding="utf-8",
    )
    return create_app(
        {
            "TESTING": True,
            "V8_REVIEW_NOTES_PATH": notes,
        }
    )


@pytest.fixture
def v8_client(v8_app: Flask) -> FlaskClient:
    return v8_app.test_client()


def test_v8_pages_load_with_exact_claim_boundaries(v8_client: FlaskClient) -> None:
    results = v8_client.get("/v8_results.html")
    assert results.status_code == 200
    page = results.get_data(as_text=True)
    assert "V8 Result Summary" in page
    assert (
        "V8 is the strongest current retrospective model, but not clinical validation."
        in page
    )
    assert "Accuracy</dt><dd>89.5%" in page
    assert "Balanced accuracy</dt><dd>87.1%" in page
    assert "TN 740" in page
    assert "FP 74" in page
    assert "FN 31" in page
    assert "TP 155" in page
    assert "The interval crosses zero" in page
    assert "Strongest truthful claim right now" in page
    assert "outcome-selected" in page
    assert "559 predictor-time gene components" in page
    assert "membership is reconstructible" in page
    assert "Not medical advice. Not clinical validation." in page
    assert "not for clinical use or patient interpretation" in page.casefold()
    assert "supports clinical use" not in page.casefold()

    review = v8_client.get("/v8_review.html")
    assert review.status_code == 200
    review_page = review.get_data(as_text=True)
    assert "V8 Manual Review" in review_page
    for label in (
        "FP",
        "FN",
        "V8/V7 disagreement",
        "High-confidence wrong",
        "Gene",
        "Consequence",
        "Automatic warning",
        "Unreviewed",
        "Reviewed",
        "Ambiguous",
        "Excluded",
    ):
        assert label in review_page
    assert "Computer suggestions are not manual conclusions" in review_page
    assert "v8-review-previous" in review_page


def test_v8_summary_and_case_studies_are_internally_consistent(
    v8_client: FlaskClient,
) -> None:
    summary = v8_client.get("/api/v8/summary").get_json()
    assert summary["n"] == 1000
    assert summary["accuracy"] == pytest.approx(0.895)
    assert summary["balanced_accuracy"] == pytest.approx(0.8712121212)
    assert summary["confusion_matrix"] == {"TN": 740, "FP": 74, "FN": 31, "TP": 155}
    assert summary["confusion_matrix"]["FP"] + summary["confusion_matrix"]["FN"] == 105
    assert summary["v7_same_record"]["interval_crosses_zero"] is True
    assert summary["v7_same_record"]["claim"] == (
        "No V8 performance improvement over V7 is claimed."
    )
    assert summary["strongest_claim"].startswith(
        "In a retrospective historical ClinVar experiment"
    )
    assert "no statistically clear overall superiority" in summary["strongest_claim"]

    cases = v8_client.get("/api/v8/case-studies").get_json()["case_studies"]
    assert len(cases) == 20
    assert {case["confusion_group"] for case in cases} == {"TN", "FP", "FN", "TP"}
    assert all(
        sum(case["confusion_group"] == group for case in cases) == 5
        for group in ("TN", "FP", "FN", "TP")
    )
    ai_review = v8_client.get("/api/v8/ai-review-suggestions")
    assert ai_review.status_code == 200
    assert ai_review.get_json()["suggested_decisions"] == {
        "ambiguous_condition_scope": 8,
        "match_correct_model_wrong": 96,
        "needs_expert_review": 1,
    }


def test_v8_queue_order_filters_and_separate_atomic_persistence(
    v8_app: Flask,
    v8_client: FlaskClient,
) -> None:
    queue = v8_client.get("/api/v8/review-queue").get_json()
    assert queue["total"] == 1000
    assert queue["page"] == 1
    assert queue["page_size"] == 25
    assert queue["page_count"] == 40
    assert [int(row["queue_order"]) for row in queue["rows"]] == list(range(1, 26))
    first = queue["rows"][0]
    assert first["confusion_group"] == "FN"
    assert v8_client.get("/api/v8/review-queue?confusion_group=FP").get_json()["rows"]
    disagreements = v8_client.get("/api/v8/review-queue?disagreement=true").get_json()[
        "rows"
    ]
    assert all(row["v8_v7_disagreement"] == "true" for row in disagreements)
    high_confidence = v8_client.get(
        "/api/v8/review-queue?high_confidence=true"
    ).get_json()
    assert high_confidence["filtered_total"] == 19
    assert all(row["high_confidence"] == "true" for row in high_confidence["rows"])

    predictions = ROOT / "outputs" / "ai_temporal_v8" / "temporal_test_predictions.csv"
    before = hashlib.sha256(predictions.read_bytes()).hexdigest()
    saved = v8_client.patch(
        f"/api/v8/review/{first['variation_id']}",
        json=_review_payload(),
    )
    assert saved.status_code == 200
    assert hashlib.sha256(predictions.read_bytes()).hexdigest() == before
    notes_path = Path(v8_app.config["V8_REVIEW_NOTES_PATH"])
    stored = json.loads(notes_path.read_text(encoding="utf-8"))
    assert stored["reviews"][first["variation_id"]]["manual_decision"] == (
        "match_correct_model_wrong"
    )
    assert stored["reviews"][first["variation_id"]]["normalized_new_outcome"]
    assert stored["reviews"][first["variation_id"]]["feature_values_used_by_v8"]
    assert stored["reviews"][first["variation_id"]]["revision"] == 1
    stale = v8_client.patch(
        f"/api/v8/review/{first['variation_id']}", json=_review_payload()
    )
    assert stale.status_code == 400
    assert "another session" in stale.get_json()["error"]
    updated = v8_client.patch(
        f"/api/v8/review/{first['variation_id']}",
        json=_review_payload(expected_revision=1, note="Second verified review."),
    )
    assert updated.status_code == 200
    stored = json.loads(notes_path.read_text(encoding="utf-8"))
    assert stored["reviews"][first["variation_id"]]["revision"] == 2
    assert len(stored["review_history"][first["variation_id"]]) == 1
    reviewed = v8_client.get("/api/v8/review-queue?status=reviewed").get_json()
    assert reviewed["filtered_total"] == 1


def test_v8_review_validation_rejects_unsafe_updates(v8_client: FlaskClient) -> None:
    first_row = v8_client.get("/api/v8/review-queue").get_json()["rows"][0]
    identifier = first_row["variation_id"]
    assert (
        v8_client.patch(
            "/api/v8/review/999999999999",
            json=_review_payload(),
        ).status_code
        == 400
    )
    first_flag = json.loads(first_row["automatic_review_flags"])[0]
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(note="", cleared_automatic_flags=[first_flag]),
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(
                manual_decision="not_reviewed",
                reviewer="",
                reviewer_confidence="",
                corrected_outcome="moved_toward_benign",
            ),
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(
                note="",
                include_in_v9_clean_dataset=False,
                exclude_from_v9_clean_dataset=True,
            ),
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(note="", corrected_outcome="moved_toward_benign"),
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(manual_decision="invented"),
        ).status_code
        == 400
    )
    for decision in ("bad_match", "possible_label_problem", "needs_expert_review"):
        response = v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(manual_decision=decision, note=""),
        )
        assert response.status_code == 400
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(note="x" * 5001),
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json=_review_payload(
                include_in_v9_clean_dataset=True,
                exclude_from_v9_clean_dataset=True,
            ),
        ).status_code
        == 400
    )


def test_v8_download_whitelist_and_model_rendering_sanity(
    v8_client: FlaskClient,
) -> None:
    downloads = (
        "v8_public_summary.json",
        "temporal_test_predictions.csv",
        "wrong_predictions.csv",
        "v8_case_studies.json",
        "error_analysis.csv",
        "v8_review_queue.csv",
        "v8_review_queue_manifest.json",
        "v8_ai_review_suggestions.json",
        "v8-ai-assisted-review.md",
        "one-page-abstract.md",
        "v8_poster_outline.md",
        "strongest_truthful_claim.txt",
        "poster-outline.md",
        "strongest-truthful-claim.md",
        "v8_metrics.json",
        "v8_protocol_audit.json",
        "v8_model_commitment.json",
        "v8_vault_commitment.json",
        "v8-case-studies.md",
        "v8-error-analysis.md",
        "ai-temporal-v8-preregistration.md",
        "ai-temporal-v8-results.md",
    )
    for filename in downloads:
        response = v8_client.get(f"/api/v8/download/{filename}")
        assert response.status_code == 200, filename
        assert response.data
    assert v8_client.get("/api/v8/download/not-allowed.csv").status_code == 404

    script = v8_client.get("/static/model_versions.js").get_data(as_text=True)
    assert "function presentationSanityCheck" in script
    assert "evidenceRows(evidence, payload.ranking.evidence_summary)" in script
    assert "Object.values(payload.ranking.evidence_summary).join" not in script
    for route in ("/", "/model_versions.html", "/v8_results.html", "/v8_review.html"):
        page = v8_client.get(route).get_data(as_text=True)
        assert "[object Object]" not in page
        assert ">undefined<" not in page
        assert ">NaN<" not in page


def test_generic_explorer_cannot_create_a_second_v8_review_store(
    v8_client: FlaskClient,
) -> None:
    identifier = v8_client.get("/api/v8/review-queue").get_json()["rows"][0][
        "variation_id"
    ]
    response = v8_client.patch(
        f"/api/prediction-explorer/V8/{identifier}/review",
        json={"status": "reviewed", "category": "unknown", "notes": "wrong store"},
    )
    assert response.status_code == 400
    assert "focused Manual Review Queue" in response.get_json()["error"]


def test_v9_preparation_pages_and_manifest_are_explicitly_not_final(
    v8_client: FlaskClient,
) -> None:
    for route in (
        "/v9_dataset.html",
        "/v9_training.html",
        "/v9_results.html",
        "/v9_explorer.html",
    ):
        response = v8_client.get(route)
        assert response.status_code == 200
        assert "V9" in response.get_data(as_text=True)
    manifest = v8_client.get("/api/v9/dataset-summary")
    assert manifest.status_code == 200
    payload = manifest.get_json()
    assert payload["number_included_messy"] == 1000
    assert payload["number_included_clean"] == 0
    assert payload["training_eligible"] is False
    assert payload["final_test_allowed"] is False
    assert payload["artifacts_stale"] is True
    assert "review store changed after dataset build" in payload["stale_reasons"]
    assert v8_client.get("/api/v9/download/v9_dataset_manifest.json").status_code == 200
    assert v8_client.get("/api/v9/download/v9_messy_dataset.csv").status_code == 409
    assert v8_client.get("/api/v9/download/not-allowed.csv").status_code == 404
