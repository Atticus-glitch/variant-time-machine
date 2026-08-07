"""Dashboard safeguards for published V9.1 internal-development evidence."""

from pathlib import Path

import pytest
from flask.testing import FlaskClient

from variant_time_machine.pilot_workspace import empty_workspace, save_workspace
from website.dashboard.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> FlaskClient:
    workspace = tmp_path / "pilot_workspace.json"
    save_workspace(workspace, empty_workspace())
    app = create_app({"TESTING": True, "PILOT_WORKSPACE_PATH": workspace})
    return app.test_client()


def test_v9_1_summary_exposes_nested_metrics_and_locks(client: FlaskClient) -> None:
    response = client.get("/api/v9-1/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["manifest"]["official_v9_1_model"] is False
    assert payload["manifest"]["final_test_evaluated"] is False
    assert payload["selected"]["candidate"] == "nested_family_selection_procedure"
    assert payload["confusion_matrix"] == {"TN": 708, "FP": 106, "FN": 19, "TP": 167}
    mlp = next(row for row in payload["candidates"] if row["candidate"] == "small_mlp")
    assert mlp["status"] == "invalid_protocol_mismatch_not_ranked"


def test_v9_1_case_explorer_filters_and_paginates(client: FlaskClient) -> None:
    errors = client.get("/api/v9-1/cases?correctness=wrong&page_size=10")
    assert errors.status_code == 200
    payload = errors.get_json()
    assert payload["total"] == 125
    assert len(payload["items"]) == 10
    assert all(row["v9_1_correct"] == "False" for row in payload["items"])

    disagreement = client.get("/api/v9-1/cases?disagreement=v9&page_size=100")
    assert disagreement.get_json()["total"] == 69
    assert client.get("/api/v9-1/cases?page=bad").status_code == 400


def test_v9_1_pages_and_safe_downloads_load(client: FlaskClient) -> None:
    training = client.get("/v9_training.html").get_data(as_text=True)
    results = client.get("/v9_results.html").get_data(as_text=True)
    explorer = client.get("/v9_explorer.html").get_data(as_text=True)
    assert "V9.1 Model Search" in training
    assert "Why Original V9 Scored Lower" in training
    assert "V9.1 Internal Results" in results
    assert "does not fairly beat V8" in results
    assert 'id="v9-1-case-rows"' in explorer
    assert client.get("/api/v9-1/download/run_manifest.json").status_code == 200
    assert client.get("/api/v9-1/download/model.joblib").status_code == 404
