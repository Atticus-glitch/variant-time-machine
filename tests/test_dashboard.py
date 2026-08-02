"""Tests for the local Flask research dashboard."""

from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from variant_time_machine.clinvar_api import (
    ClinVarConnectionError,
    ClinVarVariant,
)
from variant_time_machine.pilot_workspace import empty_workspace, save_workspace
from website.dashboard.app import SYNTHETIC_NOTICE, create_app


@pytest.fixture
def dashboard_app(tmp_path: Path) -> Flask:
    """Create a dashboard configured for Flask testing."""
    workspace = tmp_path / "pilot_workspace.json"
    save_workspace(workspace, empty_workspace())
    return create_app(
        {
            "TESTING": True,
            "PILOT_WORKSPACE_PATH": workspace,
            "VCV_HISTORY_ROOT": tmp_path / "vcv_history",
            "CLUE_SCORE_RESULTS_DB_PATH": tmp_path / "missing_clue_score.sqlite3",
            "HISTORICAL_VARIANT_DB_PATH": tmp_path / "missing_history.sqlite3",
            "AI_HOLDOUT_V4_RESULTS_DIR": tmp_path / "missing_ai_v4",
            "AI_HOLDOUT_V4_SOURCE_DB_PATH": tmp_path / "missing_v2.sqlite3",
            "AI_HOLDOUT_V5_RESULTS_DIR": tmp_path / "missing_ai_v5",
            "AI_HOLDOUT_V5_SOURCE_DB_PATH": tmp_path / "missing_v2.sqlite3",
        }
    )


@pytest.fixture
def client(dashboard_app: Flask) -> FlaskClient:
    """Return the Flask test client."""
    return dashboard_app.test_client()


def test_dashboard_homepage_and_assets_load(client: FlaskClient) -> None:
    """The dashboard shell and its local assets should be available."""
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Variant Time Machine" in page
    assert "What Is This Project?" in page
    assert "Project Progress" in page
    assert "Live ClinVar Connection" in page
    assert "Fake Example Dataset" in page
    assert "What Each Folder Does" in page
    assert "Next Three Tasks" in page
    assert "Computer Status" in page
    assert "Data Transfer Safety" in page
    assert "Current Pilot Variant" in page
    assert "Latest Research Note" in page
    assert SYNTHETIC_NOTICE in page

    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/lookup.js").status_code == 200
    assert client.get("/static/workspace.js").status_code == 200
    assert client.get("/static/version_history.js").status_code == 200
    assert client.get("/static/pilot_results.js").status_code == 200
    assert client.get("/static/prediction_results.js").status_code == 200
    assert client.get("/static/overview.js").status_code == 200
    assert client.get("/static/model_versions.js").status_code == 200
    assert client.get("/static/prediction_explorer.js").status_code == 200
    assert client.get("/static/research_timeline.js").status_code == 200
    lookup_page = client.get("/variant_lookup.html")
    assert lookup_page.status_code == 200
    assert "ClinVar Variant Lookup" in lookup_page.get_data(as_text=True)
    pilot_page = client.get("/historical_pilot.html")
    assert pilot_page.status_code == 200
    assert "Pilot Workspace" in pilot_page.get_data(as_text=True)
    assert client.get("/pilot_workspace.html").status_code == 200
    assert client.get("/pilot_results.html").status_code == 200
    assert client.get("/prediction_results.html").status_code == 200
    assert client.get("/overview.html").status_code == 200
    assert client.get("/model_versions.html").status_code == 200
    assert client.get("/prediction_explorer.html").status_code == 200
    assert client.get("/research_timeline.html").status_code == 200


def test_ai_v4_endpoint_stays_separate_and_requires_test_approval(
    client: FlaskClient,
) -> None:
    page = client.get("/prediction_results.html").get_data(as_text=True)
    assert "AI Holdout V4" in page
    assert "Test AI On 100 Unseen Records" in page
    assert "Test V5 On 100 Fresh Records" in page
    summary = client.get("/api/ai-v4/summary")
    assert summary.status_code == 200
    assert summary.get_json() == {"available": False, "state": "not_trained"}
    unapproved = client.post("/api/ai-v4/test", json={})
    assert unapproved.status_code == 428
    assert client.get("/api/ai-v5/summary").get_json() == {
        "available": False,
        "state": "not_trained",
    }
    assert client.post("/api/ai-v5/test", json={}).status_code == 428


def test_version_history_explorer_page_has_safety_copy_and_navigation(
    client: FlaskClient,
) -> None:
    """The dedicated explorer should expose its workflow and scientific limits."""
    dashboard_dir = Path(__file__).parents[1] / "website" / "dashboard"
    page = (dashboard_dir / "version_history.html").read_text(encoding="utf-8")

    assert "Version History Explorer" in page
    assert "/static/version_history.js" in page
    assert "Explore Version History" in page
    assert "Saved Histories" in page
    assert "Save as Pilot Case" in page
    assert "Mark Manually Verified" in page
    assert (
        "A VCV version changes when content in the aggregated variant record changes. "
        "A new version does not necessarily mean the medical classification changed."
        in page
    )
    assert (
        "This pilot version history is not the same thing as comparing complete "
        "monthly ClinVar release snapshots." in page
    )

    home = client.get("/").get_data(as_text=True)
    pilot = client.get("/pilot_workspace.html").get_data(as_text=True)
    explorer = client.get("/version_history.html")
    assert explorer.status_code == 200
    assert "Version History Explorer" in explorer.get_data(as_text=True)
    assert '<a href="/version_history.html">Version History Explorer</a>' in home
    assert '<a href="/version_history.html">Version History Explorer</a>' in pilot


def test_progress_endpoint_reports_all_stages_honestly(client: FlaskClient) -> None:
    """Progress should use only the declared status values and include every stage."""
    response = client.get("/api/progress")
    assert response.status_code == 200
    items = response.get_json()["items"]
    assert [item["name"] for item in items] == [
        "Project setup",
        "Load genetic data",
        "Clean and organize variants",
        "Compare historical records",
        "Timeline dataset",
        "Features",
        "Models",
    ]
    assert {item["status"] for item in items}.issubset(
        {"Not Started", "Working", "Complete"}
    )
    statuses = {item["name"]: item["status"] for item in items}
    assert statuses["Project setup"] == "Complete"
    assert statuses["Features"] == "Complete"
    assert statuses["Models"] == "Working"
    assert [item["step"] for item in items] == list(range(1, 8))


def test_dataset_endpoint_uses_labeled_synthetic_pipeline_data(
    client: FlaskClient,
) -> None:
    """The preview should expose calculated synthetic rows with expected fields."""
    response = client.get("/api/dataset")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["notice"] == SYNTHETIC_NOTICE
    assert payload["source"] == "data/example_variants.csv"
    assert len(payload["rows"]) == 4
    assert set(payload["rows"][0]) == {
        "variant_id",
        "gene",
        "old_classification",
        "new_classification",
        "result",
    }
    assert payload["rows"][0] == {
        "variant_id": "Variant001",
        "gene": "CFTR",
        "old_classification": "VUS",
        "new_classification": "Pathogenic",
        "result": "Became more concerning",
    }


def test_status_endpoint_reports_system_and_latest_notes(client: FlaskClient) -> None:
    """Status should include the milestone, system fields, and latest notebook entry."""
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["project_name"] == "Variant Time Machine"
    assert payload["current_milestone"] == "Model Validation and Error Analysis"
    assert "uncertain genetic variant" in payload["project_explanation"]
    assert len(payload["folders"]) == 8
    assert len(payload["next_tasks"]) == 3
    assert {
        "python_environment",
        "python_executable",
        "recommended_python",
        "python_migration",
        "database",
        "tests",
        "last_pipeline_run",
        "files_created",
        "raw_clinvar_files",
        "pilot_strategy",
        "archive_scan",
        "pilot_outputs",
        "storage",
    }.issubset(payload["system"])
    assert "data/example_variants.csv" in payload["system"]["files_created"]
    assert payload["research_notes"]["title"] == (
        "2026-08-02 V8 Component-Disjoint Retrospective Test"
    )
    assert "87.1212%" in payload["research_notes"]["content"]
    assert payload["clinvar_connection"]["connection_status"] == "Not connected"
    assert payload["historical_comparison"] == {
        "total_verified_variants": 0,
        "variants_with_classification_changes": 0,
        "last_verified_comparison": "None yet",
    }
    assert payload["transfer_safety"]["large_download_protection"] == "ON"
    assert payload["transfer_safety"]["current_transfer"] == "0 bytes; idle"
    assert "10 MB" in payload["transfer_safety"]["largest_planned_download"]
    assert payload["current_pilot_variant"] == {
        "selected": False,
        "variant": "No pilot variant selected",
        "gene": "No pilot variant selected",
        "current_classification": "No pilot variant selected",
        "historical_status": "No historical information investigated",
        "verification_status": "No pilot variant selected",
        "timeline": [],
    }
    assert payload["clue_score_baseline"]["available"] is False
    assert payload["clue_score_baseline"]["formula_version"] == (
        "Resolved Direction V2"
    )
    assert payload["model_validation"]["latest_model_version"] == "V8"
    assert payload["model_validation"]["v8"]["balanced_accuracy"] == pytest.approx(
        0.871212
    )
    assert any(
        "component-bootstrap interval includes zero" in warning
        for warning in payload["model_validation"]["warnings"]
    )


def test_model_registry_explorer_and_timeline_apis(
    tmp_path: Path,
) -> None:
    timeline = tmp_path / "timeline.json"
    source_timeline = Path(__file__).parents[1] / "outputs" / "project_timeline.json"
    timeline.write_text(source_timeline.read_text(encoding="utf-8"), encoding="utf-8")
    reviews = tmp_path / "model_error_reviews.json"
    app = create_app(
        {
            "TESTING": True,
            "MODEL_ERROR_REVIEW_PATH": reviews,
            "PROJECT_TIMELINE_PATH": timeline,
        }
    )
    local_client = app.test_client()

    models = local_client.get("/api/model-versions")
    assert models.status_code == 200
    assert models.get_json()["latest_model_version"] == "V8"
    assert local_client.get("/api/model-versions/V8").status_code == 200
    assert local_client.get("/api/model-versions/V4").status_code == 200

    explorer = local_client.get("/api/prediction-explorer").get_json()
    assert explorer["total"] == len(explorer["rows"])
    assert explorer["total"] == 3200
    v8_row = next(row for row in explorer["rows"] if row["v8_prediction"])
    assert v8_row["v8_correct"] is not None
    v8_identifier = v8_row["variation_id"]
    v8_detail = local_client.get(f"/api/prediction-explorer/{v8_identifier}")
    assert v8_detail.status_code == 200
    assert "V8" in v8_detail.get_json()["model_results"]
    v8_review = local_client.patch(
        f"/api/prediction-explorer/V8/{v8_identifier}/review",
        json={"status": "reviewed", "category": "unknown", "notes": "Checked V8."},
    )
    assert v8_review.status_code == 200
    reviewed_detail = local_client.get(
        f"/api/prediction-explorer/{v8_identifier}"
    ).get_json()
    assert reviewed_detail["manual_reviews"][f"V8:{v8_identifier}"]["notes"] == (
        "Checked V8."
    )
    explorer_row = explorer["rows"][0]
    identifier = explorer_row["variation_id"]
    model_id = next(
        model
        for model in ("V4", "V5", "V6", "V7", "V8")
        if explorer_row[f"{model.lower()}_prediction"]
    )
    detail = local_client.get(f"/api/prediction-explorer/{identifier}")
    assert detail.status_code == 200
    assert "older_features" in detail.get_json()
    review = local_client.patch(
        f"/api/prediction-explorer/{model_id}/{identifier}/review",
        json={"status": "reviewed", "category": "unknown", "notes": "Checked."},
    )
    assert review.status_code == 200
    assert reviews.is_file()

    timeline_payload = local_client.get("/api/research-timeline").get_json()
    assert len(timeline_payload["tasks"]) == 14
    task = timeline_payload["tasks"][2]
    updated = local_client.patch(
        "/api/research-timeline/status",
        json={"title": task["title"], "status": "in_progress"},
    )
    assert updated.status_code == 200


def test_v8_result_pages_preserve_metrics_and_claim_boundary(
    client: FlaskClient,
) -> None:
    prediction_page = client.get("/prediction_results.html").get_data(as_text=True)
    assert "AI Temporal V8" in prediction_page
    assert "87.1212%" in prediction_page
    assert "TN 740, FP 74, FN 31, TP 155" in prediction_page
    assert "-2.45 to +3.31 points" in prediction_page
    assert "did not establish overall superiority" in prediction_page
    assert "membership is reconstructible" in prediction_page

    model_page = client.get("/model_versions.html").get_data(as_text=True)
    assert "V1 Through V8" in model_page
    assert "retrospective, outcome-selected test" in model_page
    assert "did not demonstrate overall superiority" in model_page
    assert "out-of-fold labels were reused" in model_page


def test_pilot_endpoint_shows_empty_first_run(
    client: FlaskClient,
) -> None:
    """The initial browser workspace must contain no invented records."""
    response = client.get("/api/pilot")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["records"] == []
    assert payload["count"] == 0
    assert payload["first_run"] is True
    assert "protective" in payload["classification_options"]
    assert "drug response" in payload["classification_options"]


def test_dashboard_live_lookup_requires_approval_and_reports_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful mocked lookup should update the dashboard session summary."""
    result = ClinVarVariant(
        variant_identifier="VCV000014206.1",
        variation_id="14206",
        gene_name="CCL2",
        classification="protective",
        associated_conditions=("Synthetic test condition",),
        review_status="no assertion criteria provided",
        evidence_summary="SCV submissions listed: 1",
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
        response_bytes=321,
    )
    monkeypatch.setattr(
        "website.dashboard.app.lookup_clinvar_variant", lambda identifier: result
    )
    local_client = create_app({"TESTING": True}).test_client()

    plan = local_client.post("/api/clinvar/plan", json={"query": "14206"})
    assert plan.status_code == 200
    assert plan.get_json()["plan"]["estimated_max_bytes"] == 1_000_000
    unapproved = local_client.post("/api/clinvar/lookup", json={"query": "14206"})
    assert unapproved.status_code == 428
    lookup = local_client.post(
        "/api/clinvar/lookup", json={"query": "14206", "approved": True}
    )
    assert lookup.status_code == 200
    assert lookup.get_json()["variants"][0]["gene_name"] == "CCL2"
    assert lookup.get_json()["transfer"]["actual_bytes"] == 321

    status = local_client.get("/api/clinvar/status").get_json()
    assert status["connection_status"] == "Connected"
    assert status["last_lookup"] == {
        "variant": "VCV000014206.1",
        "gene": "CCL2",
        "classification": "protective",
    }


def test_dashboard_reports_lookup_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mocked offline failure should remain visible and return no fake record."""

    def fail_lookup(identifier: str) -> ClinVarVariant:
        raise ClinVarConnectionError("NCBI is unavailable")

    monkeypatch.setattr("website.dashboard.app.lookup_clinvar_variant", fail_lookup)
    local_client = create_app({"TESTING": True}).test_client()

    lookup = local_client.post(
        "/api/clinvar/lookup", json={"query": "14206", "approved": True}
    )
    assert lookup.status_code == 502
    assert lookup.get_json() == {"error": "NCBI is unavailable"}
    status = local_client.get("/api/clinvar/status").get_json()
    assert status["connection_status"] == "Not connected"
    assert status["last_lookup"] is None
