"""Safe, bounded local artifact storage for VCV history review.

The writer lock gives cooperating readers a consistent set. Each file replacement is
crash-atomic, but a process failure can still interrupt a multi-file save.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from variant_time_machine.vcv_history import (
    MAX_RESPONSE_BYTES,
    MAX_TOTAL_BYTES,
    VCVHistoryResult,
    validate_vcv_accession,
)

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_REVIEW_BYTES = 1024 * 1024
MAX_TREE_BYTES = MAX_TOTAL_BYTES + (4 * MAX_JSON_BYTES) + MAX_REVIEW_BYTES
REVIEW_STATUSES = (
    "unreviewed",
    "needs_review",
    "ambiguous",
    "manually_verified",
    "excluded",
)
VERIFICATION_REQUIREMENTS = (
    "VCV identity confirmed",
    "Variation ID confirmed",
    "gene confirmed",
    "classification type confirmed",
    "old and new versions recorded",
    "relevant dates recorded",
    "official source requests recorded",
    "classification change manually checked",
    "missing/conflicting information documented",
    "versions-vs-monthly-snapshots limitation acknowledged",
)
_GERMLINE_CHANGE_VALUES = frozenset(
    {
        "VUS_to_Pathogenic",
        "VUS_to_Likely_Pathogenic",
        "VUS_to_Benign",
        "VUS_to_Likely_Benign",
        "Pathogenic_to_VUS",
        "Benign_to_VUS",
        "Became_Conflicting",
        "Conflict_Resolved",
        "Other_Germline_Change",
    }
)

_WRITE_LOCK = threading.RLock()
_EVIDENCE_CHANGED_NOTE = (
    "Automatic evidence changed; manual verification must be repeated."
)
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "accession",
        "status",
        "reviewer_decision",
        "notes",
        "manual_corrections",
        "automatic_artifact_digest",
        "verification",
        "sources",
        "created_at_utc",
        "updated_at_utc",
    }
)
_LEGACY_REVIEW_FIELDS = _REVIEW_FIELDS - {"automatic_artifact_digest"}
_LEGACY_DIGEST_SENTINEL = "0" * 64

ReviewStatus = Literal[
    "unreviewed",
    "needs_review",
    "ambiguous",
    "manually_verified",
    "excluded",
]


class VCVHistoryStoreError(ValueError):
    """Raised when a local history artifact is invalid or unsafe."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _root_path(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("VCV history root must be supplied as a pathlib.Path.")
    return root


def _base_accession(identifier: str, *, allow_version: bool = False) -> str:
    try:
        parsed = validate_vcv_accession(identifier)
    except (TypeError, ValueError) as exc:
        raise VCVHistoryStoreError(str(exc)) from exc
    if parsed.version is not None and not allow_version:
        raise VCVHistoryStoreError(
            "Storage helpers require an unversioned VCV accession."
        )
    return parsed.accession


def _accession_dir(root: Path, accession: str) -> Path:
    root = _root_path(root)
    canonical = _base_accession(accession)
    path = root / canonical
    if path.is_symlink():
        raise VCVHistoryStoreError(
            "VCV accession directories cannot be symbolic links."
        )
    return path


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    root = _root_path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".vcv_history.lock"
    if lock_path.is_symlink():
        raise VCVHistoryStoreError("The VCV history lock cannot be a symbolic link.")
    with _WRITE_LOCK, lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise VCVHistoryStoreError("Stored values must be JSON serializable.") from exc


def _atomic_write(path: Path, content: bytes, *, maximum: int) -> None:
    if len(content) > maximum:
        raise VCVHistoryStoreError(
            f"{path.name} exceeds its {maximum:,}-byte local storage limit."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path, *, maximum: int = MAX_JSON_BYTES) -> Any:
    if path.is_symlink():
        raise VCVHistoryStoreError(f"Refusing to read symbolic link {path.name}.")
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise VCVHistoryStoreError(
            f"Missing VCV history artifact: {path.name}."
        ) from exc
    if size > maximum:
        raise VCVHistoryStoreError(f"{path.name} exceeds its local storage limit.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VCVHistoryStoreError(f"Invalid JSON artifact: {path.name}.") from exc


def _without_xml(result: object) -> dict[str, object]:
    value = result.to_dict()  # type: ignore[attr-defined]
    value.pop("raw_xml", None)
    return value


def _empty_review(
    accession: str,
    automatic_artifact_digest: str,
    timestamp: str | None = None,
) -> dict[str, object]:
    created = timestamp or _now()
    return {
        "schema_version": 1,
        "accession": accession,
        "status": "unreviewed",
        "reviewer_decision": "",
        "notes": "",
        "manual_corrections": {},
        "automatic_artifact_digest": automatic_artifact_digest,
        "verification": {item: False for item in VERIFICATION_REQUIREMENTS},
        "sources": [],
        "created_at_utc": created,
        "updated_at_utc": created,
    }


def _clean_text(value: object, field: str, maximum: int = 20_000) -> str:
    if not isinstance(value, str):
        raise VCVHistoryStoreError(f"{field} must be text.")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise VCVHistoryStoreError(f"{field} is too long.")
    return cleaned


def _validate_review(review: object, accession: str) -> dict[str, object]:
    if not isinstance(review, dict):
        raise VCVHistoryStoreError("Review must be a JSON object.")
    if set(review) != _REVIEW_FIELDS or review["schema_version"] != 1:
        raise VCVHistoryStoreError("Review fields do not match schema version 1.")
    if review["accession"] != accession:
        raise VCVHistoryStoreError("Review accession does not match its directory.")
    status = review["status"]
    if status not in REVIEW_STATUSES:
        raise VCVHistoryStoreError("Unknown VCV review status.")
    notes = _clean_text(review["notes"], "notes")
    _clean_text(review["reviewer_decision"], "reviewer_decision", 4_000)
    _clean_text(review["created_at_utc"], "created_at_utc", 100)
    _clean_text(review["updated_at_utc"], "updated_at_utc", 100)
    corrections = review["manual_corrections"]
    if not isinstance(corrections, dict) or any(
        not isinstance(key, str) or len(key) > 200 for key in corrections
    ):
        raise VCVHistoryStoreError(
            "manual_corrections must be an object with text keys."
        )
    digest = _clean_text(
        review["automatic_artifact_digest"], "automatic_artifact_digest", 64
    )
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise VCVHistoryStoreError(
            "automatic_artifact_digest must be a SHA-256 digest."
        )
    verification = review["verification"]
    if not isinstance(verification, dict) or set(verification) != set(
        VERIFICATION_REQUIREMENTS
    ):
        raise VCVHistoryStoreError("Review verification requirements are invalid.")
    if any(type(value) is not bool for value in verification.values()):
        raise VCVHistoryStoreError("Every verification value must be boolean.")
    sources = review["sources"]
    if not isinstance(sources, list) or len(sources) > 100:
        raise VCVHistoryStoreError("sources must be a list of at most 100 entries.")
    for source in sources:
        _clean_text(source, "source", 2_000)
    if status in {"ambiguous", "excluded"} and not notes:
        raise VCVHistoryStoreError("Ambiguous and excluded reviews require a note.")
    if status == "manually_verified" and not all(verification.values()):
        raise VCVHistoryStoreError(
            "Every verification requirement is required for manually_verified."
        )
    if len(_json_bytes(review)) > MAX_REVIEW_BYTES:
        raise VCVHistoryStoreError("review.json exceeds its local storage limit.")
    return review


def _load_review_for_save_unlocked(
    root: Path, accession: str
) -> tuple[dict[str, object], bool]:
    path = _accession_dir(root, accession) / "review.json"
    payload = _read_json(path, maximum=MAX_REVIEW_BYTES)
    legacy = (
        isinstance(payload, dict)
        and set(payload) == _LEGACY_REVIEW_FIELDS
        and payload.get("schema_version") == 1
    )
    if legacy:
        payload = {**payload, "automatic_artifact_digest": _LEGACY_DIGEST_SENTINEL}
    return _validate_review(payload, accession), legacy


def _directory_bytes(path: Path, replacing: set[Path] | None = None) -> int:
    if not path.exists():
        return 0
    total = 0
    replacing = replacing or set()
    for item in path.rglob("*"):
        if item.is_symlink():
            raise VCVHistoryStoreError(
                "Symbolic links are not allowed in history trees."
            )
        if item.is_file() and item not in replacing:
            total += item.stat().st_size
            if total > MAX_TREE_BYTES:
                raise VCVHistoryStoreError(
                    "VCV history tree exceeds its storage limit."
                )
    return total


def _automatic_artifact_digest(directory: Path, payloads: Mapping[Path, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        payloads, key=lambda item: item.relative_to(directory).as_posix()
    ):
        name = path.relative_to(directory).as_posix().encode("utf-8")
        content = payloads[path]
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _stale_raw_files(directory: Path, expected: set[Path]) -> set[Path]:
    raw_directory = directory / "raw"
    if raw_directory.is_symlink():
        raise VCVHistoryStoreError("The raw XML directory cannot be a symbolic link.")
    if not raw_directory.exists():
        return set()
    stale: set[Path] = set()
    for item in raw_directory.iterdir():
        if item.is_symlink():
            raise VCVHistoryStoreError("Raw XML artifacts cannot be symbolic links.")
        if item.is_file() and item.suffix == ".xml" and item not in expected:
            stale.add(item)
    return stale


def save_history(
    root: Path,
    result: VCVHistoryResult,
    *,
    app_version: str,
    git_commit: str,
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Atomically save bounded automatic artifacts while preserving review data."""
    accession = _base_accession(result.requested_accession, allow_version=True)
    directory = _accession_dir(root, accession)
    responses = (result.current_result, *result.results)
    raw_files: dict[Path, bytes] = {}
    response_sizes: dict[str, int] = {}
    retrieval_timestamps: dict[str, str] = {}
    source_requests: list[dict[str, object]] = []
    collected_warnings = [*warnings, *result.summary.unresolved_warnings]
    for response in responses:
        parsed = validate_vcv_accession(response.requested_identifier)
        if parsed.accession != accession:
            raise VCVHistoryStoreError(
                "A response belongs to a different VCV accession."
            )
        identifier = parsed.identifier
        if response.response_bytes < 0 or response.response_bytes > MAX_RESPONSE_BYTES:
            raise VCVHistoryStoreError(
                "A response size exceeds the per-response limit."
            )
        response_sizes[identifier] = response.response_bytes
        retrieval_timestamps[identifier] = response.retrieved_at_utc
        source_requests.append(
            {
                "identifier": identifier,
                "request": response.source_request,
                "retrieved_at_utc": response.retrieved_at_utc,
                "response_bytes": response.response_bytes,
                "status": response.status,
                "message": response.message,
            }
        )
        if response.message:
            collected_warnings.append(response.message)
        if response.record:
            collected_warnings.extend(response.record.warnings)
        if response.raw_xml is not None:
            content = response.raw_xml.encode("utf-8")
            if len(content) > MAX_RESPONSE_BYTES:
                raise VCVHistoryStoreError(
                    "A raw XML artifact exceeds the response limit."
                )
            raw_files[directory / "raw" / f"{identifier}.xml"] = content

    if result.total_response_bytes < 0 or result.total_response_bytes > MAX_TOTAL_BYTES:
        raise VCVHistoryStoreError("Total response bytes exceed the retrieval limit.")
    metadata = {
        "schema_version": 1,
        "requested_accession": result.requested_accession,
        "current_identifier": result.current_identifier,
        "version_plan": list(result.version_plan),
        "current_result": _without_xml(result.current_result),
        "summary": result.summary.to_dict(),
        "total_response_bytes": result.total_response_bytes,
        "cancelled": result.cancelled,
    }
    versions = {
        "schema_version": 1,
        "accession": accession,
        "versions": [_without_xml(item) for item in result.results],
    }
    comparisons = {
        "schema_version": 1,
        "accession": accession,
        "comparisons": [item.to_dict() for item in result.comparisons],
    }
    automatic_payloads = {
        directory / "metadata.json": _json_bytes(metadata),
        directory / "versions.json": _json_bytes(versions),
        directory / "comparisons.json": _json_bytes(comparisons),
        **raw_files,
    }
    automatic_digest = _automatic_artifact_digest(directory, automatic_payloads)

    with _locked(root):
        directory = _accession_dir(root, accession)
        review_path = directory / "review.json"
        if review_path.exists():
            review, legacy_review = _load_review_for_save_unlocked(root, accession)
            write_review = (
                legacy_review or review["automatic_artifact_digest"] != automatic_digest
            )
            if write_review:
                existing_notes = str(review["notes"])
                if _EVIDENCE_CHANGED_NOTE not in existing_notes:
                    review["notes"] = "\n\n".join(
                        item
                        for item in (existing_notes, _EVIDENCE_CHANGED_NOTE)
                        if item
                    )
                review["status"] = "needs_review"
                review["reviewer_decision"] = ""
                review["verification"] = {
                    item: False for item in VERIFICATION_REQUIREMENTS
                }
                review["automatic_artifact_digest"] = automatic_digest
                review["updated_at_utc"] = _now()
                _validate_review(review, accession)
        else:
            review = _empty_review(accession, automatic_digest)
            write_review = True
        manifest = {
            "schema_version": 1,
            "accession": accession,
            "source_requests": source_requests,
            "response_sizes": response_sizes,
            "total_bytes": result.total_response_bytes,
            "retrieval_timestamps": retrieval_timestamps,
            "app_version": _clean_text(app_version, "app_version", 200),
            "git_commit": _clean_text(git_commit, "git_commit", 200),
            "automatic_artifact_digest": automatic_digest,
            "warnings": list(
                dict.fromkeys(
                    _clean_text(item, "warning") for item in collected_warnings
                )
            ),
            "manual_verification": review["status"] == "manually_verified",
        }
        payloads = {
            **automatic_payloads,
            directory / "manifest.json": _json_bytes(manifest),
        }
        if write_review:
            payloads[review_path] = _json_bytes(review)
        for path, content in payloads.items():
            maximum = MAX_RESPONSE_BYTES if path.suffix == ".xml" else MAX_JSON_BYTES
            if path.name == "review.json":
                maximum = MAX_REVIEW_BYTES
            if len(content) > maximum:
                raise VCVHistoryStoreError(f"{path.name} exceeds its storage limit.")
        stale_raw_files = _stale_raw_files(directory, set(raw_files))
        replacing = {path for path in payloads if path.exists()} | stale_raw_files
        projected = _directory_bytes(directory, replacing) + sum(
            len(content) for content in payloads.values()
        )
        if projected > MAX_TREE_BYTES:
            raise VCVHistoryStoreError("VCV history tree exceeds its storage limit.")
        for path, content in payloads.items():
            maximum = MAX_RESPONSE_BYTES if path.suffix == ".xml" else MAX_JSON_BYTES
            if path.name == "review.json":
                maximum = MAX_REVIEW_BYTES
            _atomic_write(path, content, maximum=maximum)
        for path in stale_raw_files:
            path.unlink()
    return manifest


def list_histories(root: Path) -> tuple[str, ...]:
    """List canonical accession directories containing a complete manifest."""
    root = _root_path(root)
    if not root.exists():
        return ()
    histories: list[str] = []
    for item in root.iterdir():
        if not item.is_dir() or item.is_symlink():
            continue
        try:
            accession = _base_accession(item.name)
        except VCVHistoryStoreError:
            continue
        if (item / "manifest.json").is_file():
            histories.append(accession)
    return tuple(sorted(histories))


def _load_review_unlocked(root: Path, accession: str) -> dict[str, object]:
    canonical = _base_accession(accession)
    path = _accession_dir(root, canonical) / "review.json"
    return _validate_review(_read_json(path, maximum=MAX_REVIEW_BYTES), canonical)


def _load_history_unlocked(root: Path, accession: str) -> dict[str, object]:
    directory = _accession_dir(root, accession)
    return {
        "metadata": _read_json(directory / "metadata.json"),
        "versions": _read_json(directory / "versions.json"),
        "comparisons": _read_json(directory / "comparisons.json"),
        "manifest": _read_json(directory / "manifest.json"),
        "review": _load_review_unlocked(root, accession),
    }


def load_history(root: Path, accession: str) -> dict[str, object]:
    """Load one consistent artifact set under the same lock used by writers."""
    canonical = _base_accession(accession)
    with _locked(root):
        return _load_history_unlocked(root, canonical)


def load_review(root: Path, accession: str) -> dict[str, object]:
    """Load and validate review data without applying corrections to parsed data."""
    canonical = _base_accession(accession)
    with _locked(root):
        return _load_review_unlocked(root, canonical)


def update_review(
    root: Path,
    accession: str,
    *,
    status: ReviewStatus | None = None,
    reviewer_decision: str | None = None,
    notes: str | None = None,
    manual_corrections: Mapping[str, object] | None = None,
    verification: Mapping[str, bool] | None = None,
    sources: Sequence[str] | None = None,
) -> dict[str, object]:
    """Update manual review fields, leaving every automatic artifact unchanged."""
    canonical = _base_accession(accession)
    with _locked(root):
        directory = _accession_dir(root, canonical)
        review_path = directory / "review.json"
        review = _load_review_unlocked(root, canonical)
        if status is not None:
            review["status"] = status
        if reviewer_decision is not None:
            review["reviewer_decision"] = reviewer_decision
        if notes is not None:
            review["notes"] = notes
        if manual_corrections is not None:
            if not isinstance(manual_corrections, Mapping):
                raise VCVHistoryStoreError("manual_corrections must be an object.")
            current = dict(review["manual_corrections"])
            current.update(manual_corrections)
            review["manual_corrections"] = current
        if verification is not None:
            unknown = set(verification).difference(VERIFICATION_REQUIREMENTS)
            if unknown:
                raise VCVHistoryStoreError("Unknown verification requirement.")
            current_checks = dict(review["verification"])
            current_checks.update(verification)
            review["verification"] = current_checks
        if sources is not None:
            review["sources"] = list(sources)
        review["updated_at_utc"] = _now()
        validated = _validate_review(review, canonical)
        _atomic_write(review_path, _json_bytes(validated), maximum=MAX_REVIEW_BYTES)

        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
            if not isinstance(manifest, dict):
                raise VCVHistoryStoreError("manifest.json must contain an object.")
            manifest["manual_verification"] = validated["status"] == "manually_verified"
            _atomic_write(manifest_path, _json_bytes(manifest), maximum=MAX_JSON_BYTES)
        return validated


def progress_metrics(root: Path) -> dict[str, int | str]:
    """Aggregate compact progress and disk-use metrics across saved histories."""
    histories = list_histories(root)
    version_count = 0
    changed_count = 0
    verified_count = 0
    total_bytes = 0
    for accession in histories:
        directory = _accession_dir(root, accession)
        history = load_history(root, accession)
        versions = history["versions"]
        comparisons = history["comparisons"]
        review = history["review"]
        if not isinstance(versions, dict) or not isinstance(
            versions.get("versions"), list
        ):
            raise VCVHistoryStoreError("versions.json has an invalid shape.")
        if not isinstance(comparisons, dict) or not isinstance(
            comparisons.get("comparisons"), list
        ):
            raise VCVHistoryStoreError("comparisons.json has an invalid shape.")
        version_count += len(versions["versions"])
        if any(
            isinstance(item, dict)
            and item.get("detected_classification_change") in _GERMLINE_CHANGE_VALUES
            for item in comparisons["comparisons"]
        ):
            changed_count += 1
        if review["status"] == "manually_verified":
            verified_count += 1
        total_bytes += _directory_bytes(directory)
    return {
        "histories": len(histories),
        "versions": version_count,
        "changed_histories": changed_count,
        "verified": verified_count,
        "bytes": total_bytes,
        "storage": _format_bytes(total_bytes),
    }


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")
