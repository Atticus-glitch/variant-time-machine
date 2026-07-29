"""Two-stage Clue Score V1 experiment, exports, metrics, and result queries."""

import csv
import json
import math
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.clue_score import (
    CLUE_SCORE_V1_PATH,
    ClueResult,
    Prediction,
    compare_prediction,
    config_sha256,
    load_clue_score_config,
    normalize_newer_outcome,
    older_snapshot_from_row,
    prediction_to_dict,
    score_older_snapshot,
)
from variant_time_machine.config import (
    CLUE_SCORE_REVIEW_PATH,
    HISTORICAL_VARIANT_DB_PATH,
    PROJECT_ROOT,
)

DEVELOPMENT_SAMPLE_SIZE = 500
OUTPUT_FILENAMES = (
    "prediction_results.csv",
    "correct_predictions.csv",
    "wrong_predictions.csv",
    "no_prediction.csv",
    "unscorable.csv",
    "clue_score_v1.yaml",
    "metric_summary.json",
    "confusion_matrix.csv",
    "outcome_by_score.csv",
    "score_distribution.png",
    "outcome_by_score.png",
    "manual_review.csv",
    "experiment_report.md",
)
RESULT_FILTERS = {
    "all": "1 = 1",
    "correct": "result = 'Correct'",
    "wrong": "result = 'Wrong'",
    "no_prediction": "predicted_direction = 'no_prediction'",
    "not_scorable": "result = 'Not Scorable'",
    "predicted_pathogenic": "predicted_direction = 'pathogenic_direction'",
    "predicted_benign": "predicted_direction = 'benign_direction'",
    "predicted_uncertain": "predicted_direction = 'remain_uncertain'",
}
SORTS = {
    "default": "default_rank, variation_sort",
    "score_desc": "total_score DESC, variation_sort",
    "score_asc": "total_score, variation_sort",
    "gene": "COALESCE(old_gene_symbols, ''), variation_sort",
    "outcome": "COALESCE(outcome_group, ''), variation_sort",
    "confidence": "confidence_rank, variation_sort",
    "oldest_evaluation": "old_last_evaluated_sort, variation_sort",
    "newest_evaluation": "old_last_evaluated_sort DESC, variation_sort",
}


class ClueScoreExperimentError(ValueError):
    """Raised when experiment artifacts or requests are invalid."""


def _notify(
    progress: Callable[[dict[str, object]], None] | None,
    stage: str,
    **values: object,
) -> None:
    if progress:
        progress({"stage": stage, **values})


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE predictions (
            variation_id TEXT PRIMARY KEY,
            variation_sort INTEGER NOT NULL,
            old_allele_ids TEXT,
            old_gene_symbols TEXT,
            old_names TEXT,
            old_coordinates TEXT,
            old_phenotypes TEXT,
            old_origin_scope TEXT,
            old_release_date TEXT NOT NULL,
            old_last_evaluated TEXT,
            old_last_evaluated_sort TEXT,
            old_classification TEXT NOT NULL,
            old_review_status TEXT,
            old_submitter_counts TEXT,
            total_score INTEGER NOT NULL,
            predicted_direction TEXT NOT NULL,
            confidence TEXT NOT NULL,
            confidence_rank INTEGER NOT NULL,
            consequence TEXT NOT NULL,
            clues_json TEXT NOT NULL,
            clues_used_json TEXT NOT NULL,
            clues_missing_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            arithmetic TEXT NOT NULL,
            scoring_version TEXT NOT NULL,
            config_sha256 TEXT NOT NULL,
            prediction_saved_at_utc TEXT NOT NULL,
            new_allele_ids TEXT,
            new_gene_symbols TEXT,
            new_names TEXT,
            new_coordinates TEXT,
            new_phenotypes TEXT,
            new_origin_scope TEXT,
            new_release_date TEXT,
            new_last_evaluated TEXT,
            new_classification TEXT,
            new_review_status TEXT,
            new_submitter_counts TEXT,
            match_method TEXT,
            match_confidence TEXT,
            match_safe INTEGER,
            match_warnings_json TEXT,
            outcome_group TEXT,
            outcome_reason_code TEXT,
            outcome_rule TEXT,
            outcome_scorable INTEGER,
            result TEXT,
            result_reason_code TEXT,
            correct INTEGER,
            default_rank INTEGER,
            compared_at_utc TEXT
        );
        CREATE TABLE metadata (document TEXT NOT NULL);
        """
    )


def _parse_last_evaluated(value: object) -> str | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    try:
        return datetime.strptime(str(value), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _prediction_values(
    row: Mapping[str, object], prediction: Prediction, saved_at: str
) -> tuple[object, ...]:
    value = prediction_to_dict(prediction)
    return (
        prediction.variation_id,
        int(prediction.variation_id),
        row["allele_ids"],
        row["gene_symbols"],
        row["names"],
        row["coordinates"],
        row["phenotypes"],
        row["origin_simple_values"],
        row["release_date"],
        row["last_evaluated_dates"],
        _parse_last_evaluated(row["last_evaluated_dates"]),
        row["clinical_significances"],
        row["review_statuses"],
        row["submitter_counts"],
        prediction.total_score,
        prediction.predicted_direction,
        prediction.confidence,
        {
            "High confidence": 0,
            "Medium confidence": 1,
            "Low confidence": 2,
            "No prediction": 3,
        }[prediction.confidence],
        prediction.consequence,
        json.dumps(value["clues"], separators=(",", ":")),
        json.dumps(value["clues_used"], separators=(",", ":")),
        json.dumps(value["clues_missing"], separators=(",", ":")),
        json.dumps(value["warnings"], separators=(",", ":")),
        prediction.arithmetic,
        prediction.scoring_version,
        prediction.config_sha256,
        saved_at,
    )


def _older_query(sample_size: int | None) -> tuple[str, list[object]]:
    fields = (
        "variation_id, allele_ids, variant_types, names, gene_symbols, "
        "clinical_significances, last_evaluated_dates, review_statuses, "
        "submitter_counts, phenotypes, coordinates, guidelines_values, "
        "origin_simple_values, release_date"
    )
    query = (
        f"SELECT {fields} FROM variant_release WHERE release_role = 'older' "
        "AND clinical_significances = 'Uncertain significance' "
    )
    parameters: list[object] = []
    if sample_size is not None:
        query += (
            "ORDER BY ((CAST(variation_id AS INTEGER) * 1103515245 + 12345) "
            "% 2147483647), CAST(variation_id AS INTEGER) LIMIT ?"
        )
        parameters.append(sample_size)
    else:
        query += "ORDER BY CAST(variation_id AS INTEGER)"
    return query, parameters


def _insert_predictions(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    *,
    sample_size: int | None,
    progress: Callable[[dict[str, object]], None] | None,
    rules: Mapping[str, Any],
    rules_hash: str,
) -> int:
    query, parameters = _older_query(sample_size)
    source.row_factory = sqlite3.Row
    cursor = source.execute(query, parameters)
    placeholders = ",".join("?" for _ in range(27))
    insert = (
        "INSERT INTO predictions ("
        "variation_id,variation_sort,old_allele_ids,old_gene_symbols,old_names,"
        "old_coordinates,old_phenotypes,old_origin_scope,old_release_date,"
        "old_last_evaluated,old_last_evaluated_sort,old_classification,"
        "old_review_status,old_submitter_counts,total_score,predicted_direction,"
        "confidence,confidence_rank,consequence,clues_json,clues_used_json,"
        "clues_missing_json,"
        "warnings_json,arithmetic,scoring_version,config_sha256,"
        f"prediction_saved_at_utc) VALUES ({placeholders})"
    )
    count = 0
    batch: list[tuple[object, ...]] = []
    saved_at = datetime.now(UTC).isoformat()
    for raw in cursor:
        row = dict(raw)
        prediction = score_older_snapshot(
            older_snapshot_from_row(row),
            rules,
            frozen_config_sha256=rules_hash,
        )
        batch.append(_prediction_values(row, prediction, saved_at))
        if len(batch) >= 5_000:
            target.executemany(insert, batch)
            count += len(batch)
            batch.clear()
            _notify(progress, "scores_calculated", count=count)
    if batch:
        target.executemany(insert, batch)
        count += len(batch)
    target.commit()
    _notify(progress, "records_eligible", count=count)
    _notify(progress, "predictions_saved", count=count)
    return count


def _chunks(values: list[str], size: int = 500) -> Iterator[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _identifier_set(value: object) -> set[str]:
    if value is None:
        return set()
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _match_assessment(
    old: sqlite3.Row, new: sqlite3.Row | None
) -> tuple[str, str, bool, list[str]]:
    warnings: list[str] = []
    if new is None:
        return "variation_id_only", "unable", False, ["No newer record found."]
    old_alleles = _identifier_set(old["old_allele_ids"])
    new_alleles = _identifier_set(new["allele_ids"])
    if not old_alleles or not new_alleles:
        return "variation_id_only", "limited", False, ["Allele ID was missing."]
    if old_alleles != new_alleles:
        return (
            "variation_id_with_changed_alleles",
            "limited",
            False,
            ["Older and newer Allele ID sets differed."],
        )
    if old["old_gene_symbols"] != new["gene_symbols"]:
        warnings.append("Gene text differed between snapshots.")
    if old["old_phenotypes"] != new["phenotypes"]:
        warnings.append("Condition aggregation differed between snapshots.")
    if old["old_origin_scope"] not in {None, "germline"}:
        warnings.append("Older origin scope was not exclusively germline.")
        return "exact_variation_and_allele", "limited", False, warnings
    if new["origin_simple_values"] not in {None, "germline"}:
        warnings.append("Newer origin scope was not exclusively germline.")
        return "exact_variation_and_allele", "limited", False, warnings
    return "exact_variation_and_allele", "high", True, warnings


def _stored_prediction(row: sqlite3.Row) -> Prediction:
    return Prediction(
        variation_id=row["variation_id"],
        total_score=row["total_score"],
        predicted_direction=row["predicted_direction"],
        confidence=row["confidence"],
        consequence=row["consequence"],
        clues=tuple(ClueResult(**item) for item in json.loads(row["clues_json"])),
        clues_used=tuple(json.loads(row["clues_used_json"])),
        clues_missing=tuple(json.loads(row["clues_missing_json"])),
        warnings=tuple(json.loads(row["warnings_json"])),
        arithmetic=row["arithmetic"],
        scoring_version=row["scoring_version"],
        config_sha256=row["config_sha256"],
    )


def _comparison_values(old: sqlite3.Row, new: sqlite3.Row | None) -> tuple[object, ...]:
    method, confidence, safe, warnings = _match_assessment(old, new)
    outcome = normalize_newer_outcome(new["clinical_significances"] if new else None)
    comparison = compare_prediction(_stored_prediction(old), outcome, match_safe=safe)
    if comparison.result in {"Wrong", "Correct"}:
        default_rank = old["confidence_rank"] * 2 + (
            0 if comparison.result == "Wrong" else 1
        )
    else:
        default_rank = 6
    return (
        new["allele_ids"] if new else None,
        new["gene_symbols"] if new else None,
        new["names"] if new else None,
        new["coordinates"] if new else None,
        new["phenotypes"] if new else None,
        new["origin_simple_values"] if new else None,
        new["release_date"] if new else "2024-01-04",
        new["last_evaluated_dates"] if new else None,
        new["clinical_significances"] if new else None,
        new["review_statuses"] if new else None,
        new["submitter_counts"] if new else None,
        method,
        confidence,
        int(safe),
        json.dumps(warnings, separators=(",", ":")),
        outcome.group,
        outcome.reason_code,
        outcome.rule,
        int(outcome.scorable),
        comparison.result,
        comparison.reason_code,
        comparison.correct,
        default_rank,
        datetime.now(UTC).isoformat(),
        old["variation_id"],
    )


def _compare_outcomes(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    progress: Callable[[dict[str, object]], None] | None,
) -> int:
    target.row_factory = sqlite3.Row
    source.row_factory = sqlite3.Row
    ids = [row[0] for row in target.execute("SELECT variation_id FROM predictions")]
    newer: dict[str, sqlite3.Row] = {}
    fields = (
        "variation_id, allele_ids, names, gene_symbols, clinical_significances, "
        "last_evaluated_dates, review_statuses, submitter_counts, phenotypes, "
        "coordinates, origin_simple_values, release_date"
    )
    for chunk in _chunks(ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = source.execute(
            f"SELECT {fields} FROM variant_release WHERE release_role = 'newer' "
            f"AND variation_id IN ({placeholders})",
            chunk,
        )
        newer.update({row["variation_id"]: row for row in rows})
    update = (
        "UPDATE predictions SET new_allele_ids=?,new_gene_symbols=?,new_names=?,"
        "new_coordinates=?,new_phenotypes=?,new_origin_scope=?,new_release_date=?,"
        "new_last_evaluated=?,new_classification=?,new_review_status=?,"
        "new_submitter_counts=?,match_method=?,match_confidence=?,match_safe=?,"
        "match_warnings_json=?,outcome_group=?,outcome_reason_code=?,outcome_rule=?,"
        "outcome_scorable=?,result=?,result_reason_code=?,correct=?,default_rank=?,"
        "compared_at_utc=? WHERE variation_id=?"
    )
    count = 0
    batch: list[tuple[object, ...]] = []
    for old in target.execute("SELECT * FROM predictions ORDER BY variation_sort"):
        batch.append(_comparison_values(old, newer.get(old["variation_id"])))
        if len(batch) >= 5_000:
            target.executemany(update, batch)
            count += len(batch)
            batch.clear()
            _notify(progress, "outcomes_compared", count=count)
    if batch:
        target.executemany(update, batch)
        count += len(batch)
    target.commit()
    target.executescript(
        """
        CREATE INDEX predictions_result ON predictions(result);
        CREATE INDEX predictions_default ON predictions(default_rank, variation_sort);
        CREATE INDEX predictions_result_default
          ON predictions(result, default_rank, variation_sort);
        CREATE INDEX predictions_direction ON predictions(predicted_direction);
        CREATE INDEX predictions_gene ON predictions(old_gene_symbols);
        CREATE INDEX predictions_sort ON predictions(variation_sort);
        CREATE INDEX predictions_score ON predictions(total_score);
        """
    )
    _notify(progress, "outcomes_compared", count=count)
    return count


def _safe_divide(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def calculate_metrics(connection: sqlite3.Connection) -> dict[str, Any]:
    """Calculate declared metrics from real stored comparisons."""
    connection.row_factory = sqlite3.Row

    def scalar(query: str, values: tuple[object, ...] = ()) -> int:
        return int(connection.execute(query, values).fetchone()[0])

    eligible = scalar("SELECT COUNT(*) FROM predictions")
    predictions_made = scalar(
        "SELECT COUNT(*) FROM predictions WHERE predicted_direction!='no_prediction'"
    )
    no_prediction = eligible - predictions_made
    correct = scalar("SELECT COUNT(*) FROM predictions WHERE result='Correct'")
    wrong = scalar("SELECT COUNT(*) FROM predictions WHERE result='Wrong'")
    not_scorable = scalar(
        "SELECT COUNT(*) FROM predictions WHERE result='Not Scorable'"
    )
    classes = {
        "moved_toward_pathogenic": "pathogenic_direction",
        "moved_toward_benign": "benign_direction",
        "remained_uncertain": "remain_uncertain",
    }
    recalls: dict[str, float | None] = {}
    precisions: dict[str, float | None] = {}
    confusion: dict[str, dict[str, int]] = {}
    for actual, expected in classes.items():
        actual_total = scalar(
            "SELECT COUNT(*) FROM predictions WHERE outcome_group=? AND match_safe=1",
            (actual,),
        )
        true_positive = scalar(
            "SELECT COUNT(*) FROM predictions WHERE outcome_group=? "
            "AND predicted_direction=? AND match_safe=1",
            (actual, expected),
        )
        recalls[actual] = _safe_divide(true_positive, actual_total)
        predicted_total = scalar(
            "SELECT COUNT(*) FROM predictions WHERE predicted_direction=? "
            "AND outcome_scorable=1 AND match_safe=1",
            (expected,),
        )
        precisions[expected] = _safe_divide(true_positive, predicted_total)
        confusion[actual] = {}
        for predicted in (*classes.values(), "no_prediction"):
            confusion[actual][predicted] = scalar(
                "SELECT COUNT(*) FROM predictions WHERE outcome_group=? "
                "AND predicted_direction=? AND match_safe=1",
                (actual, predicted),
            )
    valid_recalls = [value for value in recalls.values() if value is not None]
    balanced = sum(valid_recalls) / len(valid_recalls) if valid_recalls else None
    clue_counts: dict[str, dict[str, int]] = {}
    for row in connection.execute(
        "SELECT clues_used_json,result FROM predictions "
        "WHERE result IN ('Correct','Wrong')"
    ):
        for clue in json.loads(row["clues_used_json"]):
            clue_counts.setdefault(clue, {"Correct": 0, "Wrong": 0})[row["result"]] += 1
    clue_stats = {
        clue: {
            **counts,
            "precision": _safe_divide(counts["Correct"], sum(counts.values())),
        }
        for clue, counts in clue_counts.items()
    }
    return {
        "schema_version": 1,
        "scoring_version": "Clue Score V1",
        "eligible_older_vus_records": eligible,
        "predictions_made": predictions_made,
        "no_prediction": no_prediction,
        "correct": correct,
        "wrong": wrong,
        "not_scorable": not_scorable,
        "overall_accuracy": _safe_divide(correct, correct + wrong),
        "balanced_accuracy": balanced,
        "pathogenic_direction_precision": precisions["pathogenic_direction"],
        "benign_direction_precision": precisions["benign_direction"],
        "uncertain_direction_accuracy": recalls["remained_uncertain"],
        "class_recall": recalls,
        "no_prediction_rate": _safe_divide(no_prediction, eligible),
        "confusion_matrix": confusion,
        "clue_stats": clue_stats,
    }


def _write_csv_query(
    connection: sqlite3.Connection,
    path: Path,
    query: str,
    parameters: tuple[object, ...] = (),
) -> None:
    cursor = connection.execute(query, parameters)
    headers = [item[0] for item in cursor.description]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(cursor)


def _export_tables(
    connection: sqlite3.Connection, output_dir: Path, metrics: Mapping[str, Any]
) -> None:
    public_columns = (
        "variation_id,old_allele_ids,old_gene_symbols,old_names,old_coordinates,"
        "old_phenotypes,old_release_date,old_last_evaluated,old_classification,"
        "old_review_status,old_submitter_counts,total_score,predicted_direction,"
        "confidence,consequence,clues_json,clues_used_json,clues_missing_json,"
        "warnings_json,arithmetic,scoring_version,config_sha256,new_allele_ids,"
        "new_gene_symbols,new_names,new_coordinates,new_phenotypes,new_release_date,"
        "new_last_evaluated,new_classification,new_review_status,"
        "new_submitter_counts,match_method,match_confidence,match_safe,"
        "match_warnings_json,outcome_group,outcome_reason_code,outcome_rule,"
        "outcome_scorable,result,result_reason_code,correct"
    )
    _write_csv_query(
        connection,
        output_dir / "prediction_results.csv",
        f"SELECT {public_columns} FROM predictions ORDER BY variation_sort",
    )
    filters = {
        "correct_predictions.csv": "result='Correct'",
        "wrong_predictions.csv": "result='Wrong'",
        "no_prediction.csv": "predicted_direction='no_prediction'",
        "unscorable.csv": "result='Not Scorable'",
    }
    for filename, condition in filters.items():
        _write_csv_query(
            connection,
            output_dir / filename,
            f"SELECT {public_columns} FROM predictions WHERE {condition} "
            "ORDER BY variation_sort",
        )
    (output_dir / "metric_summary.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    predictions = (
        "pathogenic_direction",
        "benign_direction",
        "remain_uncertain",
        "no_prediction",
    )
    with (output_dir / "confusion_matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(("actual_outcome", *predictions))
        for actual, values in metrics["confusion_matrix"].items():
            writer.writerow((actual, *(values[item] for item in predictions)))
    _write_csv_query(
        connection,
        output_dir / "outcome_by_score.csv",
        "SELECT total_score,outcome_group,result,COUNT(*) AS records "
        "FROM predictions GROUP BY total_score,outcome_group,result "
        "ORDER BY total_score,outcome_group,result",
    )
    _write_csv_query(
        connection,
        output_dir / "manual_review.csv",
        "SELECT variation_id,result AS automatic_result,'' AS review_status,"
        "'' AS correctly_matched,'' AS reviewer_decision,'' AS notes,"
        "'' AS reviewed_at_utc FROM predictions ORDER BY variation_sort",
    )
    shutil.copyfile(CLUE_SCORE_V1_PATH, output_dir / "clue_score_v1.yaml")


def _export_charts(connection: sqlite3.Connection, output_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scores = connection.execute(
        "SELECT total_score,COUNT(*) FROM predictions "
        "GROUP BY total_score ORDER BY total_score"
    ).fetchall()
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.bar([row[0] for row in scores], [row[1] for row in scores], color="#2f8193")
    axis.set(title="Clue Score V1 distribution", xlabel="Score", ylabel="Variants")
    figure.tight_layout()
    figure.savefig(output_dir / "score_distribution.png", dpi=160)
    plt.close(figure)

    rows = connection.execute(
        "SELECT total_score,outcome_group,COUNT(*) FROM predictions "
        "WHERE outcome_scorable=1 AND match_safe=1 "
        "GROUP BY total_score,outcome_group ORDER BY total_score"
    ).fetchall()
    groups: dict[str, dict[int, int]] = {}
    for score, outcome, count in rows:
        groups.setdefault(outcome, {})[score] = count
    all_scores = sorted({score for values in groups.values() for score in values})
    figure, axis = plt.subplots(figsize=(10, 5))
    bottom = [0] * len(all_scores)
    colors = ("#9a3d35", "#33745a", "#996d20")
    for (group, values), color in zip(sorted(groups.items()), colors, strict=False):
        counts = [values.get(score, 0) for score in all_scores]
        axis.bar(all_scores, counts, bottom=bottom, label=group, color=color)
        bottom = [left + right for left, right in zip(bottom, counts, strict=True)]
    axis.set(title="Normalized outcomes by score", xlabel="Score", ylabel="Variants")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "outcome_by_score.png", dpi=160)
    plt.close(figure)


def _percent(value: object) -> str:
    return "Not available" if value is None else f"{float(value):.1%}"


def _report(metrics: Mapping[str, Any], metadata: Mapping[str, Any]) -> str:
    clue_stats = metrics["clue_stats"]
    helpful = sorted(
        clue_stats.items(),
        key=lambda item: (
            item[1]["Correct"],
            item[1]["precision"] if item[1]["precision"] is not None else -1,
        ),
        reverse=True,
    )
    top_clue = helpful[0][0] if helpful else "No directional clue"
    return f"""# Clue Score V1 Results

Generated: {metadata["completed_at_utc"]}

## Question

Can a small fixed score using only fields in the January 6, 2022 ClinVar
snapshot predict the direction of the January 4, 2024 aggregate classification?

## Data Sources And Dates

- Predictor snapshot: January 6, 2022 archived `variant_summary`.
- Answer snapshot: January 4, 2024 archived `variant_summary`.
- Exact older eligibility: `Uncertain significance`.
- This is a two-snapshot comparison. It does not establish the exact date of change.

## Frozen Formula And Thresholds

The permanent formula is `config/clue_score_v1.yaml` with SHA-256
`{metadata["config_sha256"]}`. Its provisional weights were frozen before full
outcome evaluation. Scores of +3 or higher predict pathogenic direction, -2 or
lower predict benign direction, -1 through +2 predict remaining uncertain, and
records without a directional clue receive no prediction.

## Actual Results

- Eligible older VUS records: {metrics["eligible_older_vus_records"]:,}
- Predictions made: {metrics["predictions_made"]:,}
- Correct: {metrics["correct"]:,}
- Wrong: {metrics["wrong"]:,}
- No prediction: {metrics["no_prediction"]:,}
- Not scorable: {metrics["not_scorable"]:,}
- Accuracy among correct/wrong results: {_percent(metrics["overall_accuracy"])}
- Balanced accuracy: {_percent(metrics["balanced_accuracy"])}
- Pathogenic-direction precision: {_percent(metrics["pathogenic_direction_precision"])}
- Benign-direction precision: {_percent(metrics["benign_direction_precision"])}
- Uncertain-outcome recall: {_percent(metrics["uncertain_direction_accuracy"])}
- No-prediction rate: {_percent(metrics["no_prediction_rate"])}

## Confusion Matrix

See `confusion_matrix.csv`. Rows are normalized actual outcomes and columns are
prediction directions. Unscorable newer categories are excluded rather than forced
into a direction.

## Common Clues And Failures

The clue appearing in the largest number of correct predictions was `{top_clue}`.
This descriptive count does not prove that the clue caused correctness. Wrong
predictions can reflect weak HGVS consequence inference, aggregate condition
differences, and provisional review-status points. Exact counts are in
`metric_summary.json`.

## Limitations

- This is an exploratory rule-based baseline, not a medical prediction tool.
- The summary file lacks modern consequence annotations, population frequency,
  conservation, functional evidence, and submission-level evidence.
- Exact Variation ID and Allele ID equality is required; unsafe scope is not scorable.
- Aggregate classifications may combine conditions and submitters differently over time.
- Snapshot dates and `LastEvaluated` are separate and neither necessarily identifies
  the exact change date.
- Weights were not optimized and performance is not clinical validity.

## Next Experiment

Manually review stratified correct, wrong, no-prediction, and unscorable records. A
future Version 2 may test independently dated annotations or revised rules, but must
keep Version 1 unchanged and use separate validation.
"""


def run_clue_score_experiment(
    source_database: Path,
    result_database: Path,
    output_dir: Path,
    *,
    sample_size: int | None = None,
    overwrite: bool = False,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, Any]:
    """Run prediction first, then compare the separately loaded answer key."""
    rules = load_clue_score_config()
    rules_hash = config_sha256()
    source_database = Path(source_database).resolve()
    result_database = Path(result_database).resolve()
    output_dir = Path(output_dir).resolve()
    if not source_database.is_file():
        raise FileNotFoundError(f"Historical index is missing: {source_database}")
    if result_database.exists() and not overwrite:
        raise FileExistsError(f"Prediction database exists: {result_database}")
    result_database.parent.mkdir(parents=True, exist_ok=True)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{result_database.name}.", suffix=".tmp", dir=result_database.parent
    )
    os.close(descriptor)
    temporary_database = Path(temporary_name)
    temporary_output = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    started = datetime.now(UTC)
    try:
        with (
            sqlite3.connect(f"file:{source_database}?mode=ro", uri=True) as source,
            sqlite3.connect(temporary_database) as target,
        ):
            target.execute("PRAGMA journal_mode=OFF")
            target.execute("PRAGMA synchronous=OFF")
            _create_schema(target)
            _notify(progress, "records_loaded", sample_size=sample_size)
            eligible = _insert_predictions(
                source,
                target,
                sample_size=sample_size,
                progress=progress,
                rules=rules,
                rules_hash=rules_hash,
            )
            compared = _compare_outcomes(source, target, progress)
            metrics = calculate_metrics(target)
            completed = datetime.now(UTC)
            metadata = {
                "schema_version": 1,
                "mode": "development" if sample_size is not None else "full",
                "sample_size": sample_size,
                "eligible_records": eligible,
                "compared_records": compared,
                "started_at_utc": started.isoformat(),
                "completed_at_utc": completed.isoformat(),
                "runtime_seconds": (completed - started).total_seconds(),
                "source_database": str(source_database),
                "scoring_version": "Clue Score V1",
                "config_sha256": rules_hash,
                "leakage_boundary": (
                    "All predictions were committed before newer outcomes were loaded."
                ),
                "metrics": metrics,
            }
            target.execute(
                "INSERT INTO metadata VALUES (?)",
                (json.dumps(metadata, sort_keys=True),),
            )
            target.commit()
            _notify(progress, "metrics_calculated", metrics=metrics)
            _export_tables(target, temporary_output, metrics)
            _export_charts(target, temporary_output)
            (temporary_output / "experiment_report.md").write_text(
                _report(metrics, metadata), encoding="utf-8"
            )
        if output_dir.exists():
            if not overwrite:
                raise FileExistsError(f"Prediction outputs exist: {output_dir}")
            shutil.rmtree(output_dir)
        temporary_output.replace(output_dir)
        if result_database.exists():
            result_database.unlink()
        temporary_database.replace(result_database)
        if (
            sample_size is None
            and source_database == HISTORICAL_VARIANT_DB_PATH.resolve()
        ):
            research_report = PROJECT_ROOT / "research" / "clue-score-v1-results.md"
            research_report.write_text(
                (output_dir / "experiment_report.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        summary = {
            **metadata,
            **metrics,
            "result_database_bytes": result_database.stat().st_size,
            "output_bytes": sum(
                path.stat().st_size for path in output_dir.rglob("*") if path.is_file()
            ),
        }
        _notify(progress, "results_saved", summary=summary)
        return summary
    except Exception:
        temporary_database.unlink(missing_ok=True)
        shutil.rmtree(temporary_output, ignore_errors=True)
        raise


def _read_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute("SELECT document FROM metadata").fetchone()
    if row is None:
        raise ClueScoreExperimentError("Prediction metadata is missing.")
    return json.loads(row[0])


def prediction_summary(result_database: Path) -> dict[str, Any]:
    """Return stored run metadata and recalculated metrics."""
    path = Path(result_database).resolve()
    if not path.is_file():
        raise ClueScoreExperimentError("Clue Score V1 has not been run yet.")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        metadata = _read_metadata(connection)
        stored_metrics = metadata.pop("metrics", None)
        metrics = stored_metrics or calculate_metrics(connection)
        return {**metadata, **metrics}


def list_predictions(
    result_database: Path,
    *,
    query: str = "",
    result_filter: str = "all",
    sort: str = "default",
    page: int = 1,
    page_size: int = 50,
    reviews: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Return a searchable, paginated public prediction list."""
    if result_filter not in RESULT_FILTERS or sort not in SORTS:
        raise ClueScoreExperimentError("Unknown prediction filter or sort.")
    if page < 1 or page_size < 1 or page_size > 200:
        raise ClueScoreExperimentError("Invalid prediction page.")
    query = query.strip()
    if len(query) > 200:
        raise ClueScoreExperimentError(
            "Prediction search is limited to 200 characters."
        )
    clauses = [RESULT_FILTERS[result_filter]]
    parameters: list[object] = []
    if query:
        vcv = query.upper().removeprefix("VCV").split(".", 1)[0].lstrip("0")
        if query.isdigit() or (query.upper().startswith("VCV") and vcv.isdigit()):
            clauses.append("variation_id = ?")
            parameters.append(
                vcv if query.upper().startswith("VCV") else str(int(query))
            )
        else:
            like = f"%{query}%"
            clauses.append(
                "(old_gene_symbols LIKE ? OR old_names LIKE ? "
                "OR old_classification LIKE ? OR new_classification LIKE ?)"
            )
            parameters.extend([like] * 4)
    where = " AND ".join(f"({clause})" for clause in clauses)
    path = Path(result_database).resolve()
    if not path.is_file():
        raise ClueScoreExperimentError("Clue Score V1 has not been run yet.")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(
            f"SELECT COUNT(*) FROM predictions WHERE {where}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT variation_id,old_gene_symbols,old_names,old_release_date,"
            "old_classification,total_score,predicted_direction,confidence,"
            "new_release_date,new_classification,result,match_confidence "
            f"FROM predictions WHERE {where} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    review_values = reviews or {}
    public = []
    for row in rows:
        item = dict(row)
        review = review_values.get(item["variation_id"], {})
        item["manual_review_status"] = review.get("status", "unreviewed")
        item["vcv_accession"] = None
        public.append(item)
    return {
        "rows": public,
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": math.ceil(total / page_size) if total else 0,
    }


def prediction_detail(
    result_database: Path,
    variation_id: str,
    review: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Return every stored automatic clue and comparison field."""
    if not variation_id.isdigit():
        raise ClueScoreExperimentError("Variation ID must contain only digits.")
    path = Path(result_database).resolve()
    if not path.is_file():
        raise ClueScoreExperimentError("Clue Score V1 has not been run yet.")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM predictions WHERE variation_id=?", (variation_id,)
        ).fetchone()
    if row is None:
        raise ClueScoreExperimentError("Prediction was not found.")
    value = dict(row)
    for field in (
        "clues_json",
        "clues_used_json",
        "clues_missing_json",
        "warnings_json",
        "match_warnings_json",
    ):
        value[field.removesuffix("_json")] = json.loads(value.pop(field))
    value["manual_review"] = dict(review or {"status": "unreviewed"})
    value["vcv_accession"] = None
    value["vcv_note"] = "VCV accession is not present in variant_summary."
    return value


def empty_reviews() -> dict[str, Any]:
    """Return an empty sparse manual review document."""
    return {"schema_version": 1, "updated_at_utc": None, "reviews": {}}


def load_prediction_reviews(path: Path = CLUE_SCORE_REVIEW_PATH) -> dict[str, Any]:
    """Load sparse manual decisions separately from automatic predictions."""
    path = Path(path)
    if not path.exists():
        return empty_reviews()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("reviews"), dict):
        raise ClueScoreExperimentError("Prediction review file is invalid.")
    return value


def update_prediction_review(
    variation_id: str,
    changes: Mapping[str, object],
    path: Path = CLUE_SCORE_REVIEW_PATH,
) -> dict[str, Any]:
    """Atomically update only sparse manual annotation fields."""
    if not variation_id.isdigit():
        raise ClueScoreExperimentError("Variation ID must contain only digits.")
    allowed_statuses = {"reviewed", "correctly_matched", "ambiguous", "excluded"}
    status = changes.get("status")
    note = changes.get("note", "")
    if status not in allowed_statuses:
        raise ClueScoreExperimentError("Unknown manual review status.")
    if not isinstance(note, str) or len(note) > 20_000:
        raise ClueScoreExperimentError("Manual review note is invalid.")
    if status in {"ambiguous", "excluded"} and not note.strip():
        raise ClueScoreExperimentError("Ambiguous or excluded reviews require a note.")
    document = load_prediction_reviews(path)
    now = datetime.now(UTC).isoformat()
    reviews = document["reviews"]
    assert isinstance(reviews, dict)
    existing = reviews.get(variation_id, {})
    old_notes = existing.get("notes", []) if isinstance(existing, dict) else []
    notes = [*old_notes, note.strip()] if note.strip() else list(old_notes)
    review = {
        "status": status,
        "correctly_matched": status == "correctly_matched",
        "excluded": status == "excluded",
        "notes": notes,
        "updated_at_utc": now,
    }
    reviews[variation_id] = review
    document["updated_at_utc"] = now
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(document, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return review
