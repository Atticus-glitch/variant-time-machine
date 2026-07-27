"""Tests for the low-bandwidth manual ClinVar pilot command."""

from pathlib import Path

import pytest

from scripts import pilot_mode
from variant_time_machine.clinvar_api import ClinVarVariant
from variant_time_machine.pilot import PILOT_COLUMNS, read_pilot_rows


def _empty_pilot(path: Path) -> None:
    path.write_text(
        ",".join(PILOT_COLUMNS) + "\n" + ",,,,,,,,\n" * 5,
        encoding="utf-8",
    )


def _current_variant() -> ClinVarVariant:
    return ClinVarVariant(
        variant_identifier="VCV000014206.2",
        variation_id="14206",
        gene_name="CCL2",
        classification="Uncertain significance",
        associated_conditions=("Condition",),
        review_status="criteria provided",
        evidence_summary=None,
        source_url="https://www.ncbi.nlm.nih.gov/clinvar/variation/14206/",
        retrieved_at_utc="2026-07-26T00:00:00+00:00",
    )


def test_committed_pilot_has_five_empty_rows() -> None:
    path = Path("data/manual_review/pilot_variants.csv")
    rows = read_pilot_rows(path)
    assert len(rows) == 5
    assert all(tuple(row) == PILOT_COLUMNS for row in rows)
    assert all(not any(row.values()) for row in rows)


def test_unconfirmed_plan_makes_no_api_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pilot = tmp_path / "pilot.csv"
    _empty_pilot(pilot)
    monkeypatch.setattr(
        pilot_mode,
        "lookup_clinvar_variant",
        lambda *_args: pytest.fail("unconfirmed plan accessed the API"),
    )
    result = pilot_mode.main(
        ["14206", "--reason", "Manual test", "--pilot-csv", str(pilot)]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "Estimated size" in output
    assert "Why needed" in output
    assert "Large download protection: ON" in output
    assert "No request started" in output
    assert all(not row["variant_id"] for row in read_pilot_rows(pilot))


def test_confirmed_current_lookup_fills_only_one_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pilot = tmp_path / "pilot.csv"
    _empty_pilot(pilot)
    monkeypatch.setattr(
        pilot_mode, "lookup_clinvar_variant", lambda _identifier: _current_variant()
    )
    result = pilot_mode.main(
        [
            "14206",
            "--reason",
            "Manual test",
            "--confirm-api-requests",
            "--pilot-csv",
            str(pilot),
        ]
    )
    assert result == 0
    rows = read_pilot_rows(pilot)
    assert rows[0]["variant_id"] == "14206"
    assert rows[0]["VCV_accession"] == "VCV000014206.2"
    assert rows[0]["gene"] == "CCL2"
    assert rows[0]["reason_selected"] == "Manual test"
    assert rows[0]["current_classification"] == "Uncertain significance"
    assert rows[0]["historical_classification"] == ""
    assert "historical pending" in rows[0]["verification_status"]
    assert all(not row["variant_id"] for row in rows[1:])


def test_versioned_vcv_lookup_is_bounded_and_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xml = b"""<VariationArchive VariationID="14206" Accession="VCV000014206"
    Version="1">
    <Classifications><GermlineClassification>
    <Description>Uncertain significance</Description>
    </GermlineClassification></Classifications>
    </VariationArchive>"""

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            assert chunk_size == 64 * 1024
            yield xml

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        pilot_mode.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    classification, url = pilot_mode.lookup_historical_vcv("VCV000014206.1")
    assert classification == "Uncertain significance"
    assert "VCV000014206.1" in url


def test_historical_lookup_requires_an_explicit_version() -> None:
    with pytest.raises(ValueError, match="explicit version"):
        pilot_mode.lookup_historical_vcv("VCV000014206")
