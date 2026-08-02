"""Tests for the publicly committed V8 label-vault protocol."""

import json
import sqlite3
from pathlib import Path

import pytest

from variant_time_machine import ai_temporal_v8
from variant_time_machine.ai_holdout_v4 import _sha256
from variant_time_machine.ai_temporal_v8 import (
    V8_FEATURE_NAMES,
    AITemporalV8Error,
    _candidate_components,
    _gene_tokens,
    _missense_features,
    evaluate_v8_once,
    load_ai_temporal_v8_config,
    v8_features,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v8_protocol_is_frozen_before_model_development() -> None:
    config = load_ai_temporal_v8_config()
    assert config["status"] == "frozen_before_model_development"
    assert config["test_records"] == 1000
    assert config["primary_metric"] == "balanced_accuracy"
    assert "transitively" in config["test_rule"]
    assert "gene_identity" in config["feature_policy"]["forbidden"]


def test_v8_gene_normalization_is_conservative() -> None:
    assert _gene_tokens(" brca1;TP53| Not Provided,- ") == {"BRCA1", "TP53"}
    assert _gene_tokens(None) == set()


def test_v8_components_block_transitive_development_connections() -> None:
    rows = [
        ("1", "GENEA"),
        ("2", "GENEA;GENEB"),
        ("3", "GENEB;GENEC"),
        ("4", "GENED"),
        ("5", None),
    ]
    components, blocked = _candidate_components(rows, {"GENEA"})
    assert components["1"] == components["2"] == components["3"]
    assert components["1"] in blocked
    assert components["4"] not in blocked
    assert "5" not in components


def test_v8_features_include_predictor_only_missense_chemistry() -> None:
    row = {
        "names": "NM_000001.1:c.100G>A (p.Ala34Val)",
        "variant_types": "single nucleotide variant",
        "review_statuses": "criteria provided, single submitter",
        "submitter_counts": "1",
        "last_evaluated_dates": "Jan 01, 2022",
        "rcv_accessions": "RCV000000001",
        "assemblies": "GRCh37,GRCh38",
        "coordinates": "GRCh38:1:100-100 A>G",
        "source_row_count": 2,
        "gene_symbols": "GENE1",
        "phenotype_ids": "MONDO:1",
    }
    features = v8_features(row, "2024-01-04")
    assert len(features) == len(V8_FEATURE_NAMES) == 64
    assert features[V8_FEATURE_NAMES.index("consequence_missense")] == 1
    assert features[V8_FEATURE_NAMES.index("missense_chemistry_available")] == 1
    assert features[V8_FEATURE_NAMES.index("absolute_hydropathy_change")] > 0


def test_v8_unknown_missense_chemistry_has_explicit_missing_flag() -> None:
    assert _missense_features("not protein HGVS") == (0.0,) * 16


def test_v8_model_commitment_keeps_vault_unopened() -> None:
    commitment = json.loads(
        (ROOT / "outputs/evaluations/frozen/v8_model_commitment.json").read_text(
            encoding="utf-8"
        )
    )
    assert commitment["state"] == "model_and_predictions_sealed_vault_unopened"
    assert commitment["vault_accessed_during_development"] is False
    assert commitment["development_records"] == 9818
    assert commitment["feature_count"] == len(V8_FEATURE_NAMES) == 64
    assert commitment["eligible_candidate_predictions"] == 378552


def test_v8_evaluation_refuses_a_changed_vault(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs/ai_temporal_v8"
    output_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "ai_temporal_v8.yaml").write_text(
        json.dumps(load_ai_temporal_v8_config()), encoding="utf-8"
    )
    vault = output_dir / "label_vault.sqlite3"
    vault.write_bytes(b"changed vault")
    vault_commitment = tmp_path / "vault.json"
    vault_commitment.write_text(
        json.dumps({"vault_sha256": "0" * 64}), encoding="utf-8"
    )
    model_commitment = tmp_path / "model.json"
    model_commitment.write_text("{}", encoding="utf-8")

    with pytest.raises(AITemporalV8Error, match="vault hash does not match"):
        evaluate_v8_once(output_dir, vault, vault_commitment, model_commitment)


def test_v8_evaluation_refuses_second_open(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs/ai_temporal_v8"
    output_dir.mkdir(parents=True)
    (output_dir / "test_metrics.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already evaluated"):
        evaluate_v8_once(
            output_dir,
            output_dir / "label_vault.sqlite3",
            tmp_path / "vault.json",
            tmp_path / "model.json",
        )


def test_v8_evaluation_refuses_after_a_started_marker(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs/ai_temporal_v8"
    output_dir.mkdir(parents=True)
    (output_dir / "evaluation_started.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already evaluated"):
        evaluate_v8_once(
            output_dir,
            output_dir / "label_vault.sqlite3",
            tmp_path / "vault.json",
            tmp_path / "model.json",
        )


def test_v8_evaluation_cross_binds_and_publishes_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs/ai_temporal_v8"
    output_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "ai_temporal_v8.yaml"
    config = load_ai_temporal_v8_config()
    config_path.write_text(json.dumps(config), encoding="utf-8")
    config_hash = _sha256(config_path)

    prediction_path = output_dir / "sealed_candidate_predictions.sqlite3"
    with sqlite3.connect(prediction_path) as connection:
        connection.execute(
            """
            CREATE TABLE predictions (
                variation_id TEXT PRIMARY KEY, gene_symbols TEXT NOT NULL,
                component_hash TEXT NOT NULL, consequence TEXT NOT NULL,
                v8_probability REAL NOT NULL, v8_prediction TEXT NOT NULL,
                v7_probability REAL NOT NULL, v7_prediction TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    str(index),
                    f"GENE{index % 10}",
                    f"component-{index % 10}",
                    "missense" if index % 3 else "noncoding",
                    0.8 if index % 2 else 0.2,
                    "pathogenic" if index % 2 else "benign",
                    0.2 if index % 2 else 0.8,
                    "benign" if index % 2 else "pathogenic",
                )
                for index in range(1, 1001)
            ],
        )

    vault_path = output_dir / "label_vault.sqlite3"
    with sqlite3.connect(vault_path) as connection:
        connection.executescript(
            """
            CREATE TABLE labels (
                variation_id TEXT PRIMARY KEY, actual_outcome TEXT NOT NULL,
                answer_classification TEXT NOT NULL,
                component_hash TEXT NOT NULL
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        connection.executemany(
            "INSERT INTO labels VALUES (?,?,?,?)",
            [
                (
                    str(index),
                    "moved_toward_pathogenic" if index % 2 else "moved_toward_benign",
                    "Pathogenic" if index % 2 else "Benign",
                    f"component-{index % 10}",
                )
                for index in range(1, 1001)
            ],
        )
        connection.execute(
            "INSERT INTO metadata VALUES (?,?)", ("config_sha256", config_hash)
        )

    model_path = output_dir / "model.joblib"
    model_path.write_bytes(b"sealed model")
    source_hashes = {
        "development_database": "a" * 64,
        "predictor_index": "b" * 64,
        "sealed_candidates": "c" * 64,
        "v7_test_predictions": "d" * 64,
    }
    vault_commitment_path = tmp_path / "vault.json"
    vault_commitment_path.write_text(
        json.dumps(
            {
                "experiment_version": config["experiment_version"],
                "state": "label_vault_sealed_before_v8_model_development",
                "test_records": 1000,
                "development_test_variation_id_overlap": 0,
                "development_test_gene_component_overlap": 0,
                "v7_test_id_overlap": 0,
                "config_sha256": config_hash,
                "vault_sha256": _sha256(vault_path),
                "source_hashes": {**source_hashes, "answer_archive": "e" * 64},
            }
        ),
        encoding="utf-8",
    )
    model_commitment_path = tmp_path / "model.json"
    model_commitment_path.write_text(
        json.dumps(
            {
                "experiment_version": config["experiment_version"],
                "state": "model_and_predictions_sealed_vault_unopened",
                "vault_accessed_during_development": False,
                "config_sha256": config_hash,
                "model_sha256": _sha256(model_path),
                "sealed_predictions_sha256": _sha256(prediction_path),
                "source_hashes": source_hashes,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ai_temporal_v8,
        "_component_bootstrap",
        lambda rows: {"synthetic_interval": [0.0, 1.0]},
    )

    metrics = evaluate_v8_once(
        output_dir, vault_path, vault_commitment_path, model_commitment_path
    )

    assert metrics["test_records"] == 1000
    assert metrics["balanced_accuracy"] == 1.0
    assert metrics["missense_only"]["records"] > 0
    assert (output_dir / "test_metrics.json").is_file()
    assert (output_dir / "temporal_test_predictions.csv").is_file()
    marker = json.loads(
        (output_dir / "evaluation_started.json").read_text(encoding="utf-8")
    )
    assert marker["state"] == "evaluation_completed"
