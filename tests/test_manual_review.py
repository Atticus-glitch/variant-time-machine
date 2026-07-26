"""Tests for the empty manual-review table and review helper."""

import csv
from pathlib import Path

import pytest

from scripts import review_variant
from variant_time_machine.clinvar_api import ClinVarVariant

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL_TABLE = PROJECT_ROOT / "data" / "manual_review" / "test_variants.csv"


def test_manual_review_table_has_header_and_no_claimed_records() -> None:
    """The initial real-data table should contain no unverified rows."""
    with MANUAL_TABLE.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        rows = list(reader)

    assert reader.fieldnames == [
        "variant_id",
        "gene",
        "old_release_date",
        "new_release_date",
        "old_classification",
        "new_classification",
        "verification_source",
        "notes",
    ]
    assert rows == []


def test_review_tool_prints_current_data_and_unchecked_checklist(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The review command should inform but never mark checks complete."""
    result = ClinVarVariant(
        variant_identifier="VCV000014206.1",
        variation_id="14206",
        gene_name="CCL2",
        classification="protective",
        associated_conditions=("Example current condition",),
        review_status="no assertion criteria provided",
        evidence_summary="SCV submissions listed: 1",
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
    )
    monkeypatch.setattr(review_variant, "lookup_clinvar_variant", lambda value: result)

    assert review_variant.main(["14206"]) == 0
    output = capsys.readouterr().out
    assert "Current classification: protective" in output
    assert "old_classification: [verify from older archived release]" in output
    assert "new_classification: [verify from newer archived release]" in output
    for checklist_item in review_variant.CHECKLIST:
        assert f"[ ] {checklist_item}" in output
    assert "[x]" not in output.casefold()
