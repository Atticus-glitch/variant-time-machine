"""Tests for prediction-first Clue Score V1 experiment artifacts."""

import json
import sqlite3
from pathlib import Path

import pytest

from variant_time_machine.clue_score_experiment import (
    OUTPUT_FILENAMES,
    list_predictions,
    load_prediction_reviews,
    prediction_detail,
    prediction_summary,
    run_clue_score_experiment,
    update_prediction_review,
)
from website.dashboard.app import create_app


def source_database(path: Path) -> None:
    """Create four tiny two-snapshot records with declared outcomes."""
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE variant_release (
                release_role TEXT, release_date TEXT, variation_id TEXT,
                allele_ids TEXT, variant_types TEXT, names TEXT,
                gene_symbols TEXT, clinical_significances TEXT,
                last_evaluated_dates TEXT, review_statuses TEXT,
                submitter_counts TEXT, phenotypes TEXT, coordinates TEXT,
                guidelines_values TEXT, origin_simple_values TEXT
            )
            """
        )
        older = [
            (
                "1",
                "NM_1.1(G1):c.10del (p.Arg4fs)",
                "G1",
                "criteria provided, single submitter",
                "germline",
            ),
            (
                "2",
                "NM_2.1(G2):c.12A>G (p.Arg4=)",
                "G2",
                "criteria provided, single submitter",
                "germline",
            ),
            (
                "3",
                "unrecognized variant",
                "G3",
                "no assertion criteria provided",
                "germline",
            ),
            (
                "4",
                "NM_4.1(G4):c.10A>G (p.Arg4Gly)",
                "G4",
                "criteria provided, single submitter",
                "unknown",
            ),
        ]
        for identifier, name, gene, review, origin in older:
            connection.execute(
                "INSERT INTO variant_release VALUES "
                "('older','2022-01-06',?,?,?,?,?,'Uncertain significance',"
                "'Jan 01, 2020',?,'1','Condition','GRCh38:1:1-1 A>G','-',?)",
                (
                    identifier,
                    identifier,
                    "single nucleotide variant",
                    name,
                    gene,
                    review,
                    origin,
                ),
            )
        newer = {
            "1": "Pathogenic",
            "2": "Pathogenic",
            "3": "Uncertain significance",
            "4": "Benign",
        }
        for identifier, classification in newer.items():
            connection.execute(
                "INSERT INTO variant_release VALUES "
                "('newer','2024-01-04',? ,?,'single nucleotide variant',"
                "'new name','G' || ?,?,'Jan 01, 2024','criteria provided, "
                "single submitter','1','Condition','GRCh38:1:1-1 A>G','-',"
                "'germline')",
                (identifier, identifier, identifier, classification),
            )


def test_experiment_saves_predictions_before_comparison_and_exports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    result = tmp_path / "results.sqlite3"
    outputs = tmp_path / "outputs"
    source_database(source)
    events: list[str] = []

    summary = run_clue_score_experiment(
        source,
        result,
        outputs,
        progress=lambda event: events.append(str(event["stage"])),
    )

    assert events.index("predictions_saved") < events.index("outcomes_compared")
    assert summary["eligible_older_vus_records"] == 4
    assert summary["correct"] == 1
    assert summary["wrong"] == 1
    assert summary["no_prediction"] == 1
    assert summary["not_scorable"] == 1
    assert summary["overall_accuracy"] == 0.5
    assert set(OUTPUT_FILENAMES).issubset(path.name for path in outputs.iterdir())
    assert prediction_summary(result)["config_sha256"] == summary["config_sha256"]

    listed = list_predictions(result, result_filter="wrong")
    assert listed["total"] == 1
    assert listed["rows"][0]["variation_id"] == "2"
    detail = prediction_detail(result, "1")
    assert detail["arithmetic"].endswith("= +5")
    assert detail["result"] == "Correct"
    assert any(clue["points"] == 4 for clue in detail["clues"])
    assert detail["prediction_saved_at_utc"] < detail["compared_at_utc"]

    review_path = tmp_path / "dashboard_reviews.json"
    client = create_app(
        {
            "TESTING": True,
            "CLUE_SCORE_RESULTS_DB_PATH": result,
            "CLUE_SCORE_RESULTS_DIR": outputs,
            "CLUE_SCORE_REVIEW_PATH": review_path,
        }
    ).test_client()
    assert client.get("/prediction_results.html").status_code == 200
    assert client.get("/api/predictions/summary").get_json()["available"] is True
    assert client.get("/api/predictions?filter=wrong").get_json()["total"] == 1
    assert client.get("/api/predictions/1").get_json()["result"] == "Correct"
    saved_review = client.patch(
        "/api/predictions/1/review",
        json={"status": "correctly_matched", "note": "Checked."},
    )
    assert saved_review.status_code == 200
    metrics_download = client.get("/api/predictions/download/metric_summary.json")
    assert metrics_download.status_code == 200
    assert client.get("/api/predictions/download/unknown.txt").status_code == 404
    assert client.post("/api/predictions/run", json={}).status_code == 428


def test_reviews_are_sparse_separate_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    assert load_prediction_reviews(path)["reviews"] == {}

    review = update_prediction_review(
        "1", {"status": "correctly_matched", "note": "Identifiers checked."}, path
    )

    assert review["correctly_matched"] is True
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["reviews"]["1"]["notes"] == ["Identifiers checked."]
    with pytest.raises(ValueError, match="require a note"):
        update_prediction_review("2", {"status": "ambiguous", "note": ""}, path)
