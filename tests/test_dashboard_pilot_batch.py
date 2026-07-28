"""Dashboard API tests for approval-gated pilot batch retrieval."""

from __future__ import annotations

import json
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
from variant_time_machine.vcv_history_store import list_histories, save_history
from website.dashboard.app import create_app

FIRST = "VCV000000001"
SECOND = "VCV000000002"
GENERATED = "2026-07-27T12:00:00+00:00"


def _record(accession: str, version: int) -> VCVRecord:
    empty = ClassificationBlock(None, None, None, None)
    return VCVRecord(
        accession=accession,
        version=version,
        accession_version=f"{accession}.{version}",
        variation_id=str(int(accession[3:])),
        record_type="classified",
        genes=(f"GENE{int(accession[3:])}",),
        name="pilot fixture",
        hgvs=(),
        date_created="2020-01-01",
        date_last_updated="2026-01-01",
        date_deleted=None,
        germline=ClassificationBlock(
            "Uncertain significance", "criteria provided", None, 1
        ),
        somatic_clinical_impact=empty,
        oncogenicity=empty,
        conditions=("Fixture condition",),
        record_status="current",
        replaced_by=(),
        replacements=(),
        deleted=False,
        warnings=(),
    )


def _outcome(accession: str, version: int, *, current: bool = False) -> VersionResult:
    record = _record(accession, version)
    identifier = accession if current else record.accession_version
    raw = f'<VariationArchive Accession="{accession}" Version="{version}" />'
    return VersionResult(
        requested_identifier=identifier,
        source_request=(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            f"db=clinvar&id={identifier}"
        ),
        retrieved_at_utc=GENERATED,
        response_bytes=len(raw.encode()),
        status="available",
        record=record,
        raw_xml=raw,
    )


def _history(
    accession: str,
    current: VersionResult,
    *,
    cancelled: bool = False,
) -> VCVHistoryResult:
    assert current.record is not None
    versions = (1,) if current.record.version == 1 else (1, current.record.version)
    results = tuple(_outcome(accession, version) for version in versions)
    comparisons = compare_consecutive(results)
    return VCVHistoryResult(
        requested_accession=accession,
        current_identifier=current.record.accession_version,
        version_plan=versions,
        current_result=current,
        results=results,
        comparisons=comparisons,
        summary=VCVHistorySummary(
            first_available_version=versions[0],
            newest_available_version=versions[-1],
            retrieved_version_count=len(versions),
            any_germline_classification_changed=False,
            first_detected_germline_change=None,
            latest_germline_classification="Uncertain significance",
            unresolved_warnings=("Retrieval cancelled.",) if cancelled else (),
        ),
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
        }
    )


@pytest.fixture
def client(dashboard_app: Flask) -> FlaskClient:
    return dashboard_app.test_client()


def _poll(client: FlaskClient, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        payload = client.get(f"/api/vcv-history/operations/{operation_id}").get_json()
        if payload["state"] != "running":
            return payload
        time.sleep(0.01)
    pytest.fail("background pilot batch did not finish")


def _plan(
    client: FlaskClient, candidates: list[str], **extra: object
) -> dict[str, Any]:
    response = client.post(
        "/api/pilot-batch/plan", json={"candidates": candidates, **extra}
    )
    assert response.status_code == 200
    return response.get_json()["plan"]


def test_plan_is_no_network_validates_candidates_and_enforces_exact_budget(
    client: FlaskClient,
) -> None:
    calls: list[str] = []
    client.application.config["VCV_CURRENT_FETCHER"] = lambda accession: calls.append(
        accession
    )
    three = _plan(client, [f"VCV{number:09d}" for number in range(1, 4)])
    assert three["estimated_max_requests"] == 9
    assert three["estimated_max_transfer"] == 9 * 10 * 1024 * 1024
    assert three["estimated_max_transfer"] < 100_000_000
    assert three["source"].endswith("efetch.fcgi")
    assert three["candidate_count"] == 3
    assert calls == []

    invalid_lists = [
        [],
        [f"VCV{number:09d}" for number in range(1, 12)],
        [FIRST, f"{FIRST}.2"],
        ["../VCV000000001"],
    ]
    for candidates in invalid_lists:
        assert (
            client.post(
                "/api/pilot-batch/plan", json={"candidates": candidates}
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/api/pilot-batch/plan",
            json={"candidates": [f"VCV{number:09d}" for number in range(1, 5)]},
        ).status_code
        == 413
    )


def test_plan_reuses_saved_history_by_default(client: FlaskClient) -> None:
    current = _outcome(FIRST, 2, current=True)
    save_history(
        Path(client.application.config["VCV_HISTORY_ROOT"]),
        _history(FIRST, current),
        app_version="test",
        git_commit="fixture",
    )
    plan = _plan(client, [FIRST, SECOND])
    assert plan["reused_count"] == 1
    assert plan["candidates"][0]["reused"] is True
    assert plan["estimated_max_requests"] == 3

    fresh = _plan(client, [FIRST], reuse_existing=False)
    assert fresh["reused_count"] == 0
    assert fresh["estimated_max_requests"] == 3


def test_plan_records_candidate_selection_transfer(client: FlaskClient) -> None:
    source = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        "db=clinvar&id=VCV000000001&rettype=vcv&retmode=xml"
    )
    plan = _plan(
        client,
        [FIRST],
        candidate_selection_bytes=123,
        candidate_selection_requests=[
            {
                "accession": FIRST,
                "source_request": source,
                "response_bytes": 123,
                "retrieved_at_utc": GENERATED,
            }
        ],
    )
    assert plan["candidate_selection_bytes"] == 123
    assert plan["estimated_total_pilot_transfer"] == 123 + 3 * 10 * 1024 * 1024
    invalid = client.post(
        "/api/pilot-batch/plan",
        json={
            "candidates": [FIRST],
            "candidate_selection_bytes": 124,
            "candidate_selection_requests": plan["candidate_selection_requests"],
        },
    )
    assert invalid.status_code == 400


def test_run_requires_approval_and_rejects_tampered_plan(client: FlaskClient) -> None:
    plan = _plan(client, [FIRST])
    assert client.post("/api/pilot-batch/run", json={"plan": plan}).status_code == 428
    assert (
        client.post(
            "/api/pilot-batch/run", json={"approved": True, "candidates": [FIRST]}
        ).status_code
        == 400
    )
    plan["estimated_max_transfer"] = 1
    response = client.post(
        "/api/pilot-batch/run", json={"approved": True, "plan": plan}
    )
    assert response.status_code == 400
    assert "does not match" in response.get_json()["error"]


def test_two_candidates_run_sequentially_and_generate_manifest_and_outputs(
    client: FlaskClient,
) -> None:
    calls: list[str] = []

    def fetch_current(accession: str) -> VersionResult:
        calls.append(f"current:{accession}")
        return _outcome(accession, 2, current=True)

    def fetch_history(accession: str, **kwargs: Any) -> VCVHistoryResult:
        calls.append(f"history:{accession}")
        assert kwargs["mode"] == "endpoints"
        assert kwargs["max_requests"] == 2
        return _history(accession, kwargs["current_result"])

    client.application.config["VCV_CURRENT_FETCHER"] = fetch_current
    client.application.config["VCV_HISTORY_FETCHER"] = fetch_history
    plan = _plan(
        client,
        [FIRST, SECOND],
        candidate_selection_rule="First two canonical fixture candidates.",
    )
    started = client.post("/api/pilot-batch/run", json={"approved": True, "plan": plan})
    assert started.status_code == 202
    operation = _poll(client, started.get_json()["operation_id"])
    assert operation["state"] == "completed", operation
    assert calls == [
        f"current:{FIRST}",
        f"history:{FIRST}",
        f"current:{SECOND}",
        f"history:{SECOND}",
    ]
    assert operation["result"]["batch_bytes"] > 0
    assert operation["result"]["output_summary"]["candidates_attempted"] == 2
    assert all("candidate" in event for event in operation["progress_events"])

    output_root = Path(client.application.config["PILOT_RESULTS_ROOT"])
    manifest = json.loads((output_root / "batch_manifest.json").read_text())
    assert manifest["candidate_selection_rule"].startswith("First two")
    assert [item["status"] for item in manifest["candidates"]] == [
        "completed",
        "completed",
    ]
    assert manifest["actual_new_batch_bytes"] == operation["result"]["batch_bytes"]
    for filename in (
        "pilot_results.csv",
        "pilot_summary.json",
        "pilot_report.md",
        "transfer_manifest.json",
        "manual_review.csv",
    ):
        assert (output_root / filename).is_file()


def test_candidate_failure_is_recorded_without_fake_history(
    client: FlaskClient,
) -> None:
    def fetch_current(accession: str) -> VersionResult:
        if accession == FIRST:
            raise OSError("fixture current failure")
        return _outcome(accession, 1, current=True)

    client.application.config["VCV_CURRENT_FETCHER"] = fetch_current
    client.application.config["VCV_HISTORY_FETCHER"] = lambda accession, **kwargs: (
        _history(accession, kwargs["current_result"])
    )
    plan = _plan(client, [FIRST, SECOND])
    started = client.post("/api/pilot-batch/run", json={"approved": True, "plan": plan})
    operation = _poll(client, started.get_json()["operation_id"])
    assert operation["state"] == "completed", operation
    assert list_histories(Path(client.application.config["VCV_HISTORY_ROOT"])) == (
        SECOND,
    )
    attempts = operation["result"]["manifest"]["candidates"]
    assert attempts[0]["status"] == "failed"
    assert "fixture current failure" in attempts[0]["failure"]
    assert attempts[1]["status"] == "completed"


def test_cancellation_reaches_core_and_saves_partial_result(
    client: FlaskClient,
) -> None:
    entered = threading.Event()

    client.application.config["VCV_CURRENT_FETCHER"] = lambda accession: _outcome(
        accession, 2, current=True
    )

    def cancellable(accession: str, **kwargs: Any) -> VCVHistoryResult:
        entered.set()
        cancel = kwargs["cancel"]
        deadline = time.monotonic() + 2
        while not cancel.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        return _history(accession, kwargs["current_result"], cancelled=True)

    client.application.config["VCV_HISTORY_FETCHER"] = cancellable
    plan = _plan(client, [FIRST, SECOND])
    started = client.post("/api/pilot-batch/run", json={"approved": True, "plan": plan})
    operation_id = started.get_json()["operation_id"]
    assert entered.wait(timeout=1)
    cancelled = client.post(f"/api/vcv-history/operations/{operation_id}/cancel")
    assert cancelled.get_json()["cancellation_requested"] is True
    operation = _poll(client, operation_id)
    assert operation["state"] == "cancelled", operation
    assert operation["result"]["manifest"]["candidates"][0]["status"] == "partial"
    assert list_histories(Path(client.application.config["VCV_HISTORY_ROOT"])) == (
        FIRST,
    )
