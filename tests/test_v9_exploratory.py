"""Tests for isolated exploratory V9 training safeguards."""

import json
from pathlib import Path

import numpy as np
import pytest

from variant_time_machine.v9_exploratory import (
    V9ExploratoryError,
    _candidate_estimators,
    _clue_score,
    _load_inputs,
    _weights,
    run_v9_exploratory,
)

ROOT = Path(__file__).resolve().parents[1]


def test_exploratory_inputs_are_opened_locked_and_feature_allowlisted() -> None:
    config, manifest, frame, features = _load_inputs(
        ROOT, ROOT / "config/v9_exploratory.json"
    )
    assert config["official_v9_winner"] is None
    assert config["final_test_evaluated"] is False
    assert manifest["training_eligible"] is False
    assert manifest["final_test_allowed"] is False
    assert len(frame) == 1000
    assert frame["component_hash"].nunique() == 559
    assert len(features) == 64
    assert all(name.startswith("feature__") for name in features)
    assert (frame["dataset_outcome"] == frame["original_automatic_outcome"]).all()


def test_component_weights_equalize_total_component_weight() -> None:
    groups = np.asarray(["A", "A", "B", "C", "C", "C"])
    weights = _weights(groups)
    assert weights.tolist() == pytest.approx([0.5, 0.5, 1.0, 1 / 3, 1 / 3, 1 / 3])
    assert sum(weights[groups == "A"]) == pytest.approx(1)
    assert sum(weights[groups == "B"]) == pytest.approx(1)
    assert sum(weights[groups == "C"]) == pytest.approx(1)


def test_candidates_do_not_multiply_component_weights_by_class_weights() -> None:
    config = json.loads(
        (ROOT / "config/v9_exploratory.json").read_text(encoding="utf-8")
    )
    assert config["class_weight"] is None
    for family in config["candidates"]:
        for _, estimator in _candidate_estimators(family, config):
            model = (
                estimator.named_steps["model"]
                if hasattr(estimator, "named_steps")
                else estimator
            )
            assert model.get_params()["class_weight"] is None


def test_clue_score_remains_coverage_conditioned() -> None:
    _, _, frame, _ = _load_inputs(ROOT, ROOT / "config/v9_exploratory.json")
    clue_config = json.loads(
        (ROOT / "config/clue_score_v1.yaml").read_text(encoding="utf-8")
    )
    score, directional, predictions = _clue_score(frame, clue_config)
    assert len(score) == len(directional) == len(predictions) == 1000
    assert 0 < int(directional.sum()) < 1000
    assert set(predictions.tolist()) <= {0, 1}


def test_clue_score_does_not_award_criteria_when_review_conflicts() -> None:
    _, _, frame, _ = _load_inputs(ROOT, ROOT / "config/v9_exploratory.json")
    clue_config = json.loads(
        (ROOT / "config/clue_score_v1.yaml").read_text(encoding="utf-8")
    )
    clue_features = [
        "feature__consequence_loss_of_function",
        "feature__consequence_canonical_splice",
        "feature__consequence_missense",
        "feature__consequence_synonymous",
        "feature__consequence_noncoding",
        "feature__expert_panel",
        "feature__multiple_submitters_no_conflict",
        "feature__criteria_supplied",
        "feature__conflicting_interpretations",
    ]
    example = frame.iloc[[0]].copy()
    example.loc[:, clue_features] = 0
    example.loc[:, "feature__criteria_supplied"] = 1
    example.loc[:, "feature__conflicting_interpretations"] = 1
    score, directional, _ = _clue_score(example, clue_config)
    assert score.tolist() == [0]
    assert directional.tolist() == [False]


def test_exploratory_runner_refuses_official_output_paths(tmp_path: Path) -> None:
    config = json.loads(
        (ROOT / "config/v9_exploratory.json").read_text(encoding="utf-8")
    )
    assert config["status"] == "frozen_exploratory_opened_v8_plan"
    with pytest.raises(V9ExploratoryError, match="official or frozen paths"):
        run_v9_exploratory(ROOT, output_dir=tmp_path / "frozen" / "v9")


def test_exploratory_plan_cannot_name_an_official_winner(tmp_path: Path) -> None:
    config = json.loads(
        (ROOT / "config/v9_exploratory.json").read_text(encoding="utf-8")
    )
    config["official_v9_winner"] = "invented"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(V9ExploratoryError, match="cannot authorize final V9"):
        _load_inputs(ROOT, path)
