"""Tests for conservative pilot comparison and local review persistence."""

import os
from pathlib import Path

import pytest

from scripts import extract_pilot_history
from variant_time_machine.pilot import (
    compare_pilot_records,
    load_reviews,
    save_review,
    write_json_atomic,
)
from variant_time_machine.remote_archive import (
    ExtractedVCVRecord,
    RemoteReleaseMetadata,
)


def _record(
    variation_id: str,
    classification: str | None,
    *,
    status: str | None = "current",
    replaced_by: tuple[str, ...] = (),
) -> ExtractedVCVRecord:
    return ExtractedVCVRecord(
        variation_id=variation_id,
        accession=f"VCV{int(variation_id):09d}",
        version="1",
        record_type="classified",
        record_status=status,
        name=f"variant {variation_id}",
        allele_ids=(variation_id,),
        genes=("GENE",),
        conditions=("Condition",),
        germline_classification=classification,
        germline_review_status="criteria provided",
        germline_last_evaluated=None,
        germline_submission_count="1",
        somatic_clinical_impact=None,
        oncogenicity_classification=None,
        replaced_by=replaced_by,
        replacement_list=(),
    )


def test_comparison_uses_exact_ids_and_never_claims_verification() -> None:
    comparisons = compare_pilot_records(
        ["2", "4", "5"],
        [_record("2", "Uncertain significance"), _record("4", "Benign")],
        [
            _record("2", "Pathogenic"),
            _record("4", "Benign", status="replaced", replaced_by=("VCV9",)),
        ],
        older_release_date="2024-02-01",
        newer_release_date="2025-02-06",
    )
    assert comparisons[0]["match_status"] == "exact_variation_id_match"
    assert comparisons[0]["classification_change"] == (
        "Germline_Classification_Changed"
    )
    assert comparisons[1]["classification_change"] == (
        "No_Germline_Classification_Change"
    )
    assert comparisons[1]["record_history_flags"] == [
        "newer_status:replaced",
        "newer_replacement_metadata_present",
    ]
    assert comparisons[2]["match_status"] == "missing_in_both_releases"
    assert comparisons[2]["classification_change"] == "Unable_to_Verify"
    assert all(
        item["automatic_verification_status"] == "requires_manual_review"
        for item in comparisons
    )


def test_manual_review_round_trip_and_validation(tmp_path: Path) -> None:
    review_path = tmp_path / "reviews.json"
    saved = save_review(review_path, "2", "Confirmed match", "Checked both XML rows")
    assert saved["status"] == "Confirmed match"
    assert load_reviews(review_path)["2"]["notes"] == "Checked both XML rows"
    with pytest.raises(ValueError, match="Unknown"):
        save_review(review_path, "2", "Automatically verified", "")
    with pytest.raises(ValueError, match="numeric"):
        save_review(review_path, "VCV2", "Not reviewed", "")


def test_atomic_json_removes_temporary_file_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("disk error")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk error"):
        write_json_atomic(output, {"test": True})
    assert not output.with_suffix(".json.tmp").exists()
    assert not output.exists()


def test_dry_run_does_not_call_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pilot = tmp_path / "pilot.csv"
    pilot.write_text(
        "variation_id,current_accession\n2,VCV000000002.1\n", encoding="utf-8"
    )

    def metadata(release: object) -> RemoteReleaseMetadata:
        return RemoteReleaseMetadata(
            label=release.label,
            release_date=release.release_date.isoformat(),
            source_url=release.source_url,
            schema_version=release.schema_version,
            expected_compressed_size_bytes=release.compressed_size_bytes,
            reported_compressed_size_bytes=release.compressed_size_bytes,
            expected_md5=release.md5,
            reported_md5=release.md5,
            size_matches=True,
            md5_matches=True,
        )

    monkeypatch.setattr(extract_pilot_history, "inspect_remote_release", metadata)
    monkeypatch.setattr(
        extract_pilot_history,
        "extract_remote_records",
        lambda *_args, **_kwargs: pytest.fail("dry run started extraction"),
    )
    assert extract_pilot_history.main(["--dry-run", "--pilot-csv", str(pilot)]) == 0
    assert "No archive body was requested" in capsys.readouterr().out
