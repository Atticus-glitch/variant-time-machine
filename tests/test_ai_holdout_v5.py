"""Tests for richer AI Holdout V5."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from variant_time_machine.ai_holdout_v5 import (
    CLUE_NAMES,
    ai_holdout_v5_summary,
    build_fresh_100_partition,
    load_ai_holdout_v5_config,
    train_ai_holdout_v5,
)
from variant_time_machine.ai_holdout_v5 import (
    test_ai_holdout_v5_once as evaluate_hidden_test,
)


def _row(identifier: str, gene: str, target: int) -> dict:
    return {
        "variation_id": identifier,
        "gene_tokens": (gene,),
        "features": (target, *([0] * 13)),
        "target": target,
        "outcome_group": "moved_toward_pathogenic" if target else "moved_toward_benign",
    }


def _previous_manifest(count: int = 100) -> dict:
    return {
        "manifest_sha256": "previous-test-hash",
        "assignments": [
            {
                "variation_id": str(index),
                "group_key": f"gene:GENE{index}",
                "partition": "test",
            }
            for index in range(count)
        ],
    }


def test_fresh_partition_is_exact_label_independent_and_disjoint() -> None:
    rows = [_row(str(index), f"GENE{index}", index % 2) for index in range(260)]
    config = load_ai_holdout_v5_config()
    config["previous_holdout_manifest_sha256"] = "previous-test-hash"
    previous = _previous_manifest()
    first = build_fresh_100_partition(rows, config, previous)
    changed = [{**row, "target": 1 - row["target"]} for row in reversed(rows)]
    second = build_fresh_100_partition(changed, config, previous)
    assert first == second
    assert first["test_count"] == 100
    previous_groups = {item["group_key"] for item in previous["assignments"]}
    test_groups = {
        item["group_key"]
        for item in first["assignments"]
        if item["partition"] == "test"
    }
    assert test_groups.isdisjoint(previous_groups)


def test_v5_training_and_test_remain_separate(tmp_path: Path) -> None:
    database = tmp_path / "v2.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE predictions (variation_id TEXT,variation_sort INTEGER,"
            "old_gene_symbols TEXT,clues_json TEXT,outcome_group TEXT)"
        )
        for index in range(320):
            target = index % 2
            clues = []
            for offset, name in enumerate(CLUE_NAMES):
                clue = {
                    "clue": name,
                    "applied": bool(target) if offset == 0 else False,
                    "older_value": "No core older fields missing",
                    "explanation": (
                        "The classification was last evaluated 100 days before "
                        "the snapshot."
                    ),
                }
                if name == "multiple_agreeing_submitters":
                    clue["older_value"] = "2"
                clues.append(clue)
            connection.execute(
                "INSERT INTO predictions VALUES (?,?,?,?,?)",
                (
                    str(index),
                    index,
                    f"GENE{index}",
                    json.dumps(clues),
                    "moved_toward_pathogenic" if target else "moved_toward_benign",
                ),
            )
    previous = _previous_manifest()
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(previous), encoding="utf-8")
    config = load_ai_holdout_v5_config()
    config["source_database_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    config["previous_holdout_manifest_sha256"] = "previous-test-hash"
    config_path = tmp_path / "v5.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    outputs = tmp_path / "outputs"

    trained = train_ai_holdout_v5(
        database, outputs, previous_path, config_path=config_path
    )
    assert trained["hidden_test_records"] == 100
    assert trained["feature_count"] == 14
    assert ai_holdout_v5_summary(outputs)["state"] == "trained_hidden_test_unopened"
    assert not (outputs / "test_metrics.json").exists()
    metrics = evaluate_hidden_test(database, outputs)
    assert metrics["test_records"] == 100
    assert 0 <= metrics["accuracy"] <= 1
    with pytest.raises(FileExistsError, match="already"):
        evaluate_hidden_test(database, outputs)
