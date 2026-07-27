"""Tests for validated, atomic Pilot Workspace storage."""

import json
from pathlib import Path

import pytest

from variant_time_machine.clinvar_api import ClinVarVariant
from variant_time_machine.pilot_workspace import (
    CHECKLIST_FIELDS,
    DuplicatePilotVariant,
    PilotWorkspaceError,
    add_record,
    empty_workspace,
    load_workspace,
    new_pilot_record,
    public_record,
    save_workspace,
    update_record,
)


def _variant() -> ClinVarVariant:
    return ClinVarVariant(
        variant_identifier="VCV000014206.2",
        variation_id="14206",
        gene_name="CCL2",
        classification="Uncertain significance",
        associated_conditions=("Test condition",),
        review_status="criteria provided, single submitter",
        evidence_summary=None,
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
        response_bytes=321,
    )


def _workspace_with_record(path: Path) -> None:
    save_workspace(path, empty_workspace())
    add_record(path, new_pilot_record(_variant(), "Clear workflow test"))


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
        "verification_notes": "Checked the identifier, scope, dates, and source.",
        "verification_checklist": {field: True for field in CHECKLIST_FIELDS},
    }


def test_add_prevents_duplicates_and_preserves_current_wording(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    save_workspace(path, empty_workspace())
    record = new_pilot_record(_variant(), "Clear workflow test")
    add_record(path, record)
    with pytest.raises(DuplicatePilotVariant):
        add_record(path, record)
    stored = load_workspace(path)["records"][0]
    assert stored["current_classification"] == "Uncertain significance"
    assert stored["older_classification"] == ""
    assert stored["review_status"] == "unreviewed"


def test_mutation_creates_backup_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    update_record(path, "14206", {"notes": "A saved note"})
    backup = path.with_suffix(".backup.json")
    assert backup.is_file()
    assert not path.with_suffix(".json.tmp").exists()
    assert load_workspace(path)["records"][0]["notes"] == "A saved note"
    assert json.loads(backup.read_text(encoding="utf-8"))["records"]


@pytest.mark.parametrize("status", ["ambiguous", "excluded"])
def test_ambiguous_and_excluded_require_explanation(
    tmp_path: Path, status: str
) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    with pytest.raises(PilotWorkspaceError, match="explaining"):
        update_record(path, "14206", {}, status=status)
    updated = update_record(
        path,
        "14206",
        {"ambiguity_reason": "Condition scope could not be matched."},
        status=status,
    )
    assert updated["review_status"] == status


def test_verification_requires_complete_checklist_and_historical_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    with pytest.raises(PilotWorkspaceError, match="checklist"):
        update_record(path, "14206", {}, status="verified")
    verified = update_record(path, "14206", _verified_changes(), status="verified")
    assert verified["review_status"] == "verified"
    assert verified["older_classification"] == "uncertain significance"
    assert verified["newer_classification"] == "protective"
    assert verified["historical_classification_type"] == "germline"


def test_classification_categories_remain_separate(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    changes = _verified_changes()
    changes["older_classification"] = "oncogenic"
    changes["newer_classification"] = "drug response"
    changes["historical_classification_type"] = "oncogenicity"
    record = update_record(path, "14206", changes, status="verified")
    timeline = public_record(record)["timeline"]
    assert timeline["older"]["classification"] == "oncogenic"
    assert timeline["newer"]["classification"] == "drug response"
    assert timeline["change_category"] == ("Changed from oncogenic to drug response")


def test_missing_history_remains_missing(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    record = load_workspace(path)["records"][0]
    timeline = public_record(record)["timeline"]
    assert record["older_classification"] == ""
    assert timeline["change_category"] == (
        "Historical classification not yet verified."
    )


def test_historical_source_must_be_an_official_https_url(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    _workspace_with_record(path)
    with pytest.raises(PilotWorkspaceError, match="official NCBI"):
        update_record(
            path,
            "14206",
            {"historical_source_url": "https://example.com/claim"},
        )
