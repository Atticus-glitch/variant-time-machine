"""Changed-outcome-only pathogenic-versus-benign Version 2 experiment."""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.config import (
    CLUE_SCORE_RESULTS_DB_PATH,
    PROJECT_ROOT,
    RESOLVED_DIRECTION_CONFIG_PATH,
)

OUTPUT_FILENAMES = (
    "resolved_direction_results.csv",
    "correct_predictions.csv",
    "wrong_predictions.csv",
    "no_prediction.csv",
    "resolved_direction_v2.yaml",
    "metric_summary.json",
    "confusion_matrix.csv",
    "outcome_by_score.csv",
    "score_distribution.png",
    "experiment_report.md",
)


class ResolvedDirectionError(ValueError):
    """Raised when the conditional Version 2 experiment is invalid."""


def load_resolved_direction_config(
    path: Path = RESOLVED_DIRECTION_CONFIG_PATH,
) -> dict[str, Any]:
    """Load and validate the frozen JSON-compatible YAML configuration."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolvedDirectionError(
            f"Could not load Resolved Direction V2: {exc}"
        ) from exc
    if value.get("experiment_version") != "Resolved Direction V2":
        raise ResolvedDirectionError("Resolved Direction V2 configuration is invalid.")
    if value.get("status") != "frozen":
        raise ResolvedDirectionError("Resolved Direction V2 must remain frozen.")
    if "remain_uncertain" in value.get("allowed_predictions", []):
        raise ResolvedDirectionError(
            "Resolved Direction V2 cannot predict uncertainty."
        )
    return value


def resolved_config_sha256(path: Path = RESOLVED_DIRECTION_CONFIG_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binary_direction(score: int) -> str:
    """Map an older-only V1 score to the frozen conditional binary decision."""
    if score >= 1:
        return "pathogenic_direction"
    if score <= -1:
        return "benign_direction"
    return "no_prediction"


def binary_result(direction: str, outcome_group: str) -> tuple[str, str, int | None]:
    """Compare one binary direction with a clear resolved answer."""
    if outcome_group not in {"moved_toward_pathogenic", "moved_toward_benign"}:
        raise ResolvedDirectionError(
            "Version 2 accepts only resolved directional outcomes."
        )
    if direction == "no_prediction":
        return "No Prediction", "zero_score_no_direction", None
    expected = (
        "moved_toward_pathogenic"
        if direction == "pathogenic_direction"
        else "moved_toward_benign"
    )
    correct = expected == outcome_group
    return (
        "Correct" if correct else "Wrong",
        "direction_matched" if correct else "direction_mismatch",
        int(correct),
    )


def _metrics(connection: sqlite3.Connection) -> dict[str, Any]:
    def count(where: str = "1=1", values: tuple[object, ...] = ()) -> int:
        return int(
            connection.execute(
                f"SELECT COUNT(*) FROM predictions WHERE {where}", values
            ).fetchone()[0]
        )

    eligible = count()
    made = count("predicted_direction!='no_prediction'")
    no_prediction = eligible - made
    correct = count("result='Correct'")
    wrong = count("result='Wrong'")
    actual_pathogenic = count("outcome_group='moved_toward_pathogenic'")
    actual_benign = count("outcome_group='moved_toward_benign'")
    true_pathogenic = count(
        "outcome_group='moved_toward_pathogenic' "
        "AND predicted_direction='pathogenic_direction'"
    )
    true_benign = count(
        "outcome_group='moved_toward_benign' AND predicted_direction='benign_direction'"
    )
    predicted_pathogenic = count("predicted_direction='pathogenic_direction'")
    predicted_benign = count("predicted_direction='benign_direction'")

    def divide(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    pathogenic_recall = divide(true_pathogenic, actual_pathogenic)
    benign_recall = divide(true_benign, actual_benign)
    valid_recalls = [
        value for value in (pathogenic_recall, benign_recall) if value is not None
    ]
    confusion = {
        "moved_toward_pathogenic": {
            direction: count(
                "outcome_group='moved_toward_pathogenic' AND predicted_direction=?",
                (direction,),
            )
            for direction in (
                "pathogenic_direction",
                "benign_direction",
                "no_prediction",
            )
        },
        "moved_toward_benign": {
            direction: count(
                "outcome_group='moved_toward_benign' AND predicted_direction=?",
                (direction,),
            )
            for direction in (
                "pathogenic_direction",
                "benign_direction",
                "no_prediction",
            )
        },
    }
    return {
        "schema_version": 1,
        "scoring_version": "Resolved Direction V2",
        "eligible_older_vus_records": eligible,
        "resolved_direction_records": eligible,
        "predictions_made": made,
        "no_prediction": no_prediction,
        "correct": correct,
        "wrong": wrong,
        "not_scorable": 0,
        "overall_accuracy": divide(correct, correct + wrong),
        "balanced_accuracy": (
            sum(valid_recalls) / len(valid_recalls) if valid_recalls else None
        ),
        "pathogenic_direction_precision": divide(true_pathogenic, predicted_pathogenic),
        "benign_direction_precision": divide(true_benign, predicted_benign),
        "pathogenic_direction_recall": pathogenic_recall,
        "benign_direction_recall": benign_recall,
        "uncertain_direction_accuracy": None,
        "actual_pathogenic": actual_pathogenic,
        "actual_benign": actual_benign,
        "no_prediction_rate": divide(no_prediction, eligible),
        "confusion_matrix": confusion,
        "conditional_task": True,
    }


def _write_csv(connection: sqlite3.Connection, path: Path, where: str = "1=1") -> None:
    cursor = connection.execute(
        "SELECT variation_id,old_allele_ids,old_gene_symbols,old_names,"
        "old_coordinates,old_phenotypes,old_release_date,old_last_evaluated,"
        "old_classification,total_score,predicted_direction,confidence,"
        "consequence,clues_json,arithmetic,scoring_version,new_release_date,"
        "new_last_evaluated,new_classification,outcome_group,result,"
        "result_reason_code,correct FROM predictions "
        f"WHERE {where} ORDER BY variation_sort"
    )
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(item[0] for item in cursor.description)
        writer.writerows(cursor)


def _export(
    connection: sqlite3.Connection,
    output_dir: Path,
    metrics: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> None:
    _write_csv(connection, output_dir / "resolved_direction_results.csv")
    _write_csv(connection, output_dir / "correct_predictions.csv", "result='Correct'")
    _write_csv(connection, output_dir / "wrong_predictions.csv", "result='Wrong'")
    _write_csv(
        connection,
        output_dir / "no_prediction.csv",
        "predicted_direction='no_prediction'",
    )
    (output_dir / "metric_summary.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(
        RESOLVED_DIRECTION_CONFIG_PATH, output_dir / "resolved_direction_v2.yaml"
    )
    directions = ("pathogenic_direction", "benign_direction", "no_prediction")
    with (output_dir / "confusion_matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(("actual_outcome", *directions))
        for outcome, values in metrics["confusion_matrix"].items():
            writer.writerow((outcome, *(values[direction] for direction in directions)))
    cursor = connection.execute(
        "SELECT total_score,outcome_group,result,COUNT(*) FROM predictions "
        "GROUP BY total_score,outcome_group,result ORDER BY total_score,outcome_group"
    )
    with (output_dir / "outcome_by_score.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.writer(output)
        writer.writerow(("score", "actual_outcome", "result", "records"))
        writer.writerows(cursor)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = connection.execute(
        "SELECT total_score,COUNT(*) FROM predictions GROUP BY total_score "
        "ORDER BY total_score"
    ).fetchall()
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.bar([row[0] for row in rows], [row[1] for row in rows], color="#2f8193")
    axis.set(
        title="Resolved Direction V2 score distribution",
        xlabel="Frozen V1 score",
        ylabel="Resolved variants",
    )
    figure.tight_layout()
    figure.savefig(output_dir / "score_distribution.png", dpi=160)
    plt.close(figure)

    def percent(value: float | None) -> str:
        return "Not available" if value is None else f"{value:.1%}"

    report = f"""# Resolved Direction V2 Results

Generated: {metadata["completed_at_utc"]}

## Conditional Question

Among safely matched variants that were exactly uncertain in the January 6, 2022
snapshot and had become clearly pathogenic or benign by the January 4, 2024 snapshot,
which direction does the older-only frozen score predict?

This experiment does not predict whether a VUS will become certain. Cohort membership
uses the later answer snapshot, while the score itself remains based only on 2022.

## Frozen Binary Rule

- Score +1 or higher: pathogenic direction
- Score -1 or lower: benign direction
- Score 0: no prediction
- `remain_uncertain` is not an allowed prediction

## Actual Results

- Resolved directional cohort: {metrics["resolved_direction_records"]:,}
- Actual pathogenic direction: {metrics["actual_pathogenic"]:,}
- Actual benign direction: {metrics["actual_benign"]:,}
- Predictions made: {metrics["predictions_made"]:,}
- Correct: {metrics["correct"]:,}
- Wrong: {metrics["wrong"]:,}
- No prediction: {metrics["no_prediction"]:,}
- Accuracy: {percent(metrics["overall_accuracy"])}
- Balanced accuracy: {percent(metrics["balanced_accuracy"])}
- Pathogenic precision: {percent(metrics["pathogenic_direction_precision"])}
- Benign precision: {percent(metrics["benign_direction_precision"])}
- Pathogenic recall: {percent(metrics["pathogenic_direction_recall"])}
- Benign recall: {percent(metrics["benign_direction_recall"])}

## Limitation

Version 2 was designed after reviewing Version 1 aggregate results and uses the same
2024 answer snapshot. It is exploratory, not independent validation, not a prediction
of whether resolution occurs, and not a medical tool.
"""
    (output_dir / "experiment_report.md").write_text(report, encoding="utf-8")


def run_resolved_direction_experiment(
    parent_database: Path,
    result_database: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build the conditional binary cohort from immutable Version 1 predictions."""
    config = load_resolved_direction_config()
    parent_database = Path(parent_database).resolve()
    result_database = Path(result_database).resolve()
    output_dir = Path(output_dir).resolve()
    if not parent_database.is_file():
        raise FileNotFoundError(f"Clue Score V1 database is missing: {parent_database}")
    if result_database.exists() and not overwrite:
        raise FileExistsError(f"Resolved Direction result exists: {result_database}")
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
        with sqlite3.connect(temporary_database) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("ATTACH DATABASE ? AS parent", (str(parent_database),))
            connection.execute(
                "CREATE TABLE predictions AS SELECT p.*, "
                "p.predicted_direction AS v1_predicted_direction, "
                "p.result AS v1_result, NULL AS v2_config_sha256 "
                "FROM parent.predictions p WHERE p.match_safe=1 AND "
                "p.outcome_group IN "
                "('moved_toward_pathogenic','moved_toward_benign')"
            )
            rows = connection.execute(
                "SELECT variation_id,total_score,outcome_group FROM predictions"
            ).fetchall()
            rules_hash = resolved_config_sha256()
            for row in rows:
                prediction = binary_direction(int(row["total_score"]))
                result, reason, correct = binary_result(
                    prediction, row["outcome_group"]
                )
                confidence = (
                    "No prediction"
                    if prediction == "no_prediction"
                    else "Medium confidence"
                    if abs(int(row["total_score"])) >= 2
                    else "Low confidence"
                )
                rank = (
                    0
                    if result == "Wrong" and confidence == "Medium confidence"
                    else 1
                    if result == "Wrong"
                    else 2
                    if result == "Correct" and confidence == "Medium confidence"
                    else 3
                    if result == "Correct"
                    else 4
                )
                connection.execute(
                    "UPDATE predictions SET predicted_direction=?,confidence=?,"
                    "confidence_rank=?,result=?,result_reason_code=?,correct=?,"
                    "default_rank=?,scoring_version='Resolved Direction V2',"
                    "v2_config_sha256=? WHERE variation_id=?",
                    (
                        prediction,
                        confidence,
                        3
                        if prediction == "no_prediction"
                        else 1
                        if confidence.startswith("Medium")
                        else 2,
                        result,
                        reason,
                        correct,
                        rank,
                        rules_hash,
                        row["variation_id"],
                    ),
                )
            connection.executescript(
                """
                CREATE UNIQUE INDEX predictions_variation ON predictions(variation_id);
                CREATE INDEX predictions_default
                  ON predictions(default_rank,variation_sort);
                CREATE INDEX predictions_result_default
                  ON predictions(result,default_rank,variation_sort);
                CREATE INDEX predictions_direction
                  ON predictions(predicted_direction,variation_sort);
                CREATE INDEX predictions_gene ON predictions(old_gene_symbols);
                CREATE TABLE metadata (document TEXT NOT NULL);
                """
            )
            metrics = _metrics(connection)
            completed = datetime.now(UTC)
            metadata = {
                "schema_version": 1,
                "mode": "resolved_direction_full",
                "experiment_version": "Resolved Direction V2",
                "scoring_version": "Resolved Direction V2",
                "started_at_utc": started.isoformat(),
                "completed_at_utc": completed.isoformat(),
                "runtime_seconds": (completed - started).total_seconds(),
                "parent_database": str(parent_database),
                "parent_config_sha256": config["parent_config_sha256"],
                "config_sha256": rules_hash,
                "metrics": metrics,
                "conditional_task": True,
                "design_warning": config["design_warning"],
            }
            connection.execute(
                "INSERT INTO metadata VALUES (?)",
                (json.dumps(metadata, sort_keys=True),),
            )
            connection.commit()
            _export(connection, temporary_output, metrics, metadata)
        if output_dir.exists():
            if not overwrite:
                raise FileExistsError(f"Resolved Direction outputs exist: {output_dir}")
            shutil.rmtree(output_dir)
        temporary_output.replace(output_dir)
        if result_database.exists():
            result_database.unlink()
        temporary_database.replace(result_database)
        if parent_database == CLUE_SCORE_RESULTS_DB_PATH.resolve():
            report_path = PROJECT_ROOT / "research" / "resolved-direction-v2-results.md"
            report_path.write_text(
                (output_dir / "experiment_report.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return {
            **metadata,
            **metrics,
            "result_database_bytes": result_database.stat().st_size,
            "output_bytes": sum(
                path.stat().st_size for path in output_dir.rglob("*") if path.is_file()
            ),
        }
    except Exception:
        temporary_database.unlink(missing_ok=True)
        shutil.rmtree(temporary_output, ignore_errors=True)
        raise


def resolved_summary(result_database: Path) -> dict[str, Any]:
    path = Path(result_database).resolve()
    if not path.is_file():
        raise ResolvedDirectionError("Resolved Direction V2 has not been run yet.")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT document FROM metadata").fetchone()
        if row is None:
            raise ResolvedDirectionError("Resolved Direction metadata is missing.")
        metadata = json.loads(row[0])
        metrics = metadata.pop("metrics")
        return {**metadata, **metrics}
