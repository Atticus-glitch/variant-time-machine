"""Tests for the identifier-only proof-of-concept matcher."""

from pathlib import Path

import pandas as pd
import pytest

from variant_time_machine.match import match_variant_summary_snapshots

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_matcher_preserves_ambiguity_and_collapses_assemblies() -> None:
    """The matcher should report conservative outcomes for each synthetic case."""
    older = pd.read_csv(
        FIXTURES_DIR / "synthetic_older_variant_summary.tsv", sep="\t", dtype="string"
    )
    newer = pd.read_csv(
        FIXTURES_DIR / "synthetic_newer_variant_summary.tsv", sep="\t", dtype="string"
    )

    observed = match_variant_summary_snapshots(older, newer).set_index(
        "source_allele_id"
    )

    assert observed.loc["100", "match_status"] == "exact_identifier_match"
    assert observed.loc["100", "source_row_count"] == 2
    assert observed.loc["100", "newer_classification"] == "Pathogenic"
    assert observed.loc["101", "match_status"] == "allele_id_match_variation_changed"
    assert observed.loc["101", "target_variation_id"] == "2001"
    assert observed.loc["102", "match_status"] == "ambiguous_multiple_candidates"
    assert observed.loc["102", "candidate_count"] == 2
    assert observed.loc["103", "match_status"] == "conflicting_identifiers"
    assert observed.loc["104", "match_status"] == "unmatched"
    assert observed.loc["105", "match_status"] == "unsupported_complex_identifier"


def test_matcher_requires_documented_columns() -> None:
    """Missing source columns should produce a clear error."""
    incomplete = pd.DataFrame({"AlleleID": [1]})
    complete = pd.DataFrame(
        {
            "AlleleID": [1],
            "VariationID": [2],
            "ClinicalSignificance": ["Uncertain significance"],
        }
    )

    with pytest.raises(ValueError, match="VariationID, ClinicalSignificance"):
        match_variant_summary_snapshots(incomplete, complete)
