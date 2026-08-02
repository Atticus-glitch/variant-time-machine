"""Tests for the frozen temporal V7 protocol."""

import csv
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from variant_time_machine.ai_holdout_v4 import _sha256
from variant_time_machine.ai_temporal_v7 import (
    V7_FEATURE_NAMES,
    _normalised_values,
    _select_threshold,
    _transform_v5_features,
    evaluate_v7_once,
    load_ai_temporal_v7_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v7_config_freezes_temporal_boundary_and_one_thousand() -> None:
    config = load_ai_temporal_v7_config()
    assert config["prediction_snapshot_date"] == "2024-01-04"
    assert config["answer_snapshot_date"] == "2026-07-02"
    assert config["final_test_records"] == 1000
    assert tuple(config["features"]) == V7_FEATURE_NAMES
    assert "before downloading" in config["candidate_rule"]


def test_v7_numeric_transform_is_nonlinear_and_keeps_feature_count() -> None:
    source = [0.0] * 14
    source[11] = 999.0
    source[12] = 3.0
    transformed = _transform_v5_features(source)
    assert len(transformed) == 14
    assert transformed[11] == math.log1p(999)
    assert transformed[12] == math.log1p(3)


def test_v7_threshold_selection_uses_only_supplied_predictions() -> None:
    targets = np.asarray([0, 0, 1, 1])
    probabilities = np.asarray([0.1, 0.4, 0.6, 0.9])
    threshold = _select_threshold(targets, probabilities)
    assert 0.4 < threshold <= 0.6


def test_v7_identifier_sets_are_normalized() -> None:
    assert _normalised_values("1,2;3") == {"1", "2", "3"}
    assert _normalised_values("-") == set()


def test_frozen_v7_temporal_test_is_absent_from_development() -> None:
    output_dir = ROOT / "outputs/ai_temporal_v7"
    with (output_dir / "temporal_test_predictions.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1000
    test_ids = {row["variation_id"] for row in rows}
    assert len(test_ids) == 1000
    with sqlite3.connect(
        ROOT / "data/processed/resolved_direction_v2.sqlite3"
    ) as connection:
        development_ids = {
            str(row[0])
            for row in connection.execute("SELECT variation_id FROM predictions")
        }
    assert test_ids.isdisjoint(development_ids)

    training = json.loads(
        (output_dir / "training_summary.json").read_text(encoding="utf-8")
    )
    sealed = output_dir / "sealed_candidate_predictions.sqlite3"
    assert _sha256(sealed) == training["sealed_predictions_sha256"]
    metrics = json.loads((output_dir / "test_metrics.json").read_text(encoding="utf-8"))
    assert metrics["development_test_variation_id_overlap"] == 0
    assert metrics["test_records"] == 1000


def test_frozen_v7_refuses_second_evaluation() -> None:
    with pytest.raises(FileExistsError, match="already evaluated"):
        evaluate_v7_once(
            ROOT / "data/raw/clinvar/variant_summary_2026-07.txt.gz",
            ROOT / "outputs/ai_temporal_v7",
        )
