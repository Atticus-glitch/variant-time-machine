"""Storage-aware planning for the fixed historical ClinVar release pair."""

import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from variant_time_machine.config import (
    CLINVAR_RELEASES,
    HISTORICAL_DOWNLOAD_LIMIT_BYTES,
    HISTORICAL_FREE_SPACE_FRACTION,
    HISTORICAL_MINIMUM_FREE_BYTES,
    ClinVarRelease,
)


class DiskUsage(NamedTuple):
    """Filesystem capacity values used by the planner."""

    total: int
    used: int
    free: int


def _existing_file_status(path: Path, expected_size: int) -> tuple[str, int]:
    """Classify a local target without treating a wrong-size file as reusable."""
    if not path.exists():
        return "missing", 0
    if path.is_symlink() or not path.is_file():
        return "unsafe_existing_target", 0
    size = path.stat().st_size
    if size != expected_size:
        return "size_mismatch", size
    return "ready", size


def historical_download_plan(
    destination_dir: Path,
    *,
    releases: Mapping[str, ClinVarRelease] = CLINVAR_RELEASES,
    disk_usage: Callable[[Path], DiskUsage] = shutil.disk_usage,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a no-network transfer and storage plan for configured releases."""
    destination_dir = Path(destination_dir).resolve()
    disk = disk_usage(destination_dir.parent)
    release_rows: list[dict[str, Any]] = []
    required_bytes = 0
    largest_partial_bytes = 0
    blocking_targets: list[str] = []

    for role, release in releases.items():
        if release.expected_size_bytes is None:
            raise ValueError(f"Configured size is required for {release.filename}.")
        target = destination_dir / release.filename
        status, local_size = _existing_file_status(target, release.expected_size_bytes)
        needs_download = status == "missing"
        if needs_download:
            required_bytes += release.expected_size_bytes
            largest_partial_bytes = max(
                largest_partial_bytes, release.expected_size_bytes
            )
        elif status != "ready":
            blocking_targets.append(str(target))
        release_rows.append(
            {
                "role": role,
                "release_date": release.release_date.isoformat(),
                "source_url": release.source_url,
                "filename": release.filename,
                "expected_size_bytes": release.expected_size_bytes,
                "local_path": str(target),
                "local_status": status,
                "local_size_bytes": local_size,
                "download_required": needs_download,
            }
        )

    fraction_limit = int(disk.free * HISTORICAL_FREE_SPACE_FRACTION)
    reserve_limit = max(0, disk.free - HISTORICAL_MINIMUM_FREE_BYTES)
    safe_download_limit = min(
        HISTORICAL_DOWNLOAD_LIMIT_BYTES,
        fraction_limit,
        reserve_limit,
    )
    free_after = disk.free - required_bytes
    allowed = not blocking_targets and required_bytes <= safe_download_limit
    if blocking_targets:
        reason = "Existing targets are unsafe or do not match configured sizes."
    elif required_bytes > safe_download_limit:
        reason = "The required transfer exceeds the current automatic safety limit."
    elif required_bytes == 0:
        reason = "Both configured release files are already present at expected sizes."
    else:
        reason = "The transfer fits the current storage and download safety limits."

    return {
        "schema_version": 1,
        "generated_at_utc": generated_at_utc or datetime.now(UTC).isoformat(),
        "dataset": "ClinVar archived variant_summary release pair",
        "format": "gzip-compressed tab-separated variant_summary",
        "purpose": (
            "Match variants classified as uncertain in the older release to their "
            "records in the newer release"
        ),
        "destination_dir": str(destination_dir),
        "releases": release_rows,
        "release_count": len(release_rows),
        "download_count": sum(row["download_required"] for row in release_rows),
        "estimated_transfer_bytes": required_bytes,
        "estimated_temporary_bytes": largest_partial_bytes,
        "estimated_additional_storage_bytes": required_bytes,
        "disk_total_bytes": disk.total,
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
        "estimated_free_after_bytes": free_after,
        "minimum_free_reserve_bytes": HISTORICAL_MINIMUM_FREE_BYTES,
        "configured_download_ceiling_bytes": HISTORICAL_DOWNLOAD_LIMIT_BYTES,
        "free_space_fraction_limit_bytes": fraction_limit,
        "safe_download_limit_bytes": safe_download_limit,
        "blocking_targets": blocking_targets,
        "allowed": allowed,
        "decision_reason": reason,
        "requires_approval": required_bytes > 0,
        "confirmation": (
            "I approve these exact sequential official ClinVar archive downloads."
        ),
    }


def validate_download_preflight(plan: Mapping[str, Any]) -> None:
    """Reject a transfer plan that is blocked or cannot preserve its reserve."""
    if not plan.get("allowed"):
        raise ValueError(str(plan.get("decision_reason", "Download plan is blocked.")))
    if int(plan.get("estimated_free_after_bytes", -1)) < int(
        plan.get("minimum_free_reserve_bytes", HISTORICAL_MINIMUM_FREE_BYTES)
    ):
        raise ValueError("The planned download would violate the free-space reserve.")
