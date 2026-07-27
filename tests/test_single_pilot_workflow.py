"""Tests for previewing and saving the first single-variant pilot."""

from pathlib import Path

import pytest

from scripts import run_pilot_workflow, select_pilot_variant
from variant_time_machine.clinvar_api import ClinVarVariant
from variant_time_machine.pilot_record import (
    build_pilot_record,
    empty_pilot_record,
    load_pilot_record,
    save_pilot_record,
)


def _variant() -> ClinVarVariant:
    return ClinVarVariant(
        variant_identifier="VCV000014206.1",
        variation_id="14206",
        gene_name="CCL2",
        classification="Uncertain significance",
        associated_conditions=("Test condition",),
        review_status="criteria provided, single submitter",
        evidence_summary=None,
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
    )


def test_empty_record_has_declared_fields_and_no_scientific_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pilot.json"
    save_pilot_record(path, empty_pilot_record())
    record = load_pilot_record(path)
    assert record["variant_id"] == ""
    assert record["historical_records_found"] == []
    assert record["sources"] == []
    assert not path.with_suffix(".json.tmp").exists()


def test_preview_plan_does_not_request_or_save(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        select_pilot_variant,
        "lookup_clinvar_variant",
        lambda *_args: pytest.fail("preview plan accessed the API"),
    )
    result = select_pilot_variant.main(["--variation-id", "14206"])
    assert result == 0
    output = capsys.readouterr().out
    assert "Estimated size" in output
    assert "No request started" in output


def test_confirmed_preview_displays_fields_but_does_not_accept(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        select_pilot_variant, "lookup_clinvar_variant", lambda _value: _variant()
    )
    result = select_pilot_variant.main(
        ["--vcv", "VCV000014206", "--confirm-api-requests"]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "Variant ID: 14206" in output
    assert "Gene: CCL2" in output
    assert "Classification: Uncertain significance" in output
    assert "Review status: criteria provided, single submitter" in output
    assert "Conditions: Test condition" in output
    assert "Preview only" in output


def test_gene_preview_uses_only_returned_small_candidate_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        select_pilot_variant, "search_clinvar_gene", lambda _gene: ("14206",)
    )
    monkeypatch.setattr(
        select_pilot_variant, "lookup_clinvar_variant", lambda _value: _variant()
    )
    assert select_pilot_variant.main(["--gene", "CCL2", "--confirm-api-requests"]) == 0
    assert "Candidate 1" in capsys.readouterr().out


def test_workflow_without_request_confirmation_keeps_empty_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "pilot.json"
    save_pilot_record(output, empty_pilot_record())
    monkeypatch.setattr(
        run_pilot_workflow,
        "lookup_clinvar_variant",
        lambda *_args: pytest.fail("unconfirmed workflow accessed the API"),
    )
    result = run_pilot_workflow.main(
        ["14206", "--reason", "Test the first workflow", "--output", str(output)]
    )
    assert result == 0
    assert load_pilot_record(output)["variant_id"] == ""


def test_workflow_saves_current_record_with_history_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "pilot.json"
    save_pilot_record(output, empty_pilot_record())
    monkeypatch.setattr(
        run_pilot_workflow, "lookup_clinvar_variant", lambda _value: _variant()
    )
    result = run_pilot_workflow.main(
        [
            "VCV000014206",
            "--reason",
            "Clear identifiers for a workflow test",
            "--confirm-api-request",
            "--confirm-selection",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    record = load_pilot_record(output)
    assert record["variant_id"] == "14206"
    assert record["vcv_accession"] == "VCV000014206.1"
    assert record["selection_reason"] == "Clear identifiers for a workflow test"
    assert record["historical_records_found"] == []
    assert "historical verification pending" in record["verification_status"]
    assert record["notes"] == (
        "Selected pilot example only; not a scientific conclusion."
    )


def test_build_record_requires_a_selection_reason() -> None:
    with pytest.raises(ValueError, match="selection reason"):
        build_pilot_record(_variant(), "  ")
