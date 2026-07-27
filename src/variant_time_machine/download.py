"""Explicit, provenance-recorded ClinVar downloads."""

import hashlib
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

from variant_time_machine.config import (
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_TIMEOUT_SECONDS,
    LARGE_DOWNLOAD_THRESHOLD_BYTES,
    RAW_DATA_DIR,
    ClinVarRelease,
)

LOGGER = logging.getLogger(__name__)


class DownloadConfirmationRequired(ValueError):
    """Raised before a transfer when the user has not confirmed its plan."""


def transfer_plan_message(
    source_url: str,
    estimated_size_bytes: int | None,
    reason: str,
) -> str:
    """Describe source, estimated size, purpose, and the 500 MB safety boundary."""
    size = (
        f"{estimated_size_bytes:,} bytes ({estimated_size_bytes / 1_000_000:.1f} MB)"
        if estimated_size_bytes is not None
        else "unknown"
    )
    protection = (
        "This exceeds the 500 MB large-download limit."
        if estimated_size_bytes is None
        or estimated_size_bytes > LARGE_DOWNLOAD_THRESHOLD_BYTES
        else "This is below the 500 MB large-download limit."
    )
    return (
        f"Source: {source_url}\n"
        f"Estimated size: {size}\n"
        f"Why needed: {reason}\n"
        f"Large download protection: ON. {protection}"
    )


def require_transfer_confirmation(
    source_url: str,
    estimated_size_bytes: int | None,
    reason: str,
    *,
    confirmed: bool,
) -> None:
    """Show the transfer plan and fail before network access unless confirmed."""
    message = transfer_plan_message(source_url, estimated_size_bytes, reason)
    LOGGER.warning("Transfer plan:\n%s", message)
    if not confirmed:
        raise DownloadConfirmationRequired(
            f"{message}\nTransfer not started. Explicit confirmation is required."
        )


@dataclass(frozen=True)
class DownloadMetadata:
    """Provenance recorded for one downloaded archive file."""

    source_url: str
    release_date: str
    retrieval_date_utc: str
    filename: str
    size_bytes: int
    checksum_algorithm: str
    checksum: str
    expected_size_bytes: int | None
    expected_sha256: str | None


def download_clinvar_release(
    release: ClinVarRelease,
    destination_dir: Path = RAW_DATA_DIR,
    *,
    confirm: bool = False,
    overwrite: bool = False,
    reason: str = "Create a fixed historical ClinVar summary snapshot",
) -> tuple[Path, Path]:
    """Download one configured release and write a JSON provenance record.

    The caller must set ``confirm=True`` so importing this module or accidentally
    calling the function cannot start a large download. The returned paths point to
    the downloaded file and its metadata sidecar.
    """
    require_transfer_confirmation(
        release.source_url,
        release.expected_size_bytes,
        reason,
        confirmed=confirm,
    )

    destination_dir = Path(destination_dir).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_path = destination_dir / release.filename
    metadata_path = output_path.with_suffix(f"{output_path.suffix}.metadata.json")
    partial_path = output_path.with_suffix(f"{output_path.suffix}.part")
    metadata_partial_path = metadata_path.with_suffix(f"{metadata_path.suffix}.part")

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Download target already exists: {output_path}. Use overwrite=True "
            "only after checking the existing file."
        )

    digest = hashlib.sha256()
    size_bytes = 0
    LOGGER.info("Downloading %s", release.source_url)

    try:
        with requests.get(
            release.source_url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            with partial_path.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    output_file.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
    except (OSError, requests.RequestException) as exc:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"ClinVar download failed for {release.source_url}: {exc}"
        ) from exc

    checksum = digest.hexdigest()
    if release.expected_size_bytes is not None and (
        size_bytes != release.expected_size_bytes
    ):
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded size {size_bytes} does not match the configured official "
            f"size {release.expected_size_bytes} for {release.filename}."
        )
    if release.expected_sha256 is not None and checksum != release.expected_sha256:
        partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded SHA-256 does not match the configured checksum for "
            f"{release.filename}."
        )

    metadata = DownloadMetadata(
        source_url=release.source_url,
        release_date=release.release_date.isoformat(),
        retrieval_date_utc=datetime.now(UTC).isoformat(),
        filename=output_path.name,
        size_bytes=size_bytes,
        checksum_algorithm="sha256",
        checksum=checksum,
        expected_size_bytes=release.expected_size_bytes,
        expected_sha256=release.expected_sha256,
    )
    backup_suffix = f".backup-{uuid.uuid4().hex}"
    output_backup = output_path.with_name(output_path.name + backup_suffix)
    metadata_backup = metadata_path.with_name(metadata_path.name + backup_suffix)
    output_existed_before = output_path.exists()
    metadata_existed_before = metadata_path.exists()
    output_was_backed_up = False
    metadata_was_backed_up = False
    try:
        metadata_partial_path.write_text(
            json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output_path.exists():
            output_path.replace(output_backup)
            output_was_backed_up = True
        if metadata_path.exists():
            metadata_path.replace(metadata_backup)
            metadata_was_backed_up = True
        partial_path.replace(output_path)
        metadata_partial_path.replace(metadata_path)
    except OSError as exc:
        if output_was_backed_up or not output_existed_before:
            output_path.unlink(missing_ok=True)
        if metadata_was_backed_up or not metadata_existed_before:
            metadata_path.unlink(missing_ok=True)
        if output_was_backed_up:
            output_backup.replace(output_path)
        if metadata_was_backed_up:
            metadata_backup.replace(metadata_path)
        partial_path.unlink(missing_ok=True)
        metadata_partial_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not finalize ClinVar data and metadata files: {exc}"
        ) from exc
    else:
        output_backup.unlink(missing_ok=True)
        metadata_backup.unlink(missing_ok=True)
    LOGGER.info("Saved %s bytes to %s", size_bytes, output_path)
    LOGGER.info("Saved provenance metadata to %s", metadata_path)
    return output_path, metadata_path
