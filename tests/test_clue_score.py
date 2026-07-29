"""Tests for frozen Clue Score V1 and strict answer normalization."""

from dataclasses import replace

import pytest

from variant_time_machine.clue_score import (
    ClueScoreError,
    OlderSnapshot,
    assert_leakage_safe_fields,
    compare_prediction,
    normalize_newer_outcome,
    older_snapshot_from_row,
    score_older_snapshot,
)


def older(**changes: object) -> OlderSnapshot:
    """Return one complete eligible older-only record."""
    values = {
        "variation_id": "100",
        "allele_ids": "10",
        "variant_types": "single nucleotide variant",
        "names": "NM_000001.1(GENE):c.10A>G (p.Arg4Gly)",
        "gene_symbols": "GENE",
        "clinical_significances": "Uncertain significance",
        "last_evaluated_dates": "Jan 01, 2020",
        "review_statuses": "criteria provided, single submitter",
        "submitter_counts": "1",
        "phenotypes": "Example condition",
        "coordinates": "GRCh38:1:10-10 A>G",
        "guidelines_values": "ACMG2016",
        "origin_simple_values": "germline",
        "release_date": "2022-01-06",
    }
    values.update(changes)
    return OlderSnapshot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("classification", "group", "reason", "scorable"),
    [
        ("Pathogenic", "moved_toward_pathogenic", "compatible_pathogenic", True),
        (
            "Likely pathogenic",
            "moved_toward_pathogenic",
            "compatible_pathogenic",
            True,
        ),
        (
            "Pathogenic/Likely pathogenic",
            "moved_toward_pathogenic",
            "compatible_pathogenic",
            True,
        ),
        ("Benign", "moved_toward_benign", "compatible_benign", True),
        ("Likely benign", "moved_toward_benign", "compatible_benign", True),
        (
            "Benign/Likely benign",
            "moved_toward_benign",
            "compatible_benign",
            True,
        ),
        ("Uncertain significance", "remained_uncertain", "exact_uncertain", True),
        (
            "Conflicting classifications of pathogenicity",
            "conflicting_or_unusable",
            "conflicting_classification",
            False,
        ),
        (
            "protective",
            "conflicting_or_unusable",
            "non_directional_germline_category",
            False,
        ),
        (
            "risk factor",
            "conflicting_or_unusable",
            "non_directional_germline_category",
            False,
        ),
        (
            "drug response",
            "conflicting_or_unusable",
            "non_directional_germline_category",
            False,
        ),
        (
            "association",
            "conflicting_or_unusable",
            "non_directional_germline_category",
            False,
        ),
        (
            "somatic clinical impact",
            "conflicting_or_unusable",
            "non_germline_scope",
            False,
        ),
        (
            "Likely oncogenic",
            "conflicting_or_unusable",
            "non_germline_scope",
            False,
        ),
        (
            "Pathogenic; risk factor",
            "conflicting_or_unusable",
            "non_directional_germline_category",
            False,
        ),
        (
            "other",
            "conflicting_or_unusable",
            "unrecognized_classification",
            False,
        ),
        (None, "conflicting_or_unusable", "missing_classification", False),
    ],
)
def test_strict_outcome_normalization(
    classification: str | None, group: str, reason: str, scorable: bool
) -> None:
    outcome = normalize_newer_outcome(classification)
    assert outcome.group == group
    assert outcome.reason_code == reason
    assert outcome.scorable is scorable


@pytest.mark.parametrize(
    ("name", "expected_score", "expected_direction", "clue"),
    [
        (
            "NM_1.1(G):c.10del (p.Arg4fs)",
            5,
            "pathogenic_direction",
            "loss_of_function_consequence",
        ),
        (
            "NM_1.1(G):c.10C>T (p.Arg4Ter)",
            5,
            "pathogenic_direction",
            "loss_of_function_consequence",
        ),
        (
            "NM_1.1(G):c.10+1G>A",
            4,
            "pathogenic_direction",
            "canonical_splice_consequence",
        ),
        (
            "NM_1.1(G):c.10A>G (p.Arg4Gly)",
            2,
            "remain_uncertain",
            "missense_consequence",
        ),
        (
            "NM_1.1(G):c.12A>G (p.Arg4=)",
            -2,
            "benign_direction",
            "synonymous_consequence",
        ),
        ("NR_1.1(G):n.10A>G", 0, "remain_uncertain", "noncoding_consequence"),
    ],
)
def test_consequence_points_are_transparent(
    name: str, expected_score: int, expected_direction: str, clue: str
) -> None:
    prediction = score_older_snapshot(older(names=name))
    assert prediction.total_score == expected_score
    assert prediction.predicted_direction == expected_direction
    assert clue in prediction.clues_used
    assert prediction.arithmetic.endswith(f"= {expected_score:+d}")


def test_multiple_submitters_and_criteria_are_separate_frozen_clues() -> None:
    prediction = score_older_snapshot(
        older(
            names="unrecognized name",
            review_statuses="criteria provided, multiple submitters, no conflicts",
            submitter_counts="3",
        )
    )
    assert prediction.total_score == 2
    assert prediction.predicted_direction == "remain_uncertain"
    assert set(prediction.clues_used) == {
        "multiple_agreeing_submitters",
        "criteria_without_conflict",
    }


def test_no_directional_clue_produces_no_prediction() -> None:
    prediction = score_older_snapshot(
        older(
            names="unrecognized name",
            review_statuses="no assertion criteria provided",
            submitter_counts="1",
        )
    )
    assert prediction.total_score == 0
    assert prediction.predicted_direction == "no_prediction"
    assert prediction.confidence == "No prediction"


def test_scoring_rejects_ineligible_or_wrong_date_records() -> None:
    with pytest.raises(ClueScoreError, match="exact older"):
        score_older_snapshot(older(clinical_significances="Likely benign"))
    with pytest.raises(ClueScoreError, match="snapshot date"):
        score_older_snapshot(older(release_date="2024-01-04"))


def test_leakage_guard_rejects_every_newer_field_family() -> None:
    for field in (
        "new_classification",
        "newer_review_status",
        "2024_date",
        "actual_outcome",
        "answer_key",
    ):
        with pytest.raises(ClueScoreError, match="Future-information"):
            assert_leakage_safe_fields(("names", field))


def test_newer_values_cannot_change_prediction() -> None:
    base = {
        **older().__dict__,
        "new_classification": "Pathogenic",
        "new_review_status": "reviewed by expert panel",
        "new_submitter_count": "99",
        "new_last_evaluated": "Jan 1, 2024",
    }
    first = score_older_snapshot(older_snapshot_from_row(base))
    changed = {
        **base,
        "new_classification": "Benign",
        "new_review_status": "no assertion criteria provided",
        "new_submitter_count": "0",
        "new_last_evaluated": "Dec 31, 2023",
    }
    second = score_older_snapshot(older_snapshot_from_row(changed))
    assert first == second


def test_prediction_is_compared_only_after_scoring() -> None:
    prediction = score_older_snapshot(
        replace(older(), names="NM_1.1(G):c.10del (p.Arg4fs)")
    )
    correct = compare_prediction(prediction, normalize_newer_outcome("Pathogenic"))
    wrong = compare_prediction(prediction, normalize_newer_outcome("Benign"))
    unusable = compare_prediction(
        prediction, normalize_newer_outcome("Conflicting classifications")
    )
    assert (correct.result, correct.reason_code) == ("Correct", "direction_matched")
    assert (wrong.result, wrong.reason_code) == ("Wrong", "direction_mismatch")
    assert unusable.result == "Not Scorable"
