"""One manually selected ClinVar pilot record and its local persistence."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from variant_time_machine.clinvar_api import CLINVAR_ESUMMARY_URL, ClinVarVariant

PILOT_RECORD_FIELDS = (
    "variant_id",
    "vcv_accession",
    "gene",
    "selected_date",
    "selection_reason",
    "current_classification",
    "current_review_status",
    "conditions",
    "historical_records_found",
    "verification_status",
    "notes",
    "sources",
)
PILOT_RECORD_MAX_BYTES = 1024 * 1024


def empty_pilot_record() -> dict[str, object]:
    """Return the declared record shape without scientific values."""
    return {
        "variant_id": "",
        "vcv_accession": "",
        "gene": "",
        "selected_date": "",
        "selection_reason": "",
        "current_classification": "",
        "current_review_status": "",
        "conditions": [],
        "historical_records_found": [],
        "verification_status": "",
        "notes": "",
        "sources": [],
    }


def validate_pilot_record(record: dict[str, object]) -> None:
    """Reject malformed records before they reach the dashboard."""
    if len(record) != len(PILOT_RECORD_FIELDS) or set(record) != set(
        PILOT_RECORD_FIELDS
    ):
        raise ValueError("Pilot record fields do not match the declared schema.")
    variant_id = record["variant_id"]
    if not isinstance(variant_id, str) or (variant_id and not variant_id.isdigit()):
        raise ValueError("Pilot variant_id must be empty or numeric text.")
    accession = record["vcv_accession"]
    if not isinstance(accession, str) or (
        accession and not re.fullmatch(r"VCV\d{9}(?:\.\d+)?", accession)
    ):
        raise ValueError("Pilot vcv_accession is invalid.")
    for field in ("conditions", "historical_records_found", "sources"):
        value = record[field]
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError(f"Pilot {field} must be a list of text values.")
    for field in set(PILOT_RECORD_FIELDS).difference(
        {"conditions", "historical_records_found", "sources"}
    ):
        if not isinstance(record[field], str):
            raise ValueError(f"Pilot {field} must be text.")


def load_pilot_record(path: Path) -> dict[str, object]:
    """Load and validate the current single-variant pilot record."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Pilot record must be a JSON object.")
    validate_pilot_record(payload)
    return payload


def build_pilot_record(
    variant: ClinVarVariant, selection_reason: str
) -> dict[str, object]:
    """Create a current-data record with historical work clearly pending."""
    reason = selection_reason.strip()
    if not reason:
        raise ValueError("A selection reason is required.")
    esummary_source = (
        f"{CLINVAR_ESUMMARY_URL}?db=clinvar&id={variant.variation_id}&retmode=json"
    )
    record = {
        "variant_id": variant.variation_id,
        "vcv_accession": variant.variant_identifier,
        "gene": variant.gene_name or "",
        "selected_date": datetime.now(UTC).date().isoformat(),
        "selection_reason": reason,
        "current_classification": variant.classification or "",
        "current_review_status": variant.review_status or "",
        "conditions": list(variant.associated_conditions),
        "historical_records_found": [],
        "verification_status": (
            "Current ClinVar record retrieved; manual historical verification pending"
        ),
        "notes": "Selected pilot example only; not a scientific conclusion.",
        "sources": [esummary_source, variant.source_url],
    }
    validate_pilot_record(record)
    return record


def save_pilot_record(path: Path, record: dict[str, object]) -> None:
    """Atomically save one bounded pilot record."""
    validate_pilot_record(record)
    content = (json.dumps(record, indent=2, sort_keys=False) + "\n").encode("utf-8")
    if len(content) > PILOT_RECORD_MAX_BYTES:
        raise ValueError("Pilot record exceeds the 1 MB local file limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
