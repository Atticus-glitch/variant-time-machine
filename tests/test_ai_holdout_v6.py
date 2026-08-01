"""Tests for the 1,000-record AI Holdout V6 contract."""

import copy
import json
from pathlib import Path

import pytest

from variant_time_machine.ai_holdout_v4 import _document_hash
from variant_time_machine.ai_holdout_v6 import (
    AIHoldoutV6Error,
    build_fresh_1000_partition,
    load_ai_holdout_v6_config,
)

ROOT = Path(__file__).resolve().parents[1]


def _row(identifier: int, target: int) -> dict:
    return {
        "variation_id": str(identifier),
        "gene_tokens": (f"GENE{identifier}",),
        "features": (target, *([0] * 13)),
        "target": target,
        "outcome_group": "moved_toward_pathogenic" if target else "moved_toward_benign",
    }


def _previous_manifest(start: int, count: int = 100) -> dict:
    manifest = {
        "assignments": [
            {
                "variation_id": str(index),
                "group_key": f"gene:GENE{index}",
                "partition": "test",
            }
            for index in range(start, start + count)
        ]
    }
    manifest["manifest_sha256"] = _document_hash(manifest)
    return manifest


def _contract() -> tuple[dict, dict[str, dict]]:
    config = load_ai_holdout_v6_config()
    manifests = {"V4": _previous_manifest(0), "V5": _previous_manifest(100)}
    config["previous_holdout_manifest_sha256"] = {
        model_id: manifest["manifest_sha256"]
        for model_id, manifest in manifests.items()
    }
    return config, manifests


def test_v6_partition_is_exact_label_independent_and_group_isolated() -> None:
    rows = [_row(index, index % 2) for index in range(1600)]
    config, manifests = _contract()
    first = build_fresh_1000_partition(rows, config, manifests)
    changed = [{**row, "target": 1 - row["target"]} for row in reversed(rows)]
    second = build_fresh_1000_partition(changed, config, manifests)
    assert first == second
    assert first["test_count"] == 1000
    assert first["train_count"] == 400
    assert first["prior_holdout_excluded_count"] == 200
    assert set(first["overlap_checks"].values()) == {0}

    assignments = first["assignments"]
    train = {
        item["variation_id"] for item in assignments if item["partition"] == "train"
    }
    test = {item["variation_id"] for item in assignments if item["partition"] == "test"}
    assert train.isdisjoint(test)
    assert train.isdisjoint({str(index) for index in range(200)})
    assert test.isdisjoint({str(index) for index in range(200)})


def test_v6_rejects_modified_previous_manifest() -> None:
    rows = [_row(index, index % 2) for index in range(1600)]
    config, manifests = _contract()
    changed = copy.deepcopy(manifests)
    changed["V5"]["assignments"][0]["group_key"] = "gene:CHANGED"
    with pytest.raises(AIHoldoutV6Error, match="V5 manifest"):
        build_fresh_1000_partition(rows, config, changed)


def test_v6_requires_one_thousand_fresh_groups() -> None:
    rows = [_row(index, index % 2) for index in range(1100)]
    config, manifests = _contract()
    with pytest.raises(AIHoldoutV6Error, match="fresh groups"):
        build_fresh_1000_partition(rows, config, manifests)


def test_frozen_v6_test_is_absent_from_training_and_prior_tests() -> None:
    manifest = json.loads(
        (ROOT / "outputs/ai_holdout_v6/partition_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    by_partition = {
        name: {
            item["variation_id"]
            for item in manifest["assignments"]
            if item["partition"] == name
        }
        for name in ("train", "test", "quarantine", "prior_holdout_excluded")
    }
    assert len(by_partition["test"]) == 1000
    assert len(by_partition["train"]) == 2518
    assert by_partition["train"].isdisjoint(by_partition["test"])
    assert all(
        by_partition[left].isdisjoint(by_partition[right])
        for index, left in enumerate(by_partition)
        for right in tuple(by_partition)[index + 1 :]
    )

    assignment_by_id = {item["variation_id"]: item for item in manifest["assignments"]}
    prior_test_ids = set()
    prior_test_groups = set()
    for model_id in ("v4", "v5"):
        prior = json.loads(
            (ROOT / f"outputs/ai_holdout_{model_id}/partition_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        prior_test_ids.update(
            item["variation_id"]
            for item in prior["assignments"]
            if item["partition"] == "test"
        )
        prior_test_groups.update(
            item["group_key"]
            for item in prior["assignments"]
            if item["partition"] == "test"
        )
    assert by_partition["train"].isdisjoint(prior_test_ids)
    assert by_partition["test"].isdisjoint(prior_test_ids)
    assert {
        assignment_by_id[identifier]["group_key"]
        for identifier in by_partition["train"] | by_partition["test"]
    }.isdisjoint(prior_test_groups)
