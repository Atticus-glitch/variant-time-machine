"""Tests for parsing and historical VUS timeline construction."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_timeline_dataset import main as build_timeline_main
from variant_time_machine.config import CLINVAR_RELEASES, ClinVarRelease
from variant_time_machine.download import download_clinvar_release
from variant_time_machine.match import (
    classify_vus_change,
    match_variants_across_releases,
)
from variant_time_machine.parse import parse_clinvar_release, parse_variant_summary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_TIMELINE = PROJECT_ROOT / "data" / "interim" / "example_clinvar_timeline.csv"


def _synthetic_timeline() -> pd.DataFrame:
    """Load the clearly labeled synthetic timeline fixture."""
    parsed = parse_clinvar_release(EXAMPLE_TIMELINE)
    assert set(parsed["data_notice"]) == {
        "SYNTHETIC TEST DATA - NOT SCIENTIFIC RESULTS"
    }
    return parsed


def _timeline_result() -> pd.DataFrame:
    """Split the synthetic fixture into releases and run matching."""
    timeline = _synthetic_timeline()
    older = timeline[timeline["release_date"] == "2022-01-06"]
    newer = timeline[timeline["release_date"] == "2024-01-04"]
    return match_variants_across_releases(older, newer)


def test_vus_to_pathogenic_is_classified_correctly() -> None:
    """An exact later pathogenic term should receive the declared outcome."""
    result = _timeline_result().set_index("variant_id")
    assert result.loc["1000", "classification_change"] == "VUS_to_Pathogenic"


def test_vus_to_benign_is_classified_correctly() -> None:
    """An exact later benign term should receive the declared outcome."""
    result = _timeline_result().set_index("variant_id")
    assert result.loc["1001", "classification_change"] == "VUS_to_Benign"


def test_unchanged_vus_remains_uncertain() -> None:
    """An exact later VUS term should remain VUS."""
    result = _timeline_result().set_index("variant_id")
    assert result.loc["1002", "classification_change"] == "VUS_to_Still_Uncertain"


def test_conflicting_classification_is_preserved() -> None:
    """An unclear later aggregate should not be forced into a direction."""
    result = _timeline_result().set_index("variant_id")
    assert result.loc["1003", "classification_change"] == "VUS_to_Conflicting"
    assert (
        result.loc["1003", "new_classification"]
        == "Conflicting classifications of pathogenicity"
    )


def test_likely_outcomes_and_unmatched_records_are_preserved() -> None:
    """Likely terms should stay separate and absent later records should be visible."""
    result = _timeline_result().set_index("variant_id")
    assert result.loc["1004", "classification_change"] == "VUS_to_Likely_Pathogenic"
    assert result.loc["1005", "classification_change"] == "VUS_to_Likely_Benign"
    assert result.loc["1006", "classification_change"] == "Unable_to_Verify"
    assert result.loc["1006", "match_status"] == "unmatched"


def test_missing_identifiers_do_not_crash_matching() -> None:
    """A VUS with missing identifiers should remain in an unusable category."""
    result = _timeline_result()
    missing = result[result["gene"] == "MISSING_TEST"].iloc[0]
    assert missing["classification_change"] == "Unable_to_Verify"
    assert missing["match_status"] == "missing_identifier"


@pytest.mark.parametrize(
    ("classification", "status", "expected"),
    [
        ("Pathogenic", "exact_identifier_match", "VUS_to_Pathogenic"),
        (
            "Likely pathogenic",
            "exact_identifier_match",
            "VUS_to_Likely_Pathogenic",
        ),
        ("Benign", "exact_identifier_match", "VUS_to_Benign"),
        ("Likely benign", "exact_identifier_match", "VUS_to_Likely_Benign"),
        (
            "Conflicting classifications of pathogenicity",
            "exact_identifier_match",
            "VUS_to_Conflicting",
        ),
        (
            "Uncertain significance",
            "exact_identifier_match",
            "VUS_to_Still_Uncertain",
        ),
        ("risk factor", "exact_identifier_match", "Unable_to_Verify"),
        ("Pathogenic", "conflicting_identifiers", "Unable_to_Verify"),
    ],
)
def test_declared_vus_outcome_categories(
    classification: str, status: str, expected: str
) -> None:
    """Only supported exact terms and verified matches should receive outcomes."""
    assert classify_vus_change(classification, status) == expected


def test_raw_variant_summary_parser_maps_fields_and_keeps_missing_data() -> None:
    """Raw ClinVar-style headers should map without requiring complete coordinates."""
    raw = pd.DataFrame(
        {
            "#AlleleID": ["200"],
            "VariationID": ["3000"],
            "GeneSymbol": ["TESTGENE"],
            "Assembly": ["GRCh38"],
            "Chromosome": ["1"],
            "Start": [""],
            "Stop": [""],
            "ReferenceAllele": ["A"],
            "AlternateAllele": ["G"],
            "ClinicalSignificance": ["Uncertain significance"],
            "ReviewStatus": ["criteria provided, single submitter"],
            "NumberSubmitters": ["1"],
        }
    )

    parsed = parse_variant_summary(raw, "2022-01-06")

    assert parsed.loc[0, "variant_id"] == "3000"
    assert parsed.loc[0, "allele_id"] == "200"
    assert parsed.loc[0, "gene"] == "TESTGENE"
    assert pd.isna(parsed.loc[0, "position"])
    assert parsed.loc[0, "release_date"] == "2022-01-06"


def test_compressed_archive_parsing_and_filename_date_check(tmp_path: Path) -> None:
    """A ClinVar-style TSV.GZ should parse and reject a mismatched month."""
    raw = pd.DataFrame(
        {
            "#AlleleID": ["200"],
            "VariationID": ["3000"],
            "GeneSymbol": ["TESTGENE"],
            "Assembly": ["GRCh38"],
            "Chromosome": ["1"],
            "Start": ["123"],
            "Stop": ["123"],
            "ReferenceAllele": ["A"],
            "AlternateAllele": ["G"],
            "ClinicalSignificance": ["Uncertain significance"],
            "ReviewStatus": ["criteria provided single submitter"],
            "NumberSubmitters": ["1"],
        }
    )
    archive = tmp_path / "variant_summary_2022-01.txt.gz"
    raw.to_csv(archive, sep="\t", index=False, compression="gzip")

    parsed = parse_clinvar_release(archive, "2022-01-06")
    assert parsed.loc[0, "variant_id"] == "3000"

    with pytest.raises(ValueError, match="does not match archive filename"):
        parse_clinvar_release(archive, "2024-01-04")


def test_release_chronology_is_enforced() -> None:
    """A reversed historical comparison should fail clearly."""
    timeline = _synthetic_timeline()
    later_vus = timeline[
        (timeline["release_date"] == "2024-01-04")
        & (timeline["classification"] == "Uncertain significance")
    ]
    earlier = timeline[timeline["release_date"] == "2022-01-06"]

    with pytest.raises(ValueError, match="must be before"):
        match_variants_across_releases(later_vus, earlier)


def test_numeric_multi_allele_variation_is_not_counted_twice() -> None:
    """A numeric complex Variation ID should remain one unsupported record."""
    columns = {
        "gene": ["COMPLEX", "COMPLEX"],
        "classification": ["Uncertain significance", "Uncertain significance"],
        "review_status": ["criteria provided", "criteria provided"],
        "submission_count": [1, 1],
        "source_row_id": ["a", "b"],
        "assembly": ["GRCh38", "GRCh38"],
    }
    older = pd.DataFrame(
        {
            **columns,
            "variant_id": ["9000", "9000"],
            "allele_id": ["901", "902"],
            "release_date": ["2022-01-06", "2022-01-06"],
        }
    )
    newer = pd.DataFrame(
        {
            **columns,
            "variant_id": ["9000", "9000"],
            "allele_id": ["901", "902"],
            "release_date": ["2024-01-04", "2024-01-04"],
        }
    )

    result = match_variants_across_releases(older, newer)

    assert len(result) == 1
    assert result.loc[0, "match_status"] == "unsupported_complex_identifier"
    assert result.loc[0, "classification_change"] == "Unable_to_Verify"
    assert result.loc[0, "old_source_row_count"] == 2


def test_command_line_pipeline_writes_output_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command-line entry point should process two files and report real counts."""
    source = pd.read_csv(EXAMPLE_TIMELINE, dtype="string", keep_default_na=False)
    older_path = tmp_path / "older.csv"
    newer_path = tmp_path / "newer.csv"
    output_path = tmp_path / "timeline.csv"
    source[source["release_date"] == "2022-01-06"].to_csv(older_path, index=False)
    source[source["release_date"] == "2024-01-04"].to_csv(newer_path, index=False)

    exit_code = build_timeline_main(
        [str(older_path), str(newer_path), "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.is_file()
    assert "Variants processed: 8" in captured.out
    assert "Variants matched: 6" in captured.out
    assert "Variants changed: 4" in captured.out
    assert "Variants ambiguous: 1" in captured.out
    output = pd.read_csv(output_path)
    assert set(output["classification_change"]) == {
        "VUS_to_Conflicting",
        "Unable_to_Verify",
        "VUS_to_Benign",
        "VUS_to_Likely_Benign",
        "VUS_to_Likely_Pathogenic",
        "VUS_to_Pathogenic",
        "VUS_to_Still_Uncertain",
    }


def test_download_requires_explicit_confirmation(tmp_path: Path) -> None:
    """Calling the downloader without confirmation must not access the network."""
    with pytest.raises(ValueError, match="Large download not started"):
        download_clinvar_release(CLINVAR_RELEASES["older"], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_download_records_provenance_and_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A confirmed mocked download should create data and matching metadata."""
    content = b"small mocked ClinVar content\n"

    class FakeResponse:
        """Small context-manager response used without network access."""

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            assert chunk_size > 0
            return [content]

    monkeypatch.setattr(
        "variant_time_machine.download.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    release = ClinVarRelease(
        label="test",
        release_date=date(2022, 1, 6),
        source_url="https://example.test/variant_summary_test.txt.gz",
    )

    data_path, metadata_path = download_clinvar_release(release, tmp_path, confirm=True)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert data_path.read_bytes() == content
    assert metadata["source_url"] == release.source_url
    assert metadata["release_date"] == "2022-01-06"
    assert metadata["filename"] == data_path.name
    assert metadata["size_bytes"] == len(content)
    assert metadata["checksum_algorithm"] == "sha256"
    assert metadata["checksum"] == hashlib.sha256(content).hexdigest()
    assert metadata["retrieval_date_utc"].endswith("+00:00")


def test_download_finalization_restores_existing_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A metadata finalization failure should restore prior data and metadata."""
    new_content = b"replacement content\n"

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return [new_content]

    monkeypatch.setattr(
        "variant_time_machine.download.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    release = ClinVarRelease(
        label="test",
        release_date=date(2022, 1, 6),
        source_url="https://example.test/variant_summary_test.txt.gz",
    )
    data_path = tmp_path / release.filename
    metadata_path = data_path.with_suffix(f"{data_path.suffix}.metadata.json")
    data_path.write_bytes(b"original data\n")
    metadata_path.write_text("original metadata\n", encoding="utf-8")

    original_replace = Path.replace

    def fail_metadata_replace(path: Path, target: Path) -> Path:
        if path.name.endswith(".metadata.json.part"):
            raise OSError("simulated metadata replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_metadata_replace)

    with pytest.raises(RuntimeError, match="Could not finalize"):
        download_clinvar_release(release, tmp_path, confirm=True, overwrite=True)

    assert data_path.read_bytes() == b"original data\n"
    assert metadata_path.read_text(encoding="utf-8") == "original metadata\n"
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.backup-*"))


def test_download_backup_failure_does_not_delete_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure before a backup move must leave the original pair untouched."""
    new_content = b"replacement content\n"

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return [new_content]

    monkeypatch.setattr(
        "variant_time_machine.download.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    release = ClinVarRelease(
        label="test",
        release_date=date(2022, 1, 6),
        source_url="https://example.test/variant_summary_test.txt.gz",
    )
    data_path = tmp_path / release.filename
    metadata_path = data_path.with_suffix(f"{data_path.suffix}.metadata.json")
    data_path.write_bytes(b"original data\n")
    metadata_path.write_text("original metadata\n", encoding="utf-8")

    original_replace = Path.replace

    def fail_data_backup(path: Path, target: Path) -> Path:
        if path == data_path and ".backup-" in target.name:
            raise OSError("simulated backup failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_data_backup)

    with pytest.raises(RuntimeError, match="Could not finalize"):
        download_clinvar_release(release, tmp_path, confirm=True, overwrite=True)

    assert data_path.read_bytes() == b"original data\n"
    assert metadata_path.read_text(encoding="utf-8") == "original metadata\n"
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.backup-*"))
