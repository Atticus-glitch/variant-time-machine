"""Tests for the searchable two-snapshot ClinVar spreadsheet."""

import csv
import gzip
from datetime import date
from pathlib import Path

from variant_time_machine.config import ClinVarRelease
from variant_time_machine.historical_variants import (
    SOURCE_COLUMNS,
    build_historical_variant_database,
    historical_database_metadata,
    historical_variant_detail,
    search_historical_variants,
)
from website.dashboard.app import create_app


def write_archive(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a tiny archive with the complete official header shape."""
    headers = [source for source, _ in SOURCE_COLUMNS]
    with gzip.open(path, mode="wt", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_build_search_and_detail_preserve_two_release_states(tmp_path: Path) -> None:
    older = tmp_path / "older.gz"
    newer = tmp_path / "newer.gz"
    database = tmp_path / "history.sqlite3"
    base = {
        "#AlleleID": "10",
        "Type": "single nucleotide variant",
        "Name": "NM_000001.1:c.1A>G",
        "GeneSymbol": "GENE1",
        "ClinicalSignificance": "Uncertain significance",
        "LastEvaluated": "Dec 1, 2021",
        "RS# (dbSNP)": "123",
        "PhenotypeList": "Example condition",
        "ReviewStatus": "criteria provided, single submitter",
        "NumberSubmitters": "1",
        "VariationID": "100",
        "Assembly": "GRCh38",
        "Chromosome": "1",
        "Start": "1000",
        "Stop": "1000",
        "ReferenceAllele": "A",
        "AlternateAllele": "G",
    }
    write_archive(older, [base])
    write_archive(
        newer,
        [
            {
                **base,
                "ClinicalSignificance": "Pathogenic",
                "LastEvaluated": "Jan 2, 2024",
                "NumberSubmitters": "3",
            },
            {
                **base,
                "#AlleleID": "20",
                "VariationID": "200",
                "GeneSymbol": "GENE2",
                "Name": "NM_000002.1:c.2C>T",
                "RS# (dbSNP)": "456",
            },
        ],
    )
    releases = {
        "older": ClinVarRelease("older", date(2022, 1, 6), "https://old", 1),
        "newer": ClinVarRelease("newer", date(2024, 1, 4), "https://new", 1),
    }

    metadata = build_historical_variant_database(
        {"older": older, "newer": newer}, database, releases=releases
    )

    assert metadata["source_rows"] == {"older": 1, "newer": 2}
    assert metadata["variant_count"] == 2
    assert historical_database_metadata(database)["change_counts"] == {
        "Classification_changed": 1,
        "New_in_later_snapshot": 1,
    }
    page = search_historical_variants(database, query="GENE1")
    assert page["total"] == 1
    assert page["rows"][0]["old_classifications"] == "Uncertain significance"
    assert page["rows"][0]["new_classifications"] == "Pathogenic"
    assert page["rows"][0]["old_release_date"] == "2022-01-06"
    assert search_historical_variants(database, query="VCV000000100")["total"] == 1
    assert search_historical_variants(database, query="rs123")["total"] == 1
    assert search_historical_variants(database, query="allele: 10")["total"] == 1
    vus_updates = search_historical_variants(database, change_status="VUS_updated")
    assert vus_updates["total"] == 1
    assert vus_updates["rows"][0]["new_classifications"] == "Pathogenic"
    detail = historical_variant_detail(database, "100")
    assert len(detail["snapshots"]) == 2
    assert detail["snapshots"][0]["last_evaluated_dates"] == "Dec 1, 2021"
    assert detail["snapshots"][1]["last_evaluated_dates"] == "Jan 2, 2024"

    client = create_app(
        {"TESTING": True, "HISTORICAL_VARIANT_DB_PATH": database}
    ).test_client()
    assert client.get("/historical_variants.html").status_code == 200
    overview = client.get("/overview.html")
    assert overview.status_code == 200
    assert "What To Do" in overview.get_data(as_text=True)
    response = client.get("/api/historical-variants?query=GENE1&page_size=25")
    assert response.status_code == 200
    assert response.get_json()["rows"][0]["variation_id"] == "100"
    filtered = client.get(
        "/api/historical-variants?change_status=VUS_updated&page_size=1"
    )
    assert filtered.status_code == 200
    assert filtered.get_json()["total"] == 1
    assert client.get("/api/historical-variants/100").status_code == 200


def test_search_filters_and_paginates(tmp_path: Path) -> None:
    older = tmp_path / "older.gz"
    newer = tmp_path / "newer.gz"
    database = tmp_path / "history.sqlite3"
    rows = [
        {
            "#AlleleID": str(number),
            "VariationID": str(number),
            "GeneSymbol": "GENE",
            "Name": f"variant {number}",
            "ClinicalSignificance": "Benign",
        }
        for number in range(1, 4)
    ]
    write_archive(older, rows)
    write_archive(newer, rows)
    releases = {
        "older": ClinVarRelease("older", date(2022, 1, 6), "https://old", 1),
        "newer": ClinVarRelease("newer", date(2024, 1, 4), "https://new", 1),
    }
    build_historical_variant_database(
        {"older": older, "newer": newer}, database, releases=releases
    )

    page = search_historical_variants(
        database, change_status="No_classification_change", page=2, page_size=2
    )
    assert page["total"] == 3
    assert page["page_count"] == 2
    assert [row["variation_id"] for row in page["rows"]] == ["3"]


def test_builder_accepts_large_official_text_fields(tmp_path: Path) -> None:
    older = tmp_path / "older.gz"
    newer = tmp_path / "newer.gz"
    database = tmp_path / "history.sqlite3"
    row = {
        "#AlleleID": "1",
        "VariationID": "1",
        "GeneSymbol": "GENE",
        "ClinicalSignificance": "Uncertain significance",
        "PhenotypeList": "x" * 150_000,
    }
    write_archive(older, [row])
    write_archive(newer, [row])
    releases = {
        "older": ClinVarRelease("older", date(2022, 1, 6), "https://old", 1),
        "newer": ClinVarRelease("newer", date(2024, 1, 4), "https://new", 1),
    }

    build_historical_variant_database(
        {"older": older, "newer": newer}, database, releases=releases
    )

    detail = historical_variant_detail(database, "1")
    assert len(detail["snapshots"][0]["phenotypes"]) == 150_000
