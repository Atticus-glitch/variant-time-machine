"""Tests for storage-aware historical release planning."""

import time
from datetime import date
from pathlib import Path

from flask.testing import FlaskClient

from variant_time_machine.config import CLINVAR_RELEASES, ClinVarRelease
from variant_time_machine.historical_dataset import (
    DiskUsage,
    historical_download_plan,
    validate_download_preflight,
)
from website.dashboard.app import create_app


def fixed_disk_usage(path: Path) -> DiskUsage:
    """Return a deterministic roomy filesystem for no-network tests."""
    return DiskUsage(80_000_000_000, 20_000_000_000, 60_000_000_000)


def small_releases() -> dict[str, ClinVarRelease]:
    """Return a tiny pair with the same metadata shape as production releases."""
    return {
        "older": ClinVarRelease(
            "older", date(2022, 1, 6), "https://example.test/older.gz", 100
        ),
        "newer": ClinVarRelease(
            "newer", date(2024, 1, 4), "https://example.test/newer.gz", 250
        ),
    }


def test_pair_plan_reports_transfer_temp_reserve_and_exact_releases(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "raw" / "clinvar"
    destination.parent.mkdir()

    plan = historical_download_plan(
        destination,
        releases=small_releases(),
        disk_usage=fixed_disk_usage,
        generated_at_utc="2026-07-28T00:00:00+00:00",
    )

    assert plan["estimated_transfer_bytes"] == 350
    assert plan["estimated_temporary_bytes"] == 250
    assert plan["safe_download_limit_bytes"] == 5_000_000_000
    assert plan["estimated_free_after_bytes"] == 59_999_999_650
    assert plan["allowed"] is True
    assert [item["release_date"] for item in plan["releases"]] == [
        "2022-01-06",
        "2024-01-04",
    ]
    validate_download_preflight(plan)


def test_pair_plan_reuses_only_exact_regular_files(tmp_path: Path) -> None:
    destination = tmp_path / "raw" / "clinvar"
    destination.mkdir(parents=True)
    (destination / "older.gz").write_bytes(b"x" * 100)

    plan = historical_download_plan(
        destination, releases=small_releases(), disk_usage=fixed_disk_usage
    )

    assert plan["estimated_transfer_bytes"] == 250
    assert plan["download_count"] == 1
    assert plan["releases"][0]["local_status"] == "ready"
    assert plan["releases"][1]["local_status"] == "missing"


def test_pair_plan_blocks_wrong_size_existing_target(tmp_path: Path) -> None:
    destination = tmp_path / "raw" / "clinvar"
    destination.mkdir(parents=True)
    (destination / "older.gz").write_bytes(b"wrong")

    plan = historical_download_plan(
        destination, releases=small_releases(), disk_usage=fixed_disk_usage
    )

    assert plan["allowed"] is False
    assert plan["releases"][0]["local_status"] == "size_mismatch"


def test_dashboard_requires_exact_approval_and_runs_mocked_pair(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw" / "clinvar"
    raw_root.parent.mkdir()
    calls: list[str] = []

    def fake_download(release, destination, **kwargs):
        assert kwargs["confirm"] is True
        calls.append(release.label)
        destination.mkdir(parents=True, exist_ok=True)
        data = destination / release.filename
        metadata = data.with_suffix(f"{data.suffix}.metadata.json")
        data.write_bytes(release.label.encode())
        metadata.write_text("{}\n", encoding="utf-8")
        return data, metadata

    app = create_app(
        {
            "TESTING": True,
            "HISTORICAL_RAW_ROOT": raw_root,
            "HISTORICAL_DISK_USAGE": fixed_disk_usage,
            "HISTORICAL_DOWNLOADER": fake_download,
            "VCV_HISTORY_ROOT": tmp_path / "histories",
            "PILOT_RESULTS_ROOT": tmp_path / "results",
        }
    )
    client: FlaskClient = app.test_client()

    assert client.get("/historical_dataset.html").status_code == 200
    planned = client.post("/api/historical-dataset/plan", json={}).get_json()
    assert planned["plan"]["estimated_transfer_bytes"] == 319_441_148
    unapproved = client.post(
        "/api/historical-dataset/run",
        json={"plan": planned["plan"], "plan_digest": planned["plan_digest"]},
    )
    assert unapproved.status_code == 428

    started = client.post(
        "/api/historical-dataset/run",
        json={
            "approved": True,
            "plan": planned["plan"],
            "plan_digest": planned["plan_digest"],
        },
    )
    assert started.status_code == 202
    operation_id = started.get_json()["operation_id"]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        operation = client.get(
            f"/api/historical-dataset/operations/{operation_id}"
        ).get_json()
        if operation["state"] != "running":
            break
        time.sleep(0.01)

    assert operation["state"] == "completed"
    assert calls == list(CLINVAR_RELEASES)
    assert operation["result"]["actual_bytes"] == len("older") + len("newer")
