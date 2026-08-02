"""Seal and later evaluate the publicly committed V8 temporal experiment."""

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.ai_holdout_v4 import _sha256
from variant_time_machine.ai_temporal_v7 import _normalised_values, _stream_answers
from variant_time_machine.clue_score import normalize_newer_outcome
from variant_time_machine.config import AI_TEMPORAL_V8_CONFIG_PATH


class AITemporalV8Error(ValueError):
    """Raised when the frozen V8 protocol is violated."""


def load_ai_temporal_v8_config(
    path: Path = AI_TEMPORAL_V8_CONFIG_PATH,
) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AITemporalV8Error(f"Could not load AI Temporal V8: {exc}") from exc
    if config.get("experiment_version") != "AI Temporal V8":
        raise AITemporalV8Error("AI Temporal V8 configuration is invalid.")
    if config.get("status") != "frozen_before_model_development":
        raise AITemporalV8Error("V8 protocol must be frozen before model development.")
    if config.get("test_records") != 1000:
        raise AITemporalV8Error("V8 requires exactly 1,000 sealed test records.")
    return config


def _gene_tokens(value: object) -> set[str]:
    text = unicodedata.normalize("NFKC", str(value or ""))
    for delimiter in (";", "|"):
        text = text.replace(delimiter, ",")
    return {
        item.strip().upper()
        for item in text.split(",")
        if item.strip().upper() not in {"", "-", "NOT PROVIDED"}
    }


def _candidate_components(
    candidate_rows: list[tuple[str, str | None]], development_genes: set[str]
) -> tuple[dict[str, str], set[str]]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    row_tokens: dict[str, set[str]] = {}
    for identifier, gene_symbols in candidate_rows:
        tokens = _gene_tokens(gene_symbols)
        row_tokens[identifier] = tokens
        if tokens:
            first = min(tokens)
            for token in tokens:
                union(first, token)
    components = {
        identifier: find(min(tokens))
        for identifier, tokens in row_tokens.items()
        if tokens
    }
    blocked_roots = {find(token) for token in development_genes if token in parent}
    return components, blocked_roots


def _development_genes(
    development_database: Path,
    predictor_index: Path,
    v7_predictions: Path,
) -> set[str]:
    genes = set()
    with sqlite3.connect(
        f"file:{Path(development_database).resolve()}?mode=ro", uri=True
    ) as connection:
        for (value,) in connection.execute("SELECT old_gene_symbols FROM predictions"):
            genes.update(_gene_tokens(value))
    with sqlite3.connect(
        f"file:{Path(predictor_index).resolve()}?mode=ro", uri=True
    ) as history:
        v7_ids = []
        with Path(v7_predictions).open(encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                v7_ids.append(line.split(",", maxsplit=1)[0])
        for start in range(0, len(v7_ids), 500):
            chunk = v7_ids[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            query = (
                "SELECT gene_symbols FROM variant_release WHERE release_role='newer' "
                f"AND variation_id IN ({placeholders})"
            )
            for (value,) in history.execute(query, chunk):
                genes.update(_gene_tokens(value))
    return genes


def seal_v8_label_vault(
    development_database: Path,
    predictor_index: Path,
    sealed_candidates: Path,
    v7_predictions: Path,
    answer_archive: Path,
    vault_path: Path,
    public_commitment_path: Path,
    *,
    config_path: Path = AI_TEMPORAL_V8_CONFIG_PATH,
) -> dict[str, Any]:
    """Seal V8 membership and labels without returning IDs, labels, or prevalence."""
    paths = [
        Path(development_database).resolve(),
        Path(predictor_index).resolve(),
        Path(sealed_candidates).resolve(),
        Path(v7_predictions).resolve(),
        Path(answer_archive).resolve(),
    ]
    config_path = Path(config_path).resolve()
    vault_path = Path(vault_path).resolve()
    public_commitment_path = Path(public_commitment_path).resolve()
    config = load_ai_temporal_v8_config(config_path)
    if vault_path.exists() or public_commitment_path.exists():
        raise FileExistsError("V8 vault or commitment already exists.")
    expected_hashes = (
        config["development_sources"]["v2_database_sha256"],
        config["predictor_index_sha256"],
        config["sealed_candidate_predictions_sha256"],
        config["development_sources"]["v7_test_predictions_sha256"],
        config["answer_archive_sha256"],
    )
    actual_hashes = tuple(_sha256(path) for path in paths)
    if actual_hashes != expected_hashes:
        raise AITemporalV8Error("A frozen V8 source hash does not match.")

    development_genes = _development_genes(paths[0], paths[1], paths[3])
    with sqlite3.connect(f"file:{paths[2]}?mode=ro", uri=True) as candidates:
        candidate_rows = [
            (str(identifier), gene_symbols)
            for identifier, gene_symbols in candidates.execute(
                "SELECT variation_id,gene_symbols FROM predictions"
            )
        ]
    components, blocked_roots = _candidate_components(candidate_rows, development_genes)
    eligible_predictor_ids = {
        identifier
        for identifier, root in components.items()
        if root not in blocked_roots
    }
    with Path(paths[3]).open(encoding="utf-8") as handle:
        v7_test_ids = {line.split(",", maxsplit=1)[0] for line in list(handle)[1:]}
    eligible_predictor_ids.difference_update(v7_test_ids)

    vault_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=".v8-vault.", dir=vault_path.parent))
    try:
        working = temporary_dir / "answer_working.sqlite3"
        _stream_answers(paths[4], paths[2], working)
        connection = sqlite3.connect(working)
        connection.row_factory = sqlite3.Row
        safe_rows = []
        query = """
            SELECT p.variation_id,p.allele_ids,
                   GROUP_CONCAT(DISTINCT a.allele_id) AS answer_allele_ids,
                   GROUP_CONCAT(DISTINCT a.classification) AS answer_classifications,
                   GROUP_CONCAT(DISTINCT a.origin_simple) AS answer_origins
            FROM predictions AS p JOIN answer_rows AS a USING (variation_id)
            GROUP BY p.variation_id
        """
        for row in connection.execute(query):
            identifier = str(row["variation_id"])
            if identifier not in eligible_predictor_ids:
                continue
            if _normalised_values(row["allele_ids"]) != _normalised_values(
                row["answer_allele_ids"]
            ):
                continue
            if _normalised_values(row["answer_origins"]) != {"germline"}:
                continue
            classifications = _normalised_values(row["answer_classifications"])
            if len(classifications) != 1:
                continue
            classification = next(iter(classifications))
            outcome = normalize_newer_outcome(classification)
            if not outcome.scorable or outcome.group not in {
                "moved_toward_benign",
                "moved_toward_pathogenic",
            }:
                continue
            safe_rows.append(
                (
                    identifier,
                    outcome.group,
                    classification,
                    hashlib.sha256(components[identifier].encode()).hexdigest(),
                )
            )
        connection.close()
        if len(safe_rows) < 1000:
            raise AITemporalV8Error(
                f"Only {len(safe_rows)} fully isolated outcomes are available."
            )
        salt = config["vault_salt"]
        selected = sorted(
            safe_rows,
            key=lambda row: hashlib.sha256(f"{salt}:{row[0]}".encode()).hexdigest(),
        )[:1000]
        temporary_vault = temporary_dir / "label_vault.sqlite3"
        vault = sqlite3.connect(temporary_vault)
        vault.executescript(
            """
            CREATE TABLE labels (
                variation_id TEXT PRIMARY KEY,
                actual_outcome TEXT NOT NULL,
                answer_classification TEXT NOT NULL,
                component_hash TEXT NOT NULL
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        vault.executemany("INSERT INTO labels VALUES (?,?,?,?)", selected)
        vault.execute(
            "INSERT INTO metadata VALUES (?,?)",
            ("config_sha256", _sha256(config_path)),
        )
        vault.commit()
        vault.execute("VACUUM")
        vault.close()
        temporary_vault.replace(vault_path)
        commitment = {
            "schema_version": 1,
            "experiment_version": config["experiment_version"],
            "state": "label_vault_sealed_before_v8_model_development",
            "sealed_at_utc": datetime.now(UTC).isoformat(),
            "test_records": 1000,
            "eligible_safe_gene_disjoint_records": len(safe_rows),
            "eligible_gene_components": len({row[3] for row in safe_rows}),
            "development_test_variation_id_overlap": 0,
            "development_test_gene_component_overlap": 0,
            "v7_test_id_overlap": 0,
            "config_sha256": _sha256(config_path),
            "vault_sha256": _sha256(vault_path),
            "source_hashes": {
                "development_database": actual_hashes[0],
                "predictor_index": actual_hashes[1],
                "sealed_candidates": actual_hashes[2],
                "v7_test_predictions": actual_hashes[3],
                "answer_archive": actual_hashes[4],
            },
            "membership_and_labels_disclosed": False,
            "warning": config["design_warning"],
        }
        public_commitment_path.parent.mkdir(parents=True, exist_ok=True)
        public_commitment_path.write_text(
            json.dumps(commitment, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)
    return commitment
