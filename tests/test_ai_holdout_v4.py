"""Tests for the exactly-100-record neural-network holdout."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from variant_time_machine.ai_holdout_v4 import (
    FEATURE_NAMES,
    ai_holdout_v4_summary,
    build_100_record_partition,
    load_ai_holdout_v4_config,
    train_ai_holdout_v4,
)
from variant_time_machine.ai_holdout_v4 import (
    test_ai_holdout_v4_once as evaluate_hidden_test,
)


def _row(identifier: str, gene: str, target: int) -> dict:
    return {
        "variation_id": identifier,
        "gene_tokens": (gene,),
        "features": (target, *([0] * (len(FEATURE_NAMES) - 1))),
        "target": target,
        "outcome_group": "moved_toward_pathogenic" if target else "moved_toward_benign",
        "v2_predicted_direction": "no_prediction",
    }


def test_partition_selects_exactly_100_without_using_labels() -> None:
    rows = [_row(str(index), f"GENE{index}", index % 2) for index in range(150)]
    config = load_ai_holdout_v4_config()
    first = build_100_record_partition(rows, config)
    changed = [{**row, "target": 1 - row["target"]} for row in reversed(rows)]
    second = build_100_record_partition(changed, config)
    assert first == second
    assert first["test_count"] == 100
    assert first["train_count"] == 50
    assert first["quarantine_count"] == 0
    train_groups = {
        row["group_key"] for row in first["assignments"] if row["partition"] == "train"
    }
    test_groups = {
        row["group_key"] for row in first["assignments"] if row["partition"] == "test"
    }
    assert train_groups.isdisjoint(test_groups)


def test_training_keeps_hidden_test_unopened_until_one_time_evaluation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v2.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE predictions (variation_id TEXT,variation_sort INTEGER,"
            "old_gene_symbols TEXT,clues_json TEXT,outcome_group TEXT,"
            "predicted_direction TEXT)"
        )
        for index in range(240):
            target = index % 2
            clues = [
                {"clue": name, "applied": bool(target) if offset == 0 else False}
                for offset, name in enumerate(FEATURE_NAMES)
            ]
            connection.execute(
                "INSERT INTO predictions VALUES (?,?,?,?,?,?)",
                (
                    str(index),
                    index,
                    f"GENE{index}",
                    json.dumps(clues),
                    "moved_toward_pathogenic" if target else "moved_toward_benign",
                    "no_prediction",
                ),
            )
    config = load_ai_holdout_v4_config()
    config["source_database_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    config_path = tmp_path / "v4.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    outputs = tmp_path / "outputs"

    trained = train_ai_holdout_v4(database, outputs, config_path=config_path)
    assert trained["hidden_test_records"] == 100
    assert trained["state"] == "trained_hidden_test_unopened"
    assert not (outputs / "test_metrics.json").exists()
    assert ai_holdout_v4_summary(outputs)["state"] == "trained_hidden_test_unopened"

    metrics = evaluate_hidden_test(database, outputs)
    assert metrics["test_records"] == 100
    assert 0 <= metrics["accuracy"] <= 1
    assert ai_holdout_v4_summary(outputs)["state"] == "tested"
    with pytest.raises(FileExistsError, match="already"):
        evaluate_hidden_test(database, outputs)
