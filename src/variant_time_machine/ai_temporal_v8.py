"""Seal and later evaluate the publicly committed V8 temporal experiment."""

import csv
import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from variant_time_machine.ai_holdout_v4 import _sha256
from variant_time_machine.ai_temporal_v7 import (
    _calibrated_probabilities,
    _features_from_predictor_row,
    _normalised_values,
    _stream_answers,
)
from variant_time_machine.clue_score import (
    _classification_age,
    _consequence,
    _max_submitters,
    load_clue_score_config,
    normalize_newer_outcome,
)
from variant_time_machine.config import (
    AI_TEMPORAL_V7_RESULTS_DIR,
    AI_TEMPORAL_V8_CONFIG_PATH,
)
from variant_time_machine.model_registry import compute_binary_metrics
from variant_time_machine.statistical_model_v3 import _connected_group_keys


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


CONSEQUENCES = (
    "loss_of_function",
    "canonical_splice",
    "missense",
    "synonymous",
    "inframe_indel",
    "noncoding",
    "unrecognized",
)
VARIANT_TYPES = (
    "single nucleotide variant",
    "deletion",
    "duplication",
    "insertion",
    "indel",
    "microsatellite",
    "copy number gain",
    "copy number loss",
    "inversion",
    "other",
)
REVIEW_TYPES = (
    "criteria provided, single submitter",
    "criteria provided, multiple submitters, no conflicts",
    "criteria provided, conflicting interpretations",
    "no assertion criteria provided",
    "no assertion provided",
    "reviewed by expert panel",
    "other",
)
AMINO_ACIDS = {
    "Ala": ("A", 1.8, 89.09, "nonpolar"),
    "Arg": ("R", -4.5, 174.20, "positive"),
    "Asn": ("N", -3.5, 132.12, "polar"),
    "Asp": ("D", -3.5, 133.10, "negative"),
    "Cys": ("C", 2.5, 121.16, "polar"),
    "Gln": ("Q", -3.5, 146.15, "polar"),
    "Glu": ("E", -3.5, 147.13, "negative"),
    "Gly": ("G", -0.4, 75.07, "nonpolar"),
    "His": ("H", -3.2, 155.16, "positive"),
    "Ile": ("I", 4.5, 131.18, "nonpolar"),
    "Leu": ("L", 3.8, 131.18, "nonpolar"),
    "Lys": ("K", -3.9, 146.19, "positive"),
    "Met": ("M", 1.9, 149.21, "nonpolar"),
    "Phe": ("F", 2.8, 165.19, "nonpolar"),
    "Pro": ("P", -1.6, 115.13, "nonpolar"),
    "Ser": ("S", -0.8, 105.09, "polar"),
    "Thr": ("T", -0.7, 119.12, "polar"),
    "Trp": ("W", -0.9, 204.23, "nonpolar"),
    "Tyr": ("Y", -1.3, 181.19, "polar"),
    "Val": ("V", 4.2, 117.15, "nonpolar"),
}
V8_FEATURE_NAMES = (
    *(f"consequence_{value}" for value in CONSEQUENCES),
    *(f"variant_type_{value.replace(' ', '_')}" for value in VARIANT_TYPES),
    *(f"review_{value.replace(' ', '_').replace(',', '')}" for value in REVIEW_TYPES),
    "criteria_supplied",
    "multiple_submitters_no_conflict",
    "conflicting_interpretations",
    "expert_panel",
    "log1p_submitter_count",
    "log1p_evaluation_age_days",
    "evaluation_age_missing",
    "log1p_rcv_count",
    "multiple_rcvs",
    "log1p_source_row_count",
    "assembly_count",
    "coordinate_parse_available",
    "log1p_coordinate_span",
    "point_variant",
    "protein_hgvs_present",
    "coding_hgvs_present",
    "intronic_hgvs_present",
    "hgvs_deletion",
    "hgvs_duplication",
    "hgvs_insertion",
    "canonical_splice_text",
    "missense_chemistry_available",
    "absolute_hydropathy_change",
    "signed_hydropathy_change",
    "absolute_residue_mass_change_scaled",
    "charge_gain",
    "charge_loss",
    "charge_reversal",
    "polarity_change",
    "aromatic_gain",
    "aromatic_loss",
    "glycine_gain",
    "glycine_loss",
    "proline_gain",
    "proline_loss",
    "cysteine_gain",
    "cysteine_loss",
    "missing_gene",
    "missing_phenotype_ids",
    "missing_coordinate",
)


def _category(value: object, allowed: tuple[str, ...]) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned if cleaned in allowed[:-1] else "other"


def _missense_features(names: object) -> tuple[float, ...]:
    match = re.search(
        r"p\.\(?([A-Z][a-z]{2})(?:\d+)([A-Z][a-z]{2})\)?", str(names or "")
    )
    if (
        not match
        or match.group(1) not in AMINO_ACIDS
        or match.group(2) not in AMINO_ACIDS
    ):
        return (0.0,) * 16
    reference = AMINO_ACIDS[match.group(1)]
    alternate = AMINO_ACIDS[match.group(2)]
    ref_code, ref_hydropathy, ref_mass, ref_class = reference
    alt_code, alt_hydropathy, alt_mass, alt_class = alternate
    charge = {"negative": -1, "positive": 1}
    ref_charge = charge.get(ref_class, 0)
    alt_charge = charge.get(alt_class, 0)
    aromatic = {"F", "W", "Y", "H"}
    return (
        1.0,
        abs(alt_hydropathy - ref_hydropathy),
        alt_hydropathy - ref_hydropathy,
        abs(alt_mass - ref_mass) / 100,
        float(alt_charge > ref_charge),
        float(alt_charge < ref_charge),
        float(ref_charge * alt_charge == -1),
        float((ref_class == "polar") != (alt_class == "polar")),
        float(ref_code not in aromatic and alt_code in aromatic),
        float(ref_code in aromatic and alt_code not in aromatic),
        float(ref_code != "G" and alt_code == "G"),
        float(ref_code == "G" and alt_code != "G"),
        float(ref_code != "P" and alt_code == "P"),
        float(ref_code == "P" and alt_code != "P"),
        float(ref_code != "C" and alt_code == "C"),
        float(ref_code == "C" and alt_code != "C"),
    )


def v8_features(row: Mapping[str, Any], snapshot_date: str) -> tuple[float, ...]:
    """Build the preregistered V8 predictor-only tabular features."""
    names = str(row.get("names") or "")
    consequence = _consequence(names)
    variant_type = _category(row.get("variant_types"), VARIANT_TYPES)
    review = _category(row.get("review_statuses"), REVIEW_TYPES)
    review_text = str(row.get("review_statuses") or "").lower()
    submitters = _max_submitters(str(row.get("submitter_counts") or "")) or 0
    age_days, _ = _classification_age(row.get("last_evaluated_dates"), snapshot_date)
    rcv_count = len(set(re.findall(r"RCV\d+", str(row.get("rcv_accessions") or ""))))
    assemblies = {
        value.strip()
        for value in str(row.get("assemblies") or "").split(",")
        if value.strip()
    }
    coordinate_matches = re.findall(
        r":(\d+)-(\d+)(?:\s|$)", str(row.get("coordinates") or "")
    )
    spans = [abs(int(stop) - int(start)) + 1 for start, stop in coordinate_matches]
    span = min(spans) if spans else 0
    criteria = review_text.startswith("criteria provided")
    conflict = "conflict" in review_text and "no conflicts" not in review_text
    values = [float(consequence == item) for item in CONSEQUENCES]
    values.extend(float(variant_type == item) for item in VARIANT_TYPES)
    values.extend(float(review == item) for item in REVIEW_TYPES)
    values.extend(
        (
            float(criteria),
            float("multiple submitters, no conflicts" in review_text),
            float(conflict),
            float(review == "reviewed by expert panel"),
            math.log1p(submitters),
            math.log1p(age_days or 0),
            float(age_days is None),
            math.log1p(rcv_count),
            float(rcv_count > 1),
            math.log1p(int(row.get("source_row_count") or 0)),
            float(len(assemblies)),
            float(bool(spans)),
            math.log1p(span),
            float(span == 1),
            float("p." in names),
            float("c." in names),
            float(bool(re.search(r"c\.[^\s,;]*(?:\+|-)\d+", names))),
            float("del" in names.lower()),
            float("dup" in names.lower()),
            float("ins" in names.lower()),
            float(
                bool(re.search(r"(?:\+|-)(?:1|2)(?:[A-Z]>[A-Z]|_|del|dup|ins)", names))
            ),
        )
    )
    values.extend(_missense_features(names))
    values.extend(
        (
            float(not _gene_tokens(row.get("gene_symbols"))),
            float(not str(row.get("phenotype_ids") or "").strip()),
            float(not str(row.get("coordinates") or "").strip()),
        )
    )
    if len(values) != len(V8_FEATURE_NAMES):
        raise AITemporalV8Error("V8 feature construction length changed.")
    return tuple(values)


def _load_development(
    development_database: Path,
    predictor_index: Path,
    v7_predictions: Path,
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    labels: dict[str, tuple[int, str]] = {}
    with sqlite3.connect(
        f"file:{Path(development_database).resolve()}?mode=ro", uri=True
    ) as connection:
        for identifier, outcome in connection.execute(
            "SELECT variation_id,outcome_group FROM predictions"
        ):
            labels[str(identifier)] = (
                int(outcome == "moved_toward_pathogenic"),
                "older",
            )
    with Path(v7_predictions).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            labels[row["variation_id"]] = (
                int(row["actual_outcome"] == "moved_toward_pathogenic"),
                "newer",
            )
    raw_rows: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(
        f"file:{Path(predictor_index).resolve()}?mode=ro", uri=True
    ) as connection:
        connection.row_factory = sqlite3.Row
        by_role = {
            role: [
                identifier for identifier, (_, value) in labels.items() if value == role
            ]
            for role in ("older", "newer")
        }
        for role, identifiers in by_role.items():
            for start in range(0, len(identifiers), 500):
                chunk = identifiers[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                query = (
                    "SELECT * FROM variant_release WHERE release_role=? "
                    f"AND variation_id IN ({placeholders})"
                )
                for row in connection.execute(query, (role, *chunk)):
                    raw_rows[str(row["variation_id"])] = dict(row)
    if set(raw_rows) != set(labels):
        raise AITemporalV8Error("V8 development predictors are incomplete.")
    ordered_ids = sorted(labels, key=int)
    records = []
    targets = []
    features = []
    for identifier in ordered_ids:
        target, role = labels[identifier]
        row = raw_rows[identifier]
        snapshot_date = "2022-01-06" if role == "older" else "2024-01-04"
        tokens = _gene_tokens(row.get("gene_symbols")) or {f"variation:{identifier}"}
        records.append(
            {
                "variation_id": identifier,
                "gene_tokens": tuple(sorted(tokens)),
                "development_era": role,
            }
        )
        targets.append(target)
        features.append(v8_features(row, snapshot_date))
    group_keys = _connected_group_keys(records)
    groups = np.asarray([group_keys[identifier] for identifier in ordered_ids])
    counts = {group: int((groups == group).sum()) for group in set(groups)}
    weights = np.asarray([1 / counts[group] for group in groups], dtype=float)
    return (
        records,
        np.asarray(features, dtype=float),
        np.asarray(targets, dtype=int),
        groups,
        weights,
    )


def _estimators(config: Mapping[str, Any]) -> list[tuple[str, Any, int]]:
    seed = int(config["development"]["random_state"])
    values = []
    logistic = config["candidate_models"]["elastic_net_logistic"]
    for c_value in logistic["C"]:
        for ratio in logistic["l1_ratio"]:
            values.append(
                (
                    f"logistic_C_{c_value:g}_l1_{ratio:g}",
                    Pipeline(
                        (
                            ("scale", StandardScaler()),
                            (
                                "model",
                                LogisticRegression(
                                    C=float(c_value),
                                    l1_ratio=float(ratio),
                                    penalty="elasticnet",
                                    solver="saga",
                                    class_weight="balanced",
                                    max_iter=5000,
                                    random_state=seed,
                                ),
                            ),
                        )
                    ),
                    0,
                )
            )
    for item in config["candidate_models"]["hist_gradient_boosting"]:
        values.append(
            (
                f"histgb_leaf_{item['max_leaf_nodes']}_l2_{item['l2_regularization']:g}",
                HistGradientBoostingClassifier(
                    max_leaf_nodes=int(item["max_leaf_nodes"]),
                    learning_rate=float(item["learning_rate"]),
                    l2_regularization=float(item["l2_regularization"]),
                    max_iter=300,
                    class_weight="balanced",
                    random_state=seed,
                ),
                1,
            )
        )
    return values


def _fit_model(
    estimator: Any, features: np.ndarray, targets: np.ndarray, weights: np.ndarray
):
    if isinstance(estimator, Pipeline):
        return estimator.fit(features, targets, model__sample_weight=weights)
    return estimator.fit(features, targets, sample_weight=weights)


def _weighted_balanced_accuracy(
    targets: np.ndarray, predictions: np.ndarray, weights: np.ndarray
) -> float:
    recalls = []
    for label in (0, 1):
        selected = targets == label
        recalls.append(
            float(np.sum(weights[selected] * (predictions[selected] == label)))
            / float(np.sum(weights[selected]))
        )
    return sum(recalls) / 2


def _choose_candidate(results: list[dict[str, Any]]) -> str:
    best = max(item["score"] for item in results)
    eligible = [item for item in results if item["score"] >= best - 0.005]
    return min(eligible, key=lambda item: (item["complexity"], -item["score"]))["name"]


def _oof_predictions(
    estimator: Any,
    features: np.ndarray,
    targets: np.ndarray,
    groups: np.ndarray,
    weights: np.ndarray,
    folds: int,
    seed: int,
) -> tuple[np.ndarray, list[float]]:
    probabilities = np.zeros(len(targets), dtype=float)
    scores = []
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train_indices, validation_indices in splitter.split(features, targets, groups):
        fitted = _fit_model(
            clone(estimator),
            features[train_indices],
            targets[train_indices],
            weights[train_indices],
        )
        probabilities[validation_indices] = fitted.predict_proba(
            features[validation_indices]
        )[:, 1]
        scores.append(
            _weighted_balanced_accuracy(
                targets[validation_indices],
                probabilities[validation_indices] >= 0.5,
                weights[validation_indices],
            )
        )
    return probabilities, scores


def _select_threshold(
    targets: np.ndarray, probabilities: np.ndarray, weights: np.ndarray
) -> float:
    results = []
    for threshold in np.arange(0.2, 0.8001, 0.005):
        results.append(
            (
                _weighted_balanced_accuracy(
                    targets, probabilities >= threshold, weights
                ),
                -abs(threshold - 0.5),
                -threshold,
                threshold,
            )
        )
    return float(max(results)[-1])


def _select_v8_model(
    features: np.ndarray,
    targets: np.ndarray,
    groups: np.ndarray,
    weights: np.ndarray,
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = _estimators(config)
    by_name = {
        name: (estimator, complexity) for name, estimator, complexity in candidates
    }
    seed = int(config["development"]["random_state"])
    outer = StratifiedGroupKFold(
        n_splits=int(config["development"]["outer_folds"]),
        shuffle=True,
        random_state=seed,
    )
    nested_probabilities = np.zeros(len(targets), dtype=float)
    outer_selections = []
    for fold_index, (outer_train, outer_validation) in enumerate(
        outer.split(features, targets, groups)
    ):
        inner_results = []
        for name, estimator, complexity in candidates:
            probabilities, _ = _oof_predictions(
                estimator,
                features[outer_train],
                targets[outer_train],
                groups[outer_train],
                weights[outer_train],
                int(config["development"]["inner_folds"]),
                seed + fold_index + 1,
            )
            inner_results.append(
                {
                    "name": name,
                    "score": _weighted_balanced_accuracy(
                        targets[outer_train],
                        probabilities >= 0.5,
                        weights[outer_train],
                    ),
                    "complexity": complexity,
                }
            )
        chosen = _choose_candidate(inner_results)
        fitted = _fit_model(
            clone(by_name[chosen][0]),
            features[outer_train],
            targets[outer_train],
            weights[outer_train],
        )
        nested_probabilities[outer_validation] = fitted.predict_proba(
            features[outer_validation]
        )[:, 1]
        outer_selections.append(chosen)

    full_results = []
    candidate_oof = {}
    for name, estimator, complexity in candidates:
        probabilities, fold_scores = _oof_predictions(
            estimator,
            features,
            targets,
            groups,
            weights,
            int(config["development"]["outer_folds"]),
            seed,
        )
        score = _weighted_balanced_accuracy(targets, probabilities >= 0.5, weights)
        candidate_oof[name] = probabilities
        full_results.append(
            {
                "name": name,
                "score": score,
                "fold_scores": fold_scores,
                "complexity": complexity,
            }
        )
    selected_name = _choose_candidate(full_results)
    selected_estimator = by_name[selected_name][0]
    raw_oof = np.clip(candidate_oof[selected_name], 1e-6, 1 - 1e-6)
    logits = np.log(raw_oof / (1 - raw_oof)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1_000_000, max_iter=3000).fit(
        logits, targets, sample_weight=weights
    )
    calibrated_oof = calibrator.predict_proba(logits)[:, 1]
    threshold = _select_threshold(targets, calibrated_oof, weights)
    final_model = _fit_model(clone(selected_estimator), features, targets, weights)
    summary = {
        "selected_model": selected_name,
        "selected_threshold": threshold,
        "candidate_results": full_results,
        "nested_outer_selections": outer_selections,
        "nested_balanced_accuracy_at_0_5": _weighted_balanced_accuracy(
            targets, nested_probabilities >= 0.5, weights
        ),
        "selected_calibrated_oof_balanced_accuracy": _weighted_balanced_accuracy(
            targets, calibrated_oof >= threshold, weights
        ),
        "selected_calibrated_oof_roc_auc": float(
            roc_auc_score(targets, calibrated_oof, sample_weight=weights)
        ),
        "selected_calibrated_oof_brier": float(
            brier_score_loss(targets, calibrated_oof, sample_weight=weights)
        ),
    }
    return {
        "base_model": final_model,
        "calibrator": calibrator,
        "threshold": threshold,
        "feature_names": V8_FEATURE_NAMES,
    }, summary


def develop_and_seal_v8_predictions(
    development_database: Path,
    predictor_index: Path,
    v7_predictions: Path,
    sealed_candidates: Path,
    output_dir: Path,
    public_model_commitment_path: Path,
    *,
    config_path: Path = AI_TEMPORAL_V8_CONFIG_PATH,
    v7_model_dir: Path = AI_TEMPORAL_V7_RESULTS_DIR,
) -> dict[str, Any]:
    """Develop V8 without reading its vault, then seal all eligible predictions."""
    config = load_ai_temporal_v8_config(config_path)
    output_dir = Path(output_dir).resolve()
    public_model_commitment_path = Path(public_model_commitment_path).resolve()
    if (output_dir / "model.joblib").exists() or public_model_commitment_path.exists():
        raise FileExistsError("V8 model or model commitment already exists.")
    source_checks = {
        "development_database": _sha256(development_database),
        "predictor_index": _sha256(predictor_index),
        "v7_test_predictions": _sha256(v7_predictions),
        "sealed_candidates": _sha256(sealed_candidates),
    }
    if source_checks != {
        "development_database": config["development_sources"]["v2_database_sha256"],
        "predictor_index": config["predictor_index_sha256"],
        "v7_test_predictions": config["development_sources"][
            "v7_test_predictions_sha256"
        ],
        "sealed_candidates": config["sealed_candidate_predictions_sha256"],
    }:
        raise AITemporalV8Error("A V8 development source hash does not match.")
    records, features, targets, groups, weights = _load_development(
        development_database, predictor_index, v7_predictions
    )
    model_bundle, selection = _select_v8_model(
        features, targets, groups, weights, config
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    joblib.dump(model_bundle, model_path)

    development_genes = _development_genes(
        development_database, predictor_index, v7_predictions
    )
    with sqlite3.connect(
        f"file:{Path(sealed_candidates).resolve()}?mode=ro", uri=True
    ) as con:
        candidate_rows = [
            (str(identifier), gene_symbols)
            for identifier, gene_symbols in con.execute(
                "SELECT variation_id,gene_symbols FROM predictions"
            )
        ]
    components, blocked_roots = _candidate_components(candidate_rows, development_genes)
    eligible_ids = {
        identifier
        for identifier, root in components.items()
        if root not in blocked_roots
    }
    with Path(v7_predictions).open(newline="", encoding="utf-8") as handle:
        eligible_ids.difference_update(
            row["variation_id"] for row in csv.DictReader(handle)
        )
    prediction_path = output_dir / "sealed_candidate_predictions.sqlite3"
    predictions = sqlite3.connect(prediction_path)
    predictions.executescript(
        """
        CREATE TABLE predictions (
            variation_id TEXT PRIMARY KEY,
            gene_symbols TEXT NOT NULL,
            component_hash TEXT NOT NULL,
            consequence TEXT NOT NULL,
            v8_probability REAL NOT NULL,
            v8_prediction TEXT NOT NULL,
            v7_probability REAL NOT NULL,
            v7_prediction TEXT NOT NULL
        );
        """
    )
    v7_bundle = joblib.load(Path(v7_model_dir) / "model.joblib")
    clue_config = load_clue_score_config()
    clue_config["prediction_date"] = config["prediction_snapshot_date"]
    pending_rows = []
    pending_features = []
    pending_v7_features = []

    def flush() -> None:
        if not pending_rows:
            return
        v8_probabilities = _calibrated_probabilities(
            model_bundle["base_model"],
            model_bundle["calibrator"],
            np.asarray(pending_features, dtype=float),
        )
        v7_probabilities = _calibrated_probabilities(
            v7_bundle["base_model"],
            v7_bundle["calibrator"],
            np.asarray(pending_v7_features, dtype=float),
        )
        values = []
        for row, v8_probability, v7_probability in zip(
            pending_rows, v8_probabilities, v7_probabilities, strict=True
        ):
            identifier, gene_symbols, component_hash, consequence = row
            values.append(
                (
                    identifier,
                    gene_symbols,
                    component_hash,
                    consequence,
                    float(v8_probability),
                    "pathogenic"
                    if v8_probability >= model_bundle["threshold"]
                    else "benign",
                    float(v7_probability),
                    "pathogenic"
                    if v7_probability >= v7_bundle["threshold"]
                    else "benign",
                )
            )
        predictions.executemany(
            "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?)", values
        )
        predictions.commit()
        pending_rows.clear()
        pending_features.clear()
        pending_v7_features.clear()

    with sqlite3.connect(
        f"file:{Path(predictor_index).resolve()}?mode=ro", uri=True
    ) as source:
        source.row_factory = sqlite3.Row
        query = """
            SELECT current.* FROM variant_release AS current
            WHERE current.release_role='newer'
              AND current.clinical_significances='Uncertain significance'
              AND current.origin_simple_values='germline'
              AND current.variation_id GLOB '[0-9]*'
              AND NOT EXISTS (
                  SELECT 1 FROM variant_release AS old
                  WHERE old.release_role='older'
                    AND old.variation_id=current.variation_id
              )
            ORDER BY CAST(current.variation_id AS INTEGER)
        """
        for raw in source.execute(query):
            row = dict(raw)
            identifier = str(row["variation_id"])
            if identifier not in eligible_ids:
                continue
            pending_rows.append(
                (
                    identifier,
                    row["gene_symbols"] or "",
                    hashlib.sha256(components[identifier].encode()).hexdigest(),
                    _consequence(row["names"]),
                )
            )
            pending_features.append(
                v8_features(row, config["prediction_snapshot_date"])
            )
            pending_v7_features.append(_features_from_predictor_row(row, clue_config))
            if len(pending_rows) >= 5000:
                flush()
    flush()
    prediction_count = int(
        predictions.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    )
    predictions.execute("VACUUM")
    predictions.close()
    summary = {
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "state": "model_and_predictions_sealed_vault_unopened",
        "trained_at_utc": datetime.now(UTC).isoformat(),
        "development_records": len(records),
        "development_groups": len(set(groups)),
        "feature_count": len(V8_FEATURE_NAMES),
        "feature_names": list(V8_FEATURE_NAMES),
        "eligible_candidate_predictions": prediction_count,
        **selection,
        "config_sha256": _sha256(config_path),
        "model_sha256": _sha256(model_path),
        "sealed_predictions_sha256": _sha256(prediction_path),
        "source_hashes": source_checks,
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    commitment = {
        key: summary[key]
        for key in (
            "schema_version",
            "experiment_version",
            "state",
            "trained_at_utc",
            "development_records",
            "development_groups",
            "feature_count",
            "eligible_candidate_predictions",
            "selected_model",
            "selected_threshold",
            "nested_balanced_accuracy_at_0_5",
            "selected_calibrated_oof_balanced_accuracy",
            "selected_calibrated_oof_roc_auc",
            "selected_calibrated_oof_brier",
            "config_sha256",
            "model_sha256",
            "sealed_predictions_sha256",
            "source_hashes",
        )
    }
    commitment["vault_accessed_during_development"] = False
    public_model_commitment_path.parent.mkdir(parents=True, exist_ok=True)
    public_model_commitment_path.write_text(
        json.dumps(commitment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return commitment


def _metric_bundle(
    actual: list[str], predicted: list[str], probabilities: np.ndarray
) -> dict[str, Any]:
    targets = np.asarray(
        [int(value == "moved_toward_pathogenic") for value in actual], dtype=int
    )
    metrics = {
        **compute_binary_metrics(actual, predicted),
        "brier_score": float(brier_score_loss(targets, probabilities)),
    }
    if len(set(targets)) == 2:
        metrics.update(
            {
                "roc_auc": float(roc_auc_score(targets, probabilities)),
                "average_precision": float(
                    average_precision_score(targets, probabilities)
                ),
            }
        )
    else:
        metrics.update({"roc_auc": None, "average_precision": None})
    return metrics


def _component_bootstrap(
    rows: list[dict[str, Any]], *, replicates: int = 10_000
) -> dict[str, list[float]]:
    by_component: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_component.setdefault(row["component_hash"], []).append(index)
    components = sorted(by_component)
    generator = np.random.default_rng(223607)
    v8_scores = []
    v7_scores = []
    differences = []
    for _ in range(replicates):
        sampled_components = generator.choice(
            components, size=len(components), replace=True
        )
        indices = [
            index
            for component in sampled_components
            for index in by_component[str(component)]
        ]
        actual = np.asarray(
            [
                rows[index]["actual_outcome"] == "moved_toward_pathogenic"
                for index in indices
            ]
        )
        if len(set(actual)) < 2:
            continue
        v8 = np.asarray(
            [rows[index]["v8_prediction"] == "pathogenic" for index in indices]
        )
        v7 = np.asarray(
            [rows[index]["v7_prediction"] == "pathogenic" for index in indices]
        )
        v8_score = float(balanced_accuracy_score(actual, v8))
        v7_score = float(balanced_accuracy_score(actual, v7))
        v8_scores.append(v8_score)
        v7_scores.append(v7_score)
        differences.append(v8_score - v7_score)

    def interval(values: list[float]) -> list[float]:
        return [
            float(np.percentile(values, 2.5)),
            float(np.percentile(values, 97.5)),
        ]

    return {
        "v8_balanced_accuracy_95_percent": interval(v8_scores),
        "v7_balanced_accuracy_95_percent": interval(v7_scores),
        "paired_difference_95_percent": interval(differences),
    }


def evaluate_v8_once(
    output_dir: Path,
    vault_path: Path,
    vault_commitment_path: Path,
    model_commitment_path: Path,
) -> dict[str, Any]:
    """Open the publicly committed V8 vault once after model sealing."""
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "test_metrics.json"
    started_path = output_dir / "evaluation_started.json"
    if metrics_path.exists() or started_path.exists():
        raise FileExistsError("The V8 sealed temporal test was already evaluated.")
    config_path = output_dir.parent.parent / "config/ai_temporal_v8.yaml"
    config = load_ai_temporal_v8_config(config_path)
    vault_commitment = json.loads(
        Path(vault_commitment_path).read_text(encoding="utf-8")
    )
    model_commitment = json.loads(
        Path(model_commitment_path).read_text(encoding="utf-8")
    )
    if _sha256(vault_path) != vault_commitment["vault_sha256"]:
        raise AITemporalV8Error("The sealed V8 label vault hash does not match.")
    prediction_path = output_dir / "sealed_candidate_predictions.sqlite3"
    if _sha256(prediction_path) != model_commitment["sealed_predictions_sha256"]:
        raise AITemporalV8Error("The sealed V8 prediction hash does not match.")
    model_path = output_dir / "model.joblib"
    if _sha256(model_path) != model_commitment["model_sha256"]:
        raise AITemporalV8Error("The sealed V8 model hash does not match.")
    config_sha256 = _sha256(config_path)
    shared_sources = (
        "development_database",
        "predictor_index",
        "sealed_candidates",
        "v7_test_predictions",
    )
    commitments_match = (
        vault_commitment.get("config_sha256") == config_sha256
        and model_commitment.get("config_sha256") == config_sha256
        and vault_commitment.get("experiment_version") == config["experiment_version"]
        and model_commitment.get("experiment_version") == config["experiment_version"]
        and vault_commitment.get("state")
        == "label_vault_sealed_before_v8_model_development"
        and model_commitment.get("state")
        == "model_and_predictions_sealed_vault_unopened"
        and vault_commitment.get("test_records") == 1000
        and model_commitment.get("vault_accessed_during_development") is False
        and all(
            vault_commitment.get(key) == 0
            for key in (
                "development_test_variation_id_overlap",
                "development_test_gene_component_overlap",
                "v7_test_id_overlap",
            )
        )
        and all(
            vault_commitment["source_hashes"].get(key)
            == model_commitment["source_hashes"].get(key)
            for key in shared_sources
        )
    )
    if not commitments_match:
        raise AITemporalV8Error("The V8 vault and model commitments do not match.")
    started = {
        "state": "evaluation_started_vault_must_not_be_reopened",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "vault_sha256": vault_commitment["vault_sha256"],
        "sealed_predictions_sha256": model_commitment["sealed_predictions_sha256"],
    }
    with started_path.open("x", encoding="utf-8") as handle:
        json.dump(started, handle, indent=2, sort_keys=True)
        handle.write("\n")
    connection = sqlite3.connect(prediction_path)
    connection.row_factory = sqlite3.Row
    connection.execute("ATTACH DATABASE ? AS vault", (str(Path(vault_path).resolve()),))
    vault_config_row = connection.execute(
        "SELECT value FROM vault.metadata WHERE key='config_sha256'"
    ).fetchone()
    if vault_config_row is None or vault_config_row[0] != config_sha256:
        connection.close()
        raise AITemporalV8Error("The V8 vault metadata does not match the config.")
    joined = [
        dict(row)
        for row in connection.execute(
            """
            SELECT p.*,v.actual_outcome,v.answer_classification,
                   v.component_hash AS vault_component_hash
            FROM predictions AS p JOIN vault.labels AS v USING (variation_id)
            ORDER BY CAST(p.variation_id AS INTEGER)
            """
        )
    ]
    connection.close()
    if len(joined) != 1000:
        raise AITemporalV8Error(
            f"The sealed V8 evaluation joined {len(joined)} records, not 1,000."
        )
    if any(row["component_hash"] != row.pop("vault_component_hash") for row in joined):
        raise AITemporalV8Error("V8 prediction and vault component hashes differ.")
    actual = [row["actual_outcome"] for row in joined]
    v8_predictions = [row["v8_prediction"] for row in joined]
    v7_predictions = [row["v7_prediction"] for row in joined]
    v8_probabilities = np.asarray([row["v8_probability"] for row in joined])
    v7_probabilities = np.asarray([row["v7_probability"] for row in joined])
    v8_metrics = _metric_bundle(actual, v8_predictions, v8_probabilities)
    v7_metrics = _metric_bundle(actual, v7_predictions, v7_probabilities)
    majority_label = max(
        ("moved_toward_benign", "moved_toward_pathogenic"),
        key=actual.count,
    )
    majority_metrics = compute_binary_metrics(actual, [majority_label] * len(actual))
    consequence_predictions = [
        "pathogenic"
        if row["consequence"] in {"loss_of_function", "canonical_splice", "missense"}
        else "benign"
        for row in joined
    ]
    consequence_metrics = compute_binary_metrics(actual, consequence_predictions)
    targets = np.asarray(
        [int(value == "moved_toward_pathogenic") for value in actual], dtype=int
    )
    calibration_bins = []
    for lower in np.arange(0, 1, 0.1):
        upper = lower + 0.1
        selected = (v8_probabilities >= lower) & (
            v8_probabilities <= upper if upper >= 1 else v8_probabilities < upper
        )
        if selected.any():
            calibration_bins.append(
                {
                    "lower": float(lower),
                    "upper": float(upper),
                    "records": int(selected.sum()),
                    "mean_probability": float(v8_probabilities[selected].mean()),
                    "observed_pathogenic_fraction": float(targets[selected].mean()),
                }
            )
    bootstrap = _component_bootstrap(joined)
    missense_rows = [row for row in joined if row["consequence"] == "missense"]
    missense_actual = [row["actual_outcome"] for row in missense_rows]
    missense_v8_predictions = [row["v8_prediction"] for row in missense_rows]
    missense_v7_predictions = [row["v7_prediction"] for row in missense_rows]
    missense_v8_metrics = _metric_bundle(
        missense_actual,
        missense_v8_predictions,
        np.asarray([row["v8_probability"] for row in missense_rows]),
    )
    missense_v7_metrics = _metric_bundle(
        missense_actual,
        missense_v7_predictions,
        np.asarray([row["v7_probability"] for row in missense_rows]),
    )
    metrics = {
        **v8_metrics,
        "schema_version": 1,
        "experiment_version": config["experiment_version"],
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "test_records": 1000,
        "sealed_gene_components": len({row["component_hash"] for row in joined}),
        "development_test_variation_id_overlap": vault_commitment[
            "development_test_variation_id_overlap"
        ],
        "development_test_gene_component_overlap": vault_commitment[
            "development_test_gene_component_overlap"
        ],
        "v7_test_id_overlap": vault_commitment["v7_test_id_overlap"],
        "v7_same_record_baseline": v7_metrics,
        "majority_baseline": majority_metrics,
        "consequence_only_baseline": consequence_metrics,
        "v8_minus_v7_balanced_accuracy": (
            v8_metrics["balanced_accuracy"] - v7_metrics["balanced_accuracy"]
        ),
        "component_bootstrap": bootstrap,
        "missense_only": {
            **missense_v8_metrics,
            "v7_same_record_baseline": missense_v7_metrics,
            "v8_minus_v7_balanced_accuracy": (
                missense_v8_metrics["balanced_accuracy"]
                - missense_v7_metrics["balanced_accuracy"]
            ),
            "component_bootstrap": _component_bootstrap(missense_rows),
        },
        "calibration_bins": calibration_bins,
        "vault_sha256": vault_commitment["vault_sha256"],
        "sealed_predictions_sha256": model_commitment["sealed_predictions_sha256"],
        "design_warning": config["design_warning"],
    }
    temporary_metrics = metrics_path.with_suffix(".json.tmp")
    temporary_metrics.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    predictions_output = output_dir / "temporal_test_predictions.csv"
    temporary_predictions = predictions_output.with_suffix(".csv.tmp")
    with temporary_predictions.open("w", newline="", encoding="utf-8") as handle:
        fields = (
            "variation_id",
            "gene_symbols",
            "component_hash",
            "consequence",
            "v8_probability",
            "v8_prediction",
            "v7_probability",
            "v7_prediction",
            "actual_outcome",
            "answer_classification",
        )
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(joined)
    temporary_predictions.replace(predictions_output)
    temporary_metrics.replace(metrics_path)
    completed = {
        **started,
        "state": "evaluation_completed",
        "completed_at_utc": metrics["tested_at_utc"],
    }
    temporary_started = started_path.with_suffix(".json.tmp")
    temporary_started.write_text(
        json.dumps(completed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_started.replace(started_path)
    return metrics
