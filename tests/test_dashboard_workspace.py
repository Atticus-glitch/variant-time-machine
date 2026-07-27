"""Mocked browser API tests for the complete Pilot Workspace workflow."""

import subprocess
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from variant_time_machine.clinvar_api import ClinVarGeneSearch, ClinVarVariant
from variant_time_machine.pilot_workspace import (
    CHECKLIST_FIELDS,
    empty_workspace,
    save_workspace,
)
from website.dashboard.app import create_app


def _variant(*, classification: str = "Uncertain significance") -> ClinVarVariant:
    return ClinVarVariant(
        variant_identifier="VCV000014206.2",
        variation_id="14206",
        gene_name="CCL2",
        classification=classification,
        associated_conditions=("Test condition",),
        review_status="criteria provided, single submitter",
        evidence_summary=None,
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
        response_bytes=321,
    )


def _client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FlaskClient, Path]:
    path = tmp_path / "pilot_workspace.json"
    save_workspace(path, empty_workspace())
    monkeypatch.setattr(
        "website.dashboard.app.lookup_clinvar_variant", lambda _query: _variant()
    )
    app = create_app({"TESTING": True, "PILOT_WORKSPACE_PATH": path})
    return app.test_client(), path


def _prime_lookup(client: FlaskClient) -> None:
    response = client.post(
        "/api/clinvar/lookup", json={"query": "14206", "approved": True}
    )
    assert response.status_code == 200


def _add(client: FlaskClient) -> dict[str, object]:
    response = client.post(
        "/api/pilot",
        json={
            "variant_id": "14206",
            "selection_reason": "Clear identifiers for the first browser test",
            "notes": "Initial note",
            "intended_historical_date": "2020-01-01",
            "understood_current_only": True,
        },
    )
    assert response.status_code == 201
    return response.get_json()["record"]


def _verified_changes() -> dict[str, object]:
    return {
        "older_release_date": "2020-01-01",
        "older_classification": "uncertain significance",
        "newer_comparison_date": "2026-07-26",
        "newer_classification": "protective",
        "historical_source_url": (
            "https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/"
        ),
        "historical_classification_type": "germline",
        "verification_notes": "Checked exact dates, scope, and source.",
        "verification_checklist": {field: True for field in CHECKLIST_FIELDS},
    }


def test_add_requires_current_only_confirmation_and_prevents_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    _prime_lookup(client)
    refused = client.post(
        "/api/pilot",
        json={"variant_id": "14206", "selection_reason": "Test"},
    )
    assert refused.status_code == 400
    assert "not a historical result" in refused.get_json()["error"]
    _add(client)
    duplicate = client.post(
        "/api/pilot",
        json={
            "variant_id": "14206",
            "selection_reason": "Duplicate",
            "understood_current_only": True,
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["duplicate"] is True
    assert duplicate.get_json()["options"] == [
        "open_existing",
        "update_current",
        "cancel",
    ]
    refreshed = client.post(
        "/api/pilot",
        json={
            "variant_id": "14206",
            "selection_reason": "Existing record",
            "understood_current_only": True,
            "on_duplicate": "update_current",
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.get_json()["updated"] is True


def test_edit_notes_status_and_restart_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, path = _client(tmp_path, monkeypatch)
    _prime_lookup(client)
    _add(client)
    edited = client.patch(
        "/api/pilot/14206",
        json={
            "action": "mark_reviewing",
            "changes": {"notes": "Saved through the browser API"},
        },
    )
    assert edited.status_code == 200
    assert edited.get_json()["record"]["review_status"] == "reviewing"
    restarted = create_app(
        {"TESTING": True, "PILOT_WORKSPACE_PATH": path}
    ).test_client()
    record = restarted.get("/api/pilot/14206").get_json()["record"]
    assert record["notes"] == "Saved through the browser API"
    assert record["review_status"] == "reviewing"


def test_verification_checklist_is_enforced_by_dashboard_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    _prime_lookup(client)
    _add(client)
    refused = client.patch(
        "/api/pilot/14206",
        json={
            "action": "mark_verified",
            "changes": _verified_changes()
            | {"verification_checklist": {field: False for field in CHECKLIST_FIELDS}},
        },
    )
    assert refused.status_code == 400
    assert "checklist" in refused.get_json()["error"]
    verified = client.post(
        "/api/pilot/14206/verify", json={"changes": _verified_changes()}
    )
    assert verified.status_code == 200
    record = verified.get_json()["record"]
    assert record["review_status"] == "verified"
    assert record["older_classification"] == "uncertain significance"
    assert record["newer_classification"] == "protective"
    summary = client.get("/api/status").get_json()["historical_comparison"]
    assert summary["total_verified_variants"] == 1
    assert summary["variants_with_classification_changes"] == 1


@pytest.mark.parametrize("action", ["mark_ambiguous", "exclude"])
def test_ambiguous_and_excluded_actions_require_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    _prime_lookup(client)
    _add(client)
    refused = client.patch("/api/pilot/14206", json={"action": action, "changes": {}})
    assert refused.status_code == 400
    accepted = client.patch(
        "/api/pilot/14206",
        json={
            "action": action,
            "changes": {"ambiguity_reason": "Condition scope is unclear."},
        },
    )
    assert accepted.status_code == 200


def test_missing_historical_fields_stay_empty_in_dashboard_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    _prime_lookup(client)
    record = _add(client)
    assert record["older_release_date"] == ""
    assert record["older_classification"] == ""
    assert record["timeline"]["change_category"] == (
        "Historical classification not yet verified."
    )


def test_gene_lookup_is_bounded_and_reports_actual_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "website.dashboard.app.search_clinvar_gene_result",
        lambda _gene: ClinVarGeneSearch(("14206",), 100),
    )
    plan = client.post("/api/clinvar/plan", json={"query": "CCL2"}).get_json()["plan"]
    assert plan["estimated_max_bytes"] == 6_000_000
    assert plan["is_small"] is True
    lookup = client.post(
        "/api/clinvar/lookup", json={"query": "CCL2", "approved": True}
    )
    assert lookup.status_code == 200
    assert lookup.get_json()["transfer"]["actual_bytes"] == 421
    safety = client.get("/api/transfer-safety").get_json()
    assert safety["large_download_protection"] == "ON"
    assert safety["last_request"]["actual_bytes"] == 421


def test_invalid_or_shell_like_identifier_is_rejected_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("dashboard executed a shell command"),
    )
    response = client.post(
        "/api/clinvar/plan", json={"query": "14206; touch /tmp/not-allowed"}
    )
    assert response.status_code == 400
    assert "gene symbol" in response.get_json()["error"]


def test_normal_dashboard_exposes_no_archive_scan_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _path = _client(tmp_path, monkeypatch)
    response = client.post("/api/archive/extract", json={"approved": True})
    assert response.status_code == 404
    rules = {rule.rule for rule in client.application.url_map.iter_rules()}
    assert not any("archive" in rule for rule in rules)
    assert client.delete("/api/pilot/14206").status_code == 405
