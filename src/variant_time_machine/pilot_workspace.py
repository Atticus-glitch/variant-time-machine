"""Validated local storage for the browser-based pilot research workspace."""

import json
import os
import shutil
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from variant_time_machine.clinvar_api import ClinVarVariant

MAX_PILOT_RECORDS = 10
MAX_WORKSPACE_BYTES = 2 * 1024 * 1024
REVIEW_STATUSES = ("unreviewed", "reviewing", "verified", "ambiguous", "excluded")
CLASSIFICATION_OPTIONS = (
    "uncertain significance",
    "pathogenic",
    "likely pathogenic",
    "benign",
    "likely benign",
    "conflicting",
    "protective",
    "risk factor",
    "drug response",
    "oncogenic",
    "likely oncogenic",
    "other",
    "unable to determine",
)
CLASSIFICATION_TYPES = (
    "germline",
    "somatic clinical impact",
    "oncogenicity",
    "other",
    "unable to determine",
)
CHECKLIST_FIELDS = (
    "identifier_confirmed",
    "gene_confirmed",
    "current_classification_confirmed",
    "historical_source_recorded",
    "release_dates_recorded",
    "classification_type_checked",
    "ambiguities_documented",
)
EDITABLE_FIELDS = (
    "selection_reason",
    "notes",
    "intended_historical_date",
    "older_release_date",
    "older_classification",
    "newer_comparison_date",
    "newer_classification",
    "historical_source_url",
    "verification_notes",
    "ambiguity_reason",
    "historical_classification_type",
    "verification_checklist",
)
_WRITE_LOCK = threading.RLock()


class PilotWorkspaceError(ValueError):
    """Raised for invalid or unsafe pilot workspace changes."""


class DuplicatePilotVariant(PilotWorkspaceError):
    """Raised when a Variation ID already exists in the pilot list."""


class PilotVariantNotFound(PilotWorkspaceError):
    """Raised when a requested pilot record does not exist."""


def empty_workspace() -> dict[str, object]:
    """Return an empty, versioned pilot workspace."""
    return {"version": 1, "updated_at_utc": "", "records": []}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: object, field: str, maximum: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PilotWorkspaceError(f"{field} must be text.")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise PilotWorkspaceError(f"{field} must be {maximum:,} characters or fewer.")
    return cleaned


def _clean_date(value: object, field: str) -> str:
    cleaned = _clean_text(value, field, 10)
    if not cleaned:
        return ""
    try:
        date.fromisoformat(cleaned)
    except ValueError as exc:
        raise PilotWorkspaceError(f"{field} must use YYYY-MM-DD.") from exc
    return cleaned


def _clean_source_url(value: object, *, required: bool = False) -> str:
    cleaned = _clean_text(value, "historical_source_url", 1000)
    if not cleaned:
        if required:
            raise PilotWorkspaceError(
                "An official historical ClinVar source URL is required."
            )
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PilotWorkspaceError("Source URLs must be complete HTTPS links.")
    hostname = parsed.hostname.casefold()
    if hostname != "ncbi.nlm.nih.gov" and not hostname.endswith(".ncbi.nlm.nih.gov"):
        raise PilotWorkspaceError(
            "Historical classification sources must use an official NCBI URL."
        )
    return cleaned


def _checklist(value: object) -> dict[str, bool]:
    if value is None:
        return {field: False for field in CHECKLIST_FIELDS}
    if not isinstance(value, dict):
        raise PilotWorkspaceError("verification_checklist must be an object.")
    if set(value).difference(CHECKLIST_FIELDS):
        raise PilotWorkspaceError("Verification checklist contains unknown items.")
    return {field: value.get(field) is True for field in CHECKLIST_FIELDS}


def _classification(value: object, field: str) -> str:
    cleaned = _clean_text(value, field, 80).casefold()
    if cleaned and cleaned not in CLASSIFICATION_OPTIONS:
        raise PilotWorkspaceError(f"Choose a listed option for {field}.")
    return cleaned


def _classification_type(value: object) -> str:
    cleaned = _clean_text(value, "historical_classification_type", 80).casefold()
    if cleaned and cleaned not in CLASSIFICATION_TYPES:
        raise PilotWorkspaceError("Choose a listed classification type.")
    return cleaned


def new_pilot_record(
    variant: ClinVarVariant,
    selection_reason: str,
    notes: str = "",
    intended_historical_date: str = "",
) -> dict[str, object]:
    """Build one unreviewed record from a current official ClinVar response."""
    reason = _clean_text(selection_reason, "selection_reason", 1000)
    if not reason:
        raise PilotWorkspaceError("Explain why this variant belongs in the pilot.")
    timestamp = _now()
    record = {
        "variant_id": variant.variation_id,
        "vcv_accession": variant.variant_identifier,
        "gene": variant.gene_name or "",
        "conditions": list(variant.associated_conditions),
        "selection_reason": reason,
        "notes": _clean_text(notes, "notes"),
        "intended_historical_date": _clean_date(
            intended_historical_date, "intended_historical_date"
        ),
        "current_classification": variant.classification or "",
        "current_review_status": variant.review_status or "",
        "current_source_url": variant.source_url,
        "current_retrieved_at_utc": variant.retrieved_at_utc,
        "current_transfer_bytes": variant.response_bytes or 0,
        "selected_date": timestamp[:10],
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "review_status": "unreviewed",
        "older_release_date": "",
        "older_classification": "",
        "newer_comparison_date": "",
        "newer_classification": "",
        "historical_source_url": "",
        "historical_classification_type": "",
        "verification_notes": "",
        "ambiguity_reason": "",
        "verification_checklist": _checklist(None),
    }
    validate_record(record)
    return record


def validate_record(record: dict[str, object]) -> None:
    """Validate stored identifiers, field types, and scientific review rules."""
    required = {
        "variant_id",
        "vcv_accession",
        "gene",
        "conditions",
        "selection_reason",
        "notes",
        "intended_historical_date",
        "current_classification",
        "current_review_status",
        "current_source_url",
        "current_retrieved_at_utc",
        "current_transfer_bytes",
        "selected_date",
        "created_at_utc",
        "updated_at_utc",
        "review_status",
        "older_release_date",
        "older_classification",
        "newer_comparison_date",
        "newer_classification",
        "historical_source_url",
        "historical_classification_type",
        "verification_notes",
        "ambiguity_reason",
        "verification_checklist",
    }
    if set(record) != required:
        raise PilotWorkspaceError(
            "Pilot record fields do not match the workspace schema."
        )
    variant_id = _clean_text(record["variant_id"], "variant_id", 20)
    if not variant_id.isdigit() or variant_id == "0":
        raise PilotWorkspaceError("variant_id must be positive numeric text.")
    accession = _clean_text(record["vcv_accession"], "vcv_accession", 30)
    if not accession.upper().startswith("VCV"):
        raise PilotWorkspaceError("vcv_accession must be a VCV accession.")
    conditions = record["conditions"]
    if not isinstance(conditions, list) or any(
        not isinstance(item, str) for item in conditions
    ):
        raise PilotWorkspaceError("conditions must be a list of text values.")
    transfer_bytes = record["current_transfer_bytes"]
    if not isinstance(transfer_bytes, int) or transfer_bytes < 0:
        raise PilotWorkspaceError(
            "current_transfer_bytes must be a nonnegative integer."
        )
    for field in (
        "gene",
        "selection_reason",
        "notes",
        "current_classification",
        "current_review_status",
        "current_source_url",
        "current_retrieved_at_utc",
        "created_at_utc",
        "updated_at_utc",
        "verification_notes",
        "ambiguity_reason",
    ):
        _clean_text(record[field], field)
    for field in (
        "selected_date",
        "intended_historical_date",
        "older_release_date",
        "newer_comparison_date",
    ):
        _clean_date(record[field], field)
    _classification(record["older_classification"], "older_classification")
    _classification(record["newer_classification"], "newer_classification")
    _classification_type(record["historical_classification_type"])
    _clean_source_url(record["historical_source_url"])
    checklist = _checklist(record["verification_checklist"])
    status = _clean_text(record["review_status"], "review_status", 20).casefold()
    if status not in REVIEW_STATUSES:
        raise PilotWorkspaceError("Unknown review status.")
    if status in {"ambiguous", "excluded"} and not _clean_text(
        record["ambiguity_reason"], "ambiguity_reason"
    ):
        raise PilotWorkspaceError(
            "A note explaining ambiguity or exclusion is required."
        )
    if status == "verified":
        missing_checks = [field for field, checked in checklist.items() if not checked]
        if missing_checks:
            raise PilotWorkspaceError(
                "Complete every verification checklist item before marking verified."
            )
        required_values = (
            record["older_release_date"],
            record["older_classification"],
            record["newer_comparison_date"],
            record["newer_classification"],
            record["historical_source_url"],
            record["historical_classification_type"],
        )
        if not all(required_values):
            raise PilotWorkspaceError(
                "Verified records require both dates, both classifications, an "
                "official source, and a checked classification type."
            )
        older = date.fromisoformat(str(record["older_release_date"]))
        newer = date.fromisoformat(str(record["newer_comparison_date"]))
        if older >= newer:
            raise PilotWorkspaceError(
                "The older release date must be before the newer comparison date."
            )


def validate_workspace(workspace: dict[str, object]) -> None:
    """Validate the complete workspace and reject duplicate identifiers."""
    if set(workspace) != {"version", "updated_at_utc", "records"}:
        raise PilotWorkspaceError("Pilot workspace fields are invalid.")
    if workspace["version"] != 1:
        raise PilotWorkspaceError("Unsupported pilot workspace version.")
    records = workspace["records"]
    if not isinstance(records, list):
        raise PilotWorkspaceError("Pilot workspace records must be a list.")
    if len(records) > MAX_PILOT_RECORDS:
        raise PilotWorkspaceError("The small pilot is limited to ten variants.")
    identifiers: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            raise PilotWorkspaceError("Each pilot record must be an object.")
        validate_record(record)
        identifiers.append(str(record["variant_id"]))
    if len(identifiers) != len(set(identifiers)):
        raise DuplicatePilotVariant("Pilot Variation IDs must be unique.")


def load_workspace(path: Path) -> dict[str, object]:
    """Load a validated workspace, creating an empty in-memory state if absent."""
    if not path.is_file():
        return empty_workspace()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PilotWorkspaceError("Pilot workspace must be a JSON object.")
    validate_workspace(payload)
    return payload


def save_workspace(path: Path, workspace: dict[str, object]) -> None:
    """Back up and atomically replace the bounded pilot workspace."""
    validate_workspace(workspace)
    content = (json.dumps(workspace, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(content) > MAX_WORKSPACE_BYTES:
        raise PilotWorkspaceError("Pilot workspace exceeds the 2 MB local limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(".backup.json")
    try:
        temporary.write_bytes(content)
        if path.is_file():
            shutil.copy2(path, backup)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mutate_workspace(path: Path, mutation: Callable[[dict[str, object]], Any]) -> Any:
    """Serialize local read-modify-write operations under one process lock."""
    with _WRITE_LOCK:
        workspace = load_workspace(path)
        result = mutation(workspace)
        workspace["updated_at_utc"] = _now()
        save_workspace(path, workspace)
        return result


def find_record(workspace: dict[str, object], variation_id: str) -> dict[str, object]:
    """Find one record by exact numeric Variation ID."""
    for record in workspace["records"]:
        if record["variant_id"] == variation_id:
            return record
    raise PilotVariantNotFound(f"Variation ID {variation_id} is not in the pilot.")


def add_record(path: Path, record: dict[str, object]) -> dict[str, object]:
    """Add one unique pilot record and return it."""
    validate_record(record)

    def add(workspace: dict[str, object]) -> dict[str, object]:
        records = workspace["records"]
        if any(item["variant_id"] == record["variant_id"] for item in records):
            raise DuplicatePilotVariant(
                f"Variation ID {record['variant_id']} is already in the pilot."
            )
        if len(records) >= MAX_PILOT_RECORDS:
            raise PilotWorkspaceError("The small pilot is limited to ten variants.")
        records.append(record)
        return record

    return mutate_workspace(path, add)


def update_record(
    path: Path,
    variation_id: str,
    changes: dict[str, object],
    *,
    status: str | None = None,
) -> dict[str, object]:
    """Update declared review fields and enforce status-specific requirements."""
    unknown = set(changes).difference(EDITABLE_FIELDS)
    if unknown:
        raise PilotWorkspaceError(
            f"Unknown editable fields: {', '.join(sorted(unknown))}"
        )

    def update(workspace: dict[str, object]) -> dict[str, object]:
        record = find_record(workspace, variation_id)
        for field, value in changes.items():
            if field == "verification_checklist":
                record[field] = _checklist(value)
            elif field in {
                "intended_historical_date",
                "older_release_date",
                "newer_comparison_date",
            }:
                record[field] = _clean_date(value, field)
            elif field in {"older_classification", "newer_classification"}:
                record[field] = _classification(value, field)
            elif field == "historical_source_url":
                record[field] = _clean_source_url(value)
            elif field == "historical_classification_type":
                record[field] = _classification_type(value)
            else:
                record[field] = _clean_text(value, field)
        if status is not None:
            record["review_status"] = status.casefold()
        record["updated_at_utc"] = _now()
        validate_record(record)
        return record

    return mutate_workspace(path, update)


def refresh_current_record(
    path: Path, variation_id: str, variant: ClinVarVariant
) -> dict[str, object]:
    """Update only current API fields without changing manual historical work."""
    if variant.variation_id != variation_id:
        raise PilotWorkspaceError("Current lookup identifier does not match the pilot.")

    def refresh(workspace: dict[str, object]) -> dict[str, object]:
        record = find_record(workspace, variation_id)
        record.update(
            {
                "vcv_accession": variant.variant_identifier,
                "gene": variant.gene_name or "",
                "conditions": list(variant.associated_conditions),
                "current_classification": variant.classification or "",
                "current_review_status": variant.review_status or "",
                "current_source_url": variant.source_url,
                "current_retrieved_at_utc": variant.retrieved_at_utc,
                "current_transfer_bytes": variant.response_bytes or 0,
                "updated_at_utc": _now(),
            }
        )
        validate_record(record)
        return record

    return mutate_workspace(path, refresh)


def timeline_for(record: dict[str, object]) -> dict[str, object]:
    """Return an honest two-point timeline without inferring absent values."""
    older_date = str(record["older_release_date"])
    older_classification = str(record["older_classification"])
    newer_date = str(record["newer_comparison_date"])
    newer_classification = str(record["newer_classification"])
    if not older_date or not older_classification:
        change = "Historical classification not yet verified."
    elif not newer_date or not newer_classification:
        change = "Newer comparison not yet recorded."
    elif "unable to determine" in {older_classification, newer_classification}:
        change = "Unable to determine"
    elif older_classification == newer_classification:
        change = "No classification change"
    else:
        change = f"Changed from {older_classification} to {newer_classification}"
    return {
        "older": {
            "date": older_date,
            "classification": older_classification,
        },
        "newer": {
            "date": newer_date,
            "classification": newer_classification,
        },
        "change_category": change,
        "verification_state": record["review_status"],
    }


def public_record(record: dict[str, object]) -> dict[str, object]:
    """Return one JSON-ready record with its calculated timeline."""
    return {**record, "timeline": timeline_for(record)}
