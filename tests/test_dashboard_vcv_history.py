"""Dashboard API tests for bounded VCV version-history exploration."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from variant_time_machine.pilot_workspace import empty_workspace, save_workspace
from variant_time_machine.vcv_history import (
    ClassificationBlock,
    VCVHistoryResult,
    VCVHistorySummary,
    VCVRecord,
    VersionResult,
    compare_consecutive,
)
from variant_time_machine.vcv_history_store import VERIFICATION_REQUIREMENTS
from website.dashboard.app import create_app

ACCESSION = "VCV000014206"


def _record(version: int, classification: str = "Uncertain significance") -> VCVRecord:
    empty = ClassificationBlock(None, None, None, None)
    return VCVRecord(
        accession=ACCESSION,
        version=version,
        accession_version=f"{ACCESSION}.{version}",
        variation_id="14206",
        record_type="classified",
        genes=("CCL2",),
        name="test record",
        hgvs=("NM_000001.2:c.10A>G",),
        date_created="2020-01-01",
        date_last_updated=f"202{min(version, 9)}-01-01",
        date_deleted=None,
        germline=ClassificationBlock(classification, "criteria provided", None, 1),
        somatic_clinical_impact=empty,
        oncogenicity=empty,
        conditions=("Test condition",),
        record_status="current",
        replaced_by=(),
        replacements=(),
        deleted=False,
        warnings=(),
    )


def _outcome(version: int, *, current: bool = False) -> VersionResult:
    classification = "Pathogenic" if version > 1 else "Uncertain significance"
    record = _record(version, classification)
    identifier = ACCESSION if current else record.accession_version
    raw = f'<VariationArchive Accession="{ACCESSION}" Version="{version}" />'
    return VersionResult(
        requested_identifier=identifier,
        source_request=f"https://eutils.ncbi.nlm.nih.gov/efetch?{identifier}",
        retrieved_at_utc="2026-07-27T00:00:00+00:00",
        response_bytes=len(raw.encode()),
        status="available",
        record=record,
        raw_xml=raw,
    )


def _history(
    versions: tuple[int, ...], current: VersionResult, *, cancelled: bool = False
) -> VCVHistoryResult:
    results = tuple(_outcome(version) for version in versions)
    comparisons = compare_consecutive(results)
    changed = any(
        item.detected_classification_change == "VUS_to_Pathogenic"
        for item in comparisons
    )
    summary = VCVHistorySummary(
        first_available_version=versions[0] if versions else None,
        newest_available_version=versions[-1] if versions else None,
        retrieved_version_count=len(results),
        any_germline_classification_changed=changed,
        first_detected_germline_change=comparisons[0] if changed else None,
        latest_germline_classification=(
            results[-1].record.germline.classification if results else None
        ),
        unresolved_warnings=("Retrieval cancelled.",) if cancelled else (),
    )
    return VCVHistoryResult(
        requested_accession=ACCESSION,
        current_identifier=current.record.accession_version if current.record else None,
        version_plan=versions,
        current_result=current,
        results=results,
        comparisons=comparisons,
        summary=summary,
        total_response_bytes=current.response_bytes
        + sum(item.response_bytes for item in results),
        cancelled=cancelled,
    )


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
            "AI_HOLDOUT_V4_RESULTS_DIR": tmp_path / "ai_v4",
        }
    )


@pytest.fixture
def client(dashboard_app: Flask) -> FlaskClient:
    return dashboard_app.test_client()


def _set_current(app: Flask, version: int, calls: list[str] | None = None) -> None:
    def fetch(accession: str) -> VersionResult:
        if calls is not None:
            calls.append(accession)
        return _outcome(version, current=True)

    app.config["VCV_CURRENT_FETCHER"] = fetch


def _prime(client: FlaskClient, version: int = 3) -> None:
    _set_current(client.application, version)
    response = client.post(
        "/api/vcv-history/current", json={"accession": ACCESSION, "approved": True}
    )
    assert response.status_code == 200


def _poll(client: FlaskClient, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        payload = client.get(f"/api/vcv-history/operations/{operation_id}").get_json()
        if payload["state"] != "running":
            return payload
        time.sleep(0.01)
    pytest.fail("background VCV history operation did not finish")


def test_current_plan_is_no_network_strict_and_lookup_requires_approval(
    client: FlaskClient,
) -> None:
    calls: list[str] = []
    _set_current(client.application, 4, calls)
    plan = client.post(
        "/api/vcv-history/current-plan", json={"accession": f"{ACCESSION}.2"}
    )
    assert plan.status_code == 200
    assert plan.get_json()["plan"]["accession"] == ACCESSION
    assert plan.get_json()["plan"]["request_count"] == 1
    assert plan.get_json()["plan"]["estimated_max_bytes"] == 10 * 1024 * 1024
    assert calls == []
    assert (
        client.post(
            "/api/vcv-history/current", json={"accession": ACCESSION}
        ).status_code
        == 428
    )
    current = client.post(
        "/api/vcv-history/current",
        json={"accession": f"{ACCESSION}.2", "approved": True},
    )
    assert current.status_code == 200
    assert current.get_json()["current_version"] == 4
    assert current.get_json()["record"]["accession"] == ACCESSION
    assert current.get_json()["transfer"]["actual_bytes"] > 0
    assert calls == [ACCESSION]
    for unsafe in ("../VCV000014206", "vcv000014206", "VCV000014206.0"):
        assert (
            client.post(
                "/api/vcv-history/current-plan", json={"accession": unsafe}
            ).status_code
            == 400
        )


def test_plans_require_cached_current_and_cover_all_custom_endpoints_and_limits(
    client: FlaskClient,
) -> None:
    missing = client.post(
        "/api/vcv-history/plan", json={"accession": ACCESSION, "mode": "all"}
    )
    assert missing.status_code == 409
    _prime(client, 4)
    all_plan = client.post(
        "/api/vcv-history/plan", json={"accession": ACCESSION, "mode": "all"}
    ).get_json()["plan"]
    assert all_plan["requested_versions"] == [1, 2, 3, 4]
    assert all_plan["request_count"] == 4
    custom = client.post(
        "/api/vcv-history/plan",
        json={
            "accession": ACCESSION,
            "mode": "custom",
            "start_version": 2,
            "end_version": 4,
        },
    ).get_json()["plan"]
    assert custom["requested_versions"] == [2, 3, 4]
    endpoints = client.post(
        "/api/vcv-history/plan",
        json={"accession": ACCESSION, "mode": "endpoints"},
    ).get_json()["plan"]
    assert endpoints["requested_versions"] == [1, 4]

    _prime(client, 26)
    blocked = client.post(
        "/api/vcv-history/plan", json={"accession": ACCESSION, "mode": "all"}
    )
    assert blocked.status_code == 413
    assert "custom or endpoints" in blocked.get_json()["error"]
    assert (
        client.post(
            "/api/vcv-history/plan",
            json={"accession": ACCESSION, "mode": "endpoints"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/vcv-history/plan",
            json={
                "accession": ACCESSION,
                "mode": "custom",
                "start_version": 1,
                "end_version": 25,
            },
        ).status_code
        == 200
    )


def test_background_completion_progress_saved_endpoints_and_dynamic_metrics(
    client: FlaskClient,
) -> None:
    _prime(client, 3)

    def fetch_history(accession: str, **kwargs: Any) -> VCVHistoryResult:
        assert accession == ACCESSION
        progress = kwargs["progress"]
        versions = tuple(kwargs["versions"])
        for version in versions:
            progress({"event": "parsed", "identifier": f"{ACCESSION}.{version}"})
        return _history(versions, kwargs["current_result"])

    client.application.config["VCV_HISTORY_FETCHER"] = fetch_history
    plan = client.post(
        "/api/vcv-history/plan", json={"accession": ACCESSION, "mode": "all"}
    ).get_json()["plan"]
    unapproved = client.post("/api/vcv-history/explore", json={"plan": plan})
    assert unapproved.status_code == 428
    started = client.post(
        "/api/vcv-history/explore", json={"approved": True, "plan": plan}
    )
    assert started.status_code == 202
    operation = _poll(client, started.get_json()["operation_id"])
    assert operation["state"] == "completed"
    assert [event["sequence"] for event in operation["progress_events"]] == [1, 2, 3]
    assert operation["result"]["saved_accession"] == ACCESSION
    assert "raw_xml" not in str(operation["result"])

    listed = client.get("/api/vcv-histories").get_json()
    assert listed["histories"][0]["accession"] == ACCESSION
    assert listed["metrics"]["versions_retrieved"] == 3
    full = client.get(f"/api/vcv-histories/{ACCESSION}")
    assert full.status_code == 200
    assert "raw_xml" not in full.get_data(as_text=True)
    assert client.get(f"/api/vcv-histories/{ACCESSION}/raw/v1.xml").status_code == 404
    assert client.post("/api/archive/extract", json={}).status_code == 404

    status = client.get("/api/status").get_json()
    progress = status["research_progress"]
    assert progress["candidates_selected"] == 0
    assert progress["current_records_retrieved"] == 1
    assert progress["current_records_retrieved_this_session"] == 1
    assert progress["histories_explored"] == 1
    assert progress["versions_retrieved"] == 3
    assert progress["histories_with_germline_change"] == 1
    assert progress["total_recorded_history_transfer_bytes"] > 0
    assert status["transfer_safety"]["vcv_history_storage_bytes"] > 0
    assert "Review" in status["next_tasks"][1]


def test_cancellation_uses_event_and_saves_partial_result(client: FlaskClient) -> None:
    _prime(client, 3)
    entered = threading.Event()

    def cancellable(accession: str, **kwargs: Any) -> VCVHistoryResult:
        assert accession == ACCESSION
        entered.set()
        cancel = kwargs["cancel"]
        deadline = time.monotonic() + 2
        while not cancel.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        return _history((1,), kwargs["current_result"], cancelled=True)

    client.application.config["VCV_HISTORY_FETCHER"] = cancellable
    started = client.post(
        "/api/vcv-history/explore",
        json={"approved": True, "accession": ACCESSION, "mode": "endpoints"},
    )
    assert started.status_code == 202
    assert entered.wait(timeout=1)
    operation_id = started.get_json()["operation_id"]
    cancelled = client.post(f"/api/vcv-history/operations/{operation_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.get_json()["cancellation_requested"] is True
    operation = _poll(client, operation_id)
    assert operation["state"] == "cancelled"
    assert operation["result"]["saved_accession"] == ACCESSION


def test_review_actions_checklist_and_manual_corrections_preserve_automatic_values(
    client: FlaskClient,
) -> None:
    _prime(client, 2)
    current = _outcome(2, current=True)
    client.application.config["VCV_HISTORY_FETCHER"] = lambda _accession, **kwargs: (
        _history(tuple(kwargs["versions"]), current)
    )
    started = client.post(
        "/api/vcv-history/explore",
        json={"approved": True, "accession": ACCESSION, "mode": "all"},
    )
    _poll(client, started.get_json()["operation_id"])

    correction = {"versions.0.record.germline.classification": "Likely benign"}
    saved = client.patch(
        f"/api/vcv-histories/{ACCESSION}/review",
        json={
            "action": "mark_needs_review",
            "manual_corrections": correction,
            "notes": "Check this against the official source.",
        },
    )
    assert saved.status_code == 200
    assert saved.get_json()["review"]["manual_corrections"] == correction
    automatic = client.get(f"/api/vcv-histories/{ACCESSION}").get_json()
    assert (
        automatic["versions"]["versions"][0]["record"]["germline"]["classification"]
        == "Uncertain significance"
    )

    refused = client.patch(
        f"/api/vcv-histories/{ACCESSION}/review",
        json={"action": "mark_manually_verified"},
    )
    assert refused.status_code == 400
    verified = client.patch(
        f"/api/vcv-histories/{ACCESSION}/review",
        json={
            "action": "mark_manually_verified",
            "reviewer_decision": "include",
            "verification": {item: True for item in VERIFICATION_REQUIREMENTS},
            "sources": ["https://eutils.ncbi.nlm.nih.gov/efetch"],
        },
    )
    assert verified.status_code == 200
    assert verified.get_json()["review"]["status"] == "manually_verified"
    assert verified.get_json()["review"]["manual_corrections"] == correction
    cleared = client.patch(
        f"/api/vcv-histories/{ACCESSION}/review",
        json={"action": "mark_needs_review", "notes": ""},
    )
    assert cleared.status_code == 200
    assert (
        client.patch(
            f"/api/vcv-histories/{ACCESSION}/review",
            json={"action": "mark_ambiguous"},
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/vcv-histories/{ACCESSION}/review",
            json={"action": "add_note", "notes": "Second note."},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/vcv-histories/{ACCESSION}/review",
            json={"action": "add_note", "current_identifier": "tamper"},
        ).status_code
        == 400
    )
    assert client.patch(
        "/api/vcv-histories/../VCV000014206/review",
        json={"action": "add_note", "notes": "unsafe"},
    ).status_code in {400, 404}
