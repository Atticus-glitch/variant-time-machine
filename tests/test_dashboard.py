"""Tests for the local Flask research dashboard."""

from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from variant_time_machine.clinvar_api import (
    ClinVarConnectionError,
    ClinVarVariant,
)
from website.dashboard.app import SYNTHETIC_NOTICE, create_app


@pytest.fixture
def dashboard_app() -> Flask:
    """Create a dashboard configured for Flask testing."""
    return create_app({"TESTING": True})


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
    assert "Latest Research Note" in page
    assert SYNTHETIC_NOTICE in page

    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/lookup.js").status_code == 200
    assert client.get("/static/pilot.js").status_code == 200
    lookup_page = client.get("/variant_lookup.html")
    assert lookup_page.status_code == 200
    assert "ClinVar Variant Lookup" in lookup_page.get_data(as_text=True)
    pilot_page = client.get("/historical_pilot.html")
    assert pilot_page.status_code == 200
    assert "Historical Pilot" in pilot_page.get_data(as_text=True)


def test_progress_endpoint_reports_all_stages_honestly(client: FlaskClient) -> None:
    """Progress should use only the declared status values and include every stage."""
    response = client.get("/api/progress")
    assert response.status_code == 200
    items = response.get_json()["items"]
    assert [item["name"] for item in items] == [
        "Project setup",
        "Load genetic data",
        "Clean and organize variants",
        "Compare old and new ClinVar releases",
        "Create timeline dataset",
        "Find useful biological clues",
        "Train prediction models",
        "Evaluate results",
        "Create final science fair presentation",
    ]
    assert {item["status"] for item in items}.issubset(
        {"Not Started", "Working", "Complete"}
    )
    statuses = {item["name"]: item["status"] for item in items}
    assert statuses["Project setup"] == "Complete"
    assert statuses["Train prediction models"] == "Not Started"
    assert statuses["Create final science fair presentation"] == "Not Started"
    assert [item["step"] for item in items] == list(range(1, 10))


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
    assert payload["current_milestone"] == "Historical ClinVar matching pipeline"
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
        "pilot_release_pair",
        "pilot_extraction",
        "storage",
    }.issubset(payload["system"])
    assert "data/example_variants.csv" in payload["system"]["files_created"]
    assert payload["research_notes"]["title"] == (
        "2026-07-26 Bounded Historical XML Pilot"
    )
    assert "2024-02-01 and 2025-02-06" in (payload["research_notes"]["content"])
    assert payload["clinvar_connection"]["connection_status"] == "Not connected"
    assert payload["historical_comparison"] == {
        "total_verified_variants": 0,
        "variants_with_classification_changes": 0,
        "last_verified_comparison": "None yet",
    }


def test_pilot_endpoint_shows_current_data_and_missing_history(
    client: FlaskClient,
) -> None:
    """The unextracted pilot must keep archive values blank and state why."""
    response = client.get("/api/pilot")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["rows"]) == 16
    assert "extraction has not been run" in payload["historical_data_status"]
    assert payload["rows"][0]["variation_id"] == "2"
    assert payload["rows"][0]["current_gene"] == "AP5Z1"
    assert payload["rows"][0]["older_germline_classification"] is None
    assert payload["rows"][0]["newer_germline_classification"] is None
    assert payload["rows"][0]["automatic_verification_status"] == (
        "requires_manual_review"
    )


def test_pilot_review_endpoint_persists_explicit_human_state(
    tmp_path: Path,
) -> None:
    """A review should be saved locally and returned on the next pilot request."""
    review_path = tmp_path / "pilot_review.json"
    local_client = create_app(
        {"TESTING": True, "PILOT_REVIEW_PATH": review_path}
    ).test_client()
    response = local_client.post(
        "/api/pilot/review/2",
        json={"status": "Needs follow-up", "notes": "Check replacement metadata"},
    )
    assert response.status_code == 200
    assert review_path.is_file()
    row = local_client.get("/api/pilot").get_json()["rows"][0]
    assert row["manual_review"]["status"] == "Needs follow-up"
    assert row["manual_review"]["notes"] == "Check replacement metadata"

    unknown = local_client.post(
        "/api/pilot/review/999999",
        json={"status": "Not reviewed", "notes": ""},
    )
    assert unknown.status_code == 404


def test_dashboard_live_lookup_updates_connection_status(
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
    )
    monkeypatch.setattr(
        "website.dashboard.app.lookup_clinvar_variant", lambda identifier: result
    )
    local_client = create_app({"TESTING": True}).test_client()

    lookup = local_client.get("/api/clinvar/lookup?variant_id=14206")
    assert lookup.status_code == 200
    assert lookup.get_json()["variant"]["gene_name"] == "CCL2"

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

    lookup = local_client.get("/api/clinvar/lookup?variant_id=14206")
    assert lookup.status_code == 502
    assert lookup.get_json() == {"error": "NCBI is unavailable"}
    status = local_client.get("/api/clinvar/status").get_json()
    assert status["connection_status"] == "Not connected"
    assert status["last_lookup"] is None
