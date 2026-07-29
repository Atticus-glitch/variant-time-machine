"""Tests for the changed-outcome-only binary Version 2 experiment."""

from pathlib import Path

import pytest

from tests.test_clue_score_experiment import source_database
from variant_time_machine.clue_score_experiment import (
    list_predictions,
    run_clue_score_experiment,
)
from variant_time_machine.resolved_direction import (
    OUTPUT_FILENAMES,
    ResolvedDirectionError,
    binary_direction,
    binary_result,
    resolved_summary,
    run_resolved_direction_experiment,
)


@pytest.mark.parametrize(
    ("score", "direction"),
    [
        (5, "pathogenic_direction"),
        (1, "pathogenic_direction"),
        (0, "no_prediction"),
        (-1, "benign_direction"),
        (-4, "benign_direction"),
    ],
)
def test_binary_direction_never_predicts_uncertain(score: int, direction: str) -> None:
    assert binary_direction(score) == direction
    assert binary_direction(score) != "remain_uncertain"


def test_binary_comparison_accepts_only_resolved_outcomes() -> None:
    assert binary_result("pathogenic_direction", "moved_toward_pathogenic") == (
        "Correct",
        "direction_matched",
        1,
    )
    assert binary_result("benign_direction", "moved_toward_pathogenic") == (
        "Wrong",
        "direction_mismatch",
        0,
    )
    assert binary_result("no_prediction", "moved_toward_benign") == (
        "No Prediction",
        "zero_score_no_direction",
        None,
    )
    with pytest.raises(ResolvedDirectionError, match="resolved"):
        binary_result("pathogenic_direction", "remained_uncertain")


def test_resolved_experiment_excludes_uncertain_and_unsafe_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    parent = tmp_path / "v1.sqlite3"
    parent_outputs = tmp_path / "v1_outputs"
    result = tmp_path / "v2.sqlite3"
    outputs = tmp_path / "v2_outputs"
    source_database(source)
    run_clue_score_experiment(source, parent, parent_outputs)

    summary = run_resolved_direction_experiment(parent, result, outputs)

    assert summary["resolved_direction_records"] == 2
    assert summary["actual_pathogenic"] == 2
    assert summary["actual_benign"] == 0
    assert summary["correct"] == 1
    assert summary["wrong"] == 1
    assert summary["no_prediction"] == 0
    assert summary["not_scorable"] == 0
    assert set(OUTPUT_FILENAMES).issubset(path.name for path in outputs.iterdir())
    assert resolved_summary(result)["conditional_task"] is True
    listed = list_predictions(result)
    assert listed["total"] == 2
    assert {row["predicted_direction"] for row in listed["rows"]}.isdisjoint(
        {"remain_uncertain"}
    )
