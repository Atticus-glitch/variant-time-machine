"""Tests for learned-weight Statistical Model V3."""

import json
import sqlite3
from pathlib import Path

import pytest

from variant_time_machine.statistical_model_v3 import (
    FEATURE_NAMES,
    StatisticalModelV3Error,
    build_partition,
    load_statistical_model_v3_config,
    run_statistical_model_v3,
)


def _row(identifier: str, genes: tuple[str, ...], target: int, feature: int) -> dict:
    return {
        "variation_id": identifier,
        "gene_tokens": genes,
        "features": (feature, *([0] * (len(FEATURE_NAMES) - 1))),
        "target": target,
        "outcome_group": "moved_toward_pathogenic" if target else "moved_toward_benign",
        "v2_predicted_direction": "no_prediction",
    }


def _config(source_hash: str = "unused") -> dict:
    config = load_statistical_model_v3_config()
    config["source_database_sha256"] = source_hash
    config["partition"] = {**config["partition"], "test_fraction": 0.5, "salt": "test"}
    return config


def test_partition_is_deterministic_label_independent_and_grouped() -> None:
    rows = [
        _row("1", ("A", "B"), 0, 0),
        _row("2", ("B", "C"), 1, 1),
        _row("3", ("D",), 0, 0),
        _row("4", (), 1, 1),
        _row("5", ("E",), 0, 0),
    ]
    config = _config()
    first = build_partition(rows, config)
    changed_labels = [{**row, "target": 1 - row["target"]} for row in reversed(rows)]
    second = build_partition(changed_labels, config)
    assert first == second
    assignments = {row["variation_id"]: row for row in first["assignments"]}
    assert assignments["1"]["partition"] == assignments["2"]["partition"]
    assert assignments["1"]["group_key"] == "gene:A|B|C"


def test_config_rejects_changed_feature_allowlist(tmp_path: Path) -> None:
    config = load_statistical_model_v3_config()
    config["features"] = ["total_score"]
    path = tmp_path / "bad.yaml"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(StatisticalModelV3Error, match="allowlist"):
        load_statistical_model_v3_config(path)


def test_end_to_end_uses_applied_clues_and_refuses_overwrite(tmp_path: Path) -> None:
    database = tmp_path / "v2.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE predictions (variation_id TEXT,variation_sort INTEGER,"
            "old_gene_symbols TEXT,clues_json TEXT,outcome_group TEXT,"
            "predicted_direction TEXT)"
        )
        for index in range(1, 41):
            pathogenic = index % 2
            clues = [
                {
                    "clue": name,
                    "applied": bool(pathogenic) if offset == 0 else False,
                    "points": 999,
                }
                for offset, name in enumerate(FEATURE_NAMES)
            ]
            connection.execute(
                "INSERT INTO predictions VALUES (?,?,?,?,?,?)",
                (
                    str(index),
                    index,
                    f"GENE{index}",
                    json.dumps(clues),
                    "moved_toward_pathogenic" if pathogenic else "moved_toward_benign",
                    "pathogenic_direction" if not pathogenic else "benign_direction",
                ),
            )
    import hashlib

    source_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    config = _config(source_hash)
    config_path = tmp_path / "v3.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    outputs = tmp_path / "outputs"
    summary = run_statistical_model_v3(database, outputs, config_path=config_path)
    assert summary["accuracy"] == 1.0
    model = json.loads((outputs / "model.json").read_text(encoding="utf-8"))
    assert model["coefficients"][FEATURE_NAMES[0]] > 0
    assert set(model["features"]) == set(FEATURE_NAMES)
    with pytest.raises(FileExistsError):
        run_statistical_model_v3(database, outputs, config_path=config_path)
