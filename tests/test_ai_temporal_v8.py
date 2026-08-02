"""Tests for the publicly committed V8 label-vault protocol."""

from variant_time_machine.ai_temporal_v8 import (
    _candidate_components,
    _gene_tokens,
    load_ai_temporal_v8_config,
)


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
