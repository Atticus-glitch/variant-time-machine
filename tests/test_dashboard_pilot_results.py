"""Local dashboard tests for the real pilot results page and API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from variant_time_machine.pilot_results import NOTICE, OUTPUT_FILENAMES
from variant_time_machine.pilot_workspace import empty_workspace, save_workspace
from website.dashboard.app import create_app


@pytest.fixture
def dashboard_app(tmp_path: Path) -> Flask:
    workspace = tmp_path / "pilot_workspace.json"
    save_workspace(workspace, empty_workspace())
    return create_app(
        {
            "TESTING": True,
            "PILOT_WORKSPACE_PATH": workspace,
            "VCV_HISTORY_ROOT": tmp_path / "histories",
            "PILOT_RESULTS_ROOT": tmp_path / "pilot_results",
        }
    )


@pytest.fixture
def client(dashboard_app: Flask) -> FlaskClient:
    return dashboard_app.test_client()


def _aggregation() -> dict[str, object]:
    summary = {
        "candidates_attempted": 3,
        "candidates_successfully_retrieved": 2,
        "total_official_versions_retrieved": 5,
        "variants_with_germline_change": 1,
        "variants_with_no_germline_change": 1,
        "variants_unable_to_compare": 1,
        "change_category_counts": {
            "No_Germline_Change": 1,
            "Unable_to_Compare": 1,
            "VUS_to_Pathogenic": 1,
        },
        "total_bytes_transferred": 321,
        "total_local_storage_bytes": 654,
        "manually_verified": 1,
        "needs_review": 0,
        "generated_at_utc": "2026-07-27T12:00:00+00:00",
        "notice": NOTICE,
    }
    row = {
        "VCV accession": "VCV000014026",
        "Variation ID": "14026",
        "gene": "CCL2",
        "first version": 1,
        "newest version": 2,
        "versions retrieved": 2,
        "first aggregate germline classification": "Uncertain significance",
        "newest aggregate germline classification": "Pathogenic",
        "detected change category": "VUS_to_Pathogenic",
        "automatic confidence": "high",
        "automatic result": "VUS_to_Pathogenic",
        "manually reviewed status": "manually_verified",
        "manual confirmed result": "Other_Germline_Change",
        "warnings": "",
    }
    return {"rows": [row], "summary": summary, "transfer_manifest": {}}


def test_page_has_critical_copy_navigation_batch_gate_and_no_synthetic_claim(
    client: FlaskClient,
) -> None:
    response = client.get("/pilot_results.html")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Pilot Results" in page
    assert (
        "This is a small technical pilot. It tests whether official VCV histories "
        "can be collected and compared. It does not yet prove that future "
        "reclassification can be predicted."
    ) in page
    assert NOTICE in page
    assert "VCV000000002\nVCV000000005\nVCV000014026" in page
    assert "Include the existing VCV000014026 case" in page
    assert page.count('id="batch-confirmation"') == 1
    assert page.count('id="run-batch"') == 1
    assert "Synthetic example data" not in page
    assert "/version_history.html" in page
    assert client.get("/static/pilot_results.js").status_code == 200

    for route in ("/", "/pilot_workspace.html", "/version_history.html"):
        assert 'href="/pilot_results.html"' in client.get(route).get_data(as_text=True)


def test_summary_api_returns_live_six_values_and_separate_results(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "website.dashboard.app.aggregate_pilot_results",
        lambda history_root, output_root: _aggregation(),
    )
    payload = client.get("/api/pilot-results").get_json()
    summary = payload["summary"]
    assert [
        summary["candidates_attempted"],
        summary["candidates_successfully_retrieved"],
        summary["total_official_versions_retrieved"],
        summary["variants_with_germline_change"],
        summary["variants_with_no_germline_change"],
        summary["variants_unable_to_compare"],
    ] == [3, 2, 5, 1, 1, 1]
    assert summary["total_bytes_transferred"] == 321
    assert summary["total_local_storage_bytes"] == 654
    assert payload["rows"][0]["automatic result"] == "VUS_to_Pathogenic"
    assert payload["rows"][0]["manual confirmed result"] == "Other_Germline_Change"
    assert payload["all_outputs_exist"] is False
    assert set(payload["output_files"]) == set(OUTPUT_FILENAMES)
    assert "notice" not in payload.get("synthetic", {})


def test_downloads_have_fixed_names_content_and_attachment_headers(
    client: FlaskClient,
) -> None:
    root = Path(client.application.config["PILOT_RESULTS_ROOT"])
    root.mkdir()
    for filename in OUTPUT_FILENAMES:
        (root / filename).write_bytes(f"fixture:{filename}".encode())

    for filename in OUTPUT_FILENAMES:
        response = client.get(f"/api/pilot-results/download/{filename}")
        assert response.status_code == 200
        assert response.data == f"fixture:{filename}".encode()
        assert (
            f"attachment; filename={filename}"
            in response.headers["Content-Disposition"]
        )

    assert client.get("/api/pilot-results/download/unknown.csv").status_code == 404
    traversal = client.get("/api/pilot-results/download/%2E%2E%2Fbatch_manifest.json")
    assert traversal.status_code == 404


def test_main_progress_detects_result_and_batch_output_bandwidth(
    client: FlaskClient,
) -> None:
    root = Path(client.application.config["PILOT_RESULTS_ROOT"])
    root.mkdir()
    (root / "pilot_results.csv").write_text("header\n", encoding="utf-8")
    (root / "batch_manifest.json").write_text(
        json.dumps({"actual_new_batch_bytes": 9876}), encoding="utf-8"
    )

    payload = client.get("/api/status").get_json()
    progress = payload["research_progress"]
    assert progress["pilot_results_file_created"] is True
    assert progress["pilot_output_bandwidth_bytes"] == 9876
    assert payload["next_tasks"] == [
        "Review high-confidence wrong Clue Score V1 predictions.",
        "Review matching and scope for unscorable baseline records.",
        "Design Version 2 separately without changing Version 1.",
    ]
    assert str(root / "pilot_results.csv") in payload["system"]["files_created"]
