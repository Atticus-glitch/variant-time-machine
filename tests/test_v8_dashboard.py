"""Tests for the public V8 result and separate manual-review presentation."""

import hashlib
import json
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from website.dashboard.app import create_app

ROOT = Path(__file__).parents[1]


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
    assert "Manual Review Queue" in review_page
    for label in (
        "FP",
        "FN",
        "V8/V7 disagreement",
        "High confidence",
        "Gene",
        "Consequence",
        "Match warning",
        "Unreviewed",
        "Reviewed",
        "Ambiguous",
        "Excluded",
    ):
        assert label in review_page
    assert "Probability assigned to predicted direction" in review_page
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


def test_v8_queue_order_filters_and_separate_atomic_persistence(
    v8_app: Flask,
    v8_client: FlaskClient,
) -> None:
    queue = v8_client.get("/api/v8/review-queue").get_json()
    assert queue["total"] == 198
    assert queue["page"] == 1
    assert queue["page_size"] == 25
    assert queue["page_count"] == 8
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
        json={"decision": "model genuinely wrong", "note": "Checked source record."},
    )
    assert saved.status_code == 200
    assert hashlib.sha256(predictions.read_bytes()).hexdigest() == before
    notes_path = Path(v8_app.config["V8_REVIEW_NOTES_PATH"])
    stored = json.loads(notes_path.read_text(encoding="utf-8"))
    assert stored["reviews"][first["variation_id"]]["decision"] == (
        "model genuinely wrong"
    )
    reviewed = v8_client.get("/api/v8/review-queue?status=reviewed").get_json()
    assert reviewed["filtered_total"] == 1


def test_v8_review_validation_rejects_unsafe_updates(v8_client: FlaskClient) -> None:
    identifier = v8_client.get("/api/v8/review-queue").get_json()["rows"][0][
        "variation_id"
    ]
    assert (
        v8_client.patch(
            "/api/v8/review/999999999999",
            json={"decision": "match correct", "note": ""},
        ).status_code
        == 400
    )
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json={"decision": "invented", "note": ""},
        ).status_code
        == 400
    )
    for decision in (
        "match ambiguous",
        "classification-scope problem",
        "exclude from final analysis",
    ):
        response = v8_client.patch(
            f"/api/v8/review/{identifier}", json={"decision": decision, "note": ""}
        )
        assert response.status_code == 400
    assert (
        v8_client.patch(
            f"/api/v8/review/{identifier}",
            json={"decision": "match correct", "note": "x" * 5001},
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
