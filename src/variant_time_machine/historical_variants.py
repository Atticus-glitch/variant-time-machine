"""Build and query a searchable two-snapshot ClinVar variant index."""

import csv
import gzip
import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from variant_time_machine.config import CLINVAR_RELEASES, ClinVarRelease

SOURCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("#AlleleID", "allele_id"),
    ("Type", "variant_type"),
    ("Name", "name"),
    ("GeneID", "gene_id"),
    ("GeneSymbol", "gene_symbol"),
    ("HGNC_ID", "hgnc_id"),
    ("ClinicalSignificance", "clinical_significance"),
    ("ClinSigSimple", "clin_sig_simple"),
    ("LastEvaluated", "last_evaluated"),
    ("RS# (dbSNP)", "rs_id"),
    ("nsv/esv (dbVar)", "dbvar_id"),
    ("RCVaccession", "rcv_accession"),
    ("PhenotypeIDS", "phenotype_ids"),
    ("PhenotypeList", "phenotype_list"),
    ("Origin", "origin"),
    ("OriginSimple", "origin_simple"),
    ("Assembly", "assembly"),
    ("ChromosomeAccession", "chromosome_accession"),
    ("Chromosome", "chromosome"),
    ("Start", "start_position"),
    ("Stop", "stop_position"),
    ("ReferenceAllele", "reference_allele"),
    ("AlternateAllele", "alternate_allele"),
    ("Cytogenetic", "cytogenetic"),
    ("ReviewStatus", "review_status"),
    ("NumberSubmitters", "number_submitters"),
    ("Guidelines", "guidelines"),
    ("TestedInGTR", "tested_in_gtr"),
    ("OtherIDs", "other_ids"),
    ("SubmitterCategories", "submitter_categories"),
    ("VariationID", "variation_id"),
    ("PositionVCF", "position_vcf"),
    ("ReferenceAlleleVCF", "reference_allele_vcf"),
    ("AlternateAlleleVCF", "alternate_allele_vcf"),
)
MAX_SOURCE_FIELD_BYTES = 10 * 1024 * 1024

INDEX_COLUMNS: tuple[str, ...] = (
    "variation_id",
    "old_allele_ids",
    "new_allele_ids",
    "old_gene_symbols",
    "new_gene_symbols",
    "old_names",
    "new_names",
    "old_classifications",
    "new_classifications",
    "old_last_evaluated",
    "new_last_evaluated",
    "old_review_statuses",
    "new_review_statuses",
    "old_submitter_counts",
    "new_submitter_counts",
    "old_rs_ids",
    "new_rs_ids",
    "old_phenotypes",
    "new_phenotypes",
    "old_coordinates",
    "new_coordinates",
    "old_release_date",
    "new_release_date",
    "change_status",
)


class HistoricalVariantDatabaseError(ValueError):
    """Raised when the searchable historical dataset is unavailable or invalid."""


def _create_schema(connection: sqlite3.Connection) -> None:
    source_fields = ",\n".join(f"{target} TEXT" for _, target in SOURCE_COLUMNS)
    connection.executescript(
        f"""
        CREATE TABLE source_records (
            release_role TEXT NOT NULL,
            release_date TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            {source_fields}
        );
        CREATE TABLE variant_release (
            release_role TEXT NOT NULL,
            release_date TEXT NOT NULL,
            variation_id TEXT NOT NULL,
            allele_ids TEXT,
            variant_types TEXT,
            names TEXT,
            gene_ids TEXT,
            gene_symbols TEXT,
            hgnc_ids TEXT,
            clinical_significances TEXT,
            clin_sig_simple_values TEXT,
            last_evaluated_dates TEXT,
            rs_ids TEXT,
            dbvar_ids TEXT,
            rcv_accessions TEXT,
            phenotype_ids TEXT,
            phenotypes TEXT,
            origins TEXT,
            origin_simple_values TEXT,
            assemblies TEXT,
            coordinates TEXT,
            cytogenetic_values TEXT,
            review_statuses TEXT,
            submitter_counts TEXT,
            guidelines_values TEXT,
            tested_in_gtr_values TEXT,
            other_ids_values TEXT,
            submitter_categories_values TEXT,
            source_row_count INTEGER NOT NULL,
            PRIMARY KEY (release_role, variation_id)
        );
        """
    )


def _source_values(row: Mapping[str, str]) -> tuple[str | None, ...]:
    return tuple(
        (row.get(source) or "").strip() or None for source, _ in SOURCE_COLUMNS
    )


def _ingest_release(
    connection: sqlite3.Connection,
    release: ClinVarRelease,
    role: str,
    archive_path: Path,
    *,
    batch_size: int,
    progress: Callable[[dict[str, object]], None] | None,
) -> int:
    targets = [target for _, target in SOURCE_COLUMNS]
    placeholders = ",".join("?" for _ in range(len(targets) + 3))
    statement = (
        "INSERT INTO source_records "
        f"(release_role, release_date, source_row_number, {','.join(targets)}) "
        f"VALUES ({placeholders})"
    )
    total = 0
    batch: list[tuple[object, ...]] = []
    with gzip.open(archive_path, mode="rt", encoding="utf-8", newline="") as source:
        csv.field_size_limit(MAX_SOURCE_FIELD_BYTES)
        reader = csv.DictReader(source, delimiter="\t")
        missing = [
            name for name, _ in SOURCE_COLUMNS if name not in (reader.fieldnames or [])
        ]
        if missing:
            raise HistoricalVariantDatabaseError(
                f"{archive_path.name} is missing columns: {', '.join(missing)}"
            )
        for row_number, row in enumerate(reader, start=1):
            batch.append(
                (
                    role,
                    release.release_date.isoformat(),
                    row_number,
                    *_source_values(row),
                )
            )
            if len(batch) >= batch_size:
                connection.executemany(statement, batch)
                total += len(batch)
                batch.clear()
                if progress:
                    progress({"stage": "ingest", "role": role, "rows": total})
        if batch:
            connection.executemany(statement, batch)
            total += len(batch)
    if progress:
        progress({"stage": "ingest_complete", "role": role, "rows": total})
    return total


def _build_release_summaries(connection: sqlite3.Connection) -> None:
    distinct = "GROUP_CONCAT(DISTINCT NULLIF({field}, ''))"
    coordinate = (
        "NULLIF(COALESCE(assembly, '') || ':' || COALESCE(chromosome, '') || ':' || "
        "COALESCE(start_position, '') || '-' || COALESCE(stop_position, '') || ' ' || "
        "COALESCE(reference_allele, '') || '>' || "
        "COALESCE(alternate_allele, ''), '::- >')"
    )
    fields = {
        "allele_ids": "allele_id",
        "variant_types": "variant_type",
        "names": "name",
        "gene_ids": "gene_id",
        "gene_symbols": "gene_symbol",
        "hgnc_ids": "hgnc_id",
        "clinical_significances": "clinical_significance",
        "clin_sig_simple_values": "clin_sig_simple",
        "last_evaluated_dates": "last_evaluated",
        "rs_ids": "rs_id",
        "dbvar_ids": "dbvar_id",
        "rcv_accessions": "rcv_accession",
        "phenotype_ids": "phenotype_ids",
        "phenotypes": "phenotype_list",
        "origins": "origin",
        "origin_simple_values": "origin_simple",
        "assemblies": "assembly",
        "coordinates": coordinate,
        "cytogenetic_values": "cytogenetic",
        "review_statuses": "review_status",
        "submitter_counts": "number_submitters",
        "guidelines_values": "guidelines",
        "tested_in_gtr_values": "tested_in_gtr",
        "other_ids_values": "other_ids",
        "submitter_categories_values": "submitter_categories",
    }
    projections = ",\n".join(
        f"{distinct.format(field=source)} AS {target}"
        if target != "coordinates"
        else f"GROUP_CONCAT(DISTINCT {source}) AS {target}"
        for target, source in fields.items()
    )
    connection.execute(
        f"""
        INSERT INTO variant_release
        SELECT release_role, release_date, variation_id,
               {projections},
               COUNT(*) AS source_row_count
        FROM source_records
        WHERE variation_id IS NOT NULL AND variation_id != ''
        GROUP BY release_role, release_date, variation_id
        """
    )


def _build_variant_index(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE variant_index AS
        WITH ids AS (
            SELECT DISTINCT variation_id FROM variant_release
        )
        SELECT
            ids.variation_id,
            CAST(ids.variation_id AS INTEGER) AS variation_sort,
            older.allele_ids AS old_allele_ids,
            newer.allele_ids AS new_allele_ids,
            older.gene_symbols AS old_gene_symbols,
            newer.gene_symbols AS new_gene_symbols,
            older.names AS old_names,
            newer.names AS new_names,
            older.clinical_significances AS old_classifications,
            newer.clinical_significances AS new_classifications,
            older.last_evaluated_dates AS old_last_evaluated,
            newer.last_evaluated_dates AS new_last_evaluated,
            older.review_statuses AS old_review_statuses,
            newer.review_statuses AS new_review_statuses,
            older.submitter_counts AS old_submitter_counts,
            newer.submitter_counts AS new_submitter_counts,
            older.rs_ids AS old_rs_ids,
            newer.rs_ids AS new_rs_ids,
            older.phenotypes AS old_phenotypes,
            newer.phenotypes AS new_phenotypes,
            older.coordinates AS old_coordinates,
            newer.coordinates AS new_coordinates,
            older.release_date AS old_release_date,
            newer.release_date AS new_release_date,
            CASE
                WHEN older.variation_id IS NULL THEN 'New_in_later_snapshot'
                WHEN newer.variation_id IS NULL THEN 'Missing_from_later_snapshot'
                WHEN COALESCE(older.clinical_significances, '') =
                     COALESCE(newer.clinical_significances, '')
                    THEN 'No_classification_change'
                ELSE 'Classification_changed'
            END AS change_status
        FROM ids
        LEFT JOIN variant_release AS older
          ON older.variation_id = ids.variation_id AND older.release_role = 'older'
        LEFT JOIN variant_release AS newer
          ON newer.variation_id = ids.variation_id AND newer.release_role = 'newer';

        CREATE UNIQUE INDEX variant_index_variation_id ON variant_index(variation_id);
        CREATE INDEX variant_index_sort ON variant_index(variation_sort, variation_id);
        CREATE INDEX variant_index_old_gene ON variant_index(old_gene_symbols);
        CREATE INDEX variant_index_new_gene ON variant_index(new_gene_symbols);
        CREATE INDEX variant_index_old_allele ON variant_index(old_allele_ids);
        CREATE INDEX variant_index_new_allele ON variant_index(new_allele_ids);
        CREATE INDEX variant_index_old_rs ON variant_index(old_rs_ids);
        CREATE INDEX variant_index_new_rs ON variant_index(new_rs_ids);
        CREATE INDEX variant_index_change ON variant_index(change_status);
        CREATE INDEX variant_index_vus_change
          ON variant_index(
            change_status, old_classifications, variation_sort, variation_id
          );
        """
    )


def build_historical_variant_database(
    archives: Mapping[str, Path],
    output_path: Path,
    *,
    releases: Mapping[str, ClinVarRelease] = CLINVAR_RELEASES,
    overwrite: bool = False,
    batch_size: int = 20_000,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Stream configured archives into an atomic indexed SQLite database."""
    output_path = Path(output_path).resolve()
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Historical variant database exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for role in releases:
        path = Path(archives[role]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"ClinVar archive does not exist: {path}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    row_counts: dict[str, int] = {}
    started = datetime.now(UTC)
    try:
        with sqlite3.connect(temporary) as connection:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=FILE")
            _create_schema(connection)
            for role, release in releases.items():
                row_counts[role] = _ingest_release(
                    connection,
                    release,
                    role,
                    Path(archives[role]),
                    batch_size=batch_size,
                    progress=progress,
                )
                connection.commit()
            if progress:
                progress({"stage": "summarize"})
            _build_release_summaries(connection)
            _build_variant_index(connection)
            variant_count = connection.execute(
                "SELECT COUNT(*) FROM variant_index"
            ).fetchone()[0]
            change_counts = dict(
                connection.execute(
                    "SELECT change_status, COUNT(*) FROM variant_index "
                    "GROUP BY change_status"
                ).fetchall()
            )
            metadata = {
                "schema_version": 1,
                "built_at_utc": datetime.now(UTC).isoformat(),
                "build_seconds": (datetime.now(UTC) - started).total_seconds(),
                "source_rows": row_counts,
                "variant_count": variant_count,
                "change_counts": change_counts,
                "releases": {
                    role: {
                        "release_date": release.release_date.isoformat(),
                        "source_url": release.source_url,
                        "archive_path": str(Path(archives[role]).resolve()),
                    }
                    for role, release in releases.items()
                },
            }
            connection.execute("CREATE TABLE metadata (document TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO metadata VALUES (?)", (json.dumps(metadata),)
            )
            connection.execute("DROP TABLE source_records")
            connection.commit()
            connection.execute("VACUUM")
            connection.execute("PRAGMA optimize")
        temporary.replace(output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return metadata


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    database_path = Path(database_path).resolve()
    if not database_path.is_file():
        raise HistoricalVariantDatabaseError(
            "The historical spreadsheet index has not been built yet."
        )
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def historical_database_metadata(database_path: Path) -> dict[str, object]:
    """Read build metadata from the historical database."""
    with _connect_read_only(database_path) as connection:
        row = connection.execute("SELECT document FROM metadata").fetchone()
        if row is None:
            raise HistoricalVariantDatabaseError("Historical metadata is missing.")
        value = json.loads(row["document"])
        if not isinstance(value, dict):
            raise HistoricalVariantDatabaseError("Historical metadata is invalid.")
        return value


def search_historical_variants(
    database_path: Path,
    *,
    query: str = "",
    change_status: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    """Return one safe, paginated spreadsheet page."""
    query = query.strip()
    if len(query) > 200:
        raise HistoricalVariantDatabaseError("Search is limited to 200 characters.")
    if page < 1 or page_size < 1 or page_size > 200:
        raise HistoricalVariantDatabaseError("Invalid page or page size.")
    allowed_statuses = {
        "",
        "Classification_changed",
        "No_classification_change",
        "New_in_later_snapshot",
        "Missing_from_later_snapshot",
        "VUS_updated",
    }
    if change_status not in allowed_statuses:
        raise HistoricalVariantDatabaseError("Unknown change-status filter.")

    clauses: list[str] = []
    parameters: list[object] = []
    if query:
        vcv_match = re.fullmatch(r"VCV0*(\d+)(?:\.\d+)?", query, re.IGNORECASE)
        rs_match = re.fullmatch(r"rs(\d+)", query, re.IGNORECASE)
        allele_match = re.fullmatch(r"allele\s*:\s*(\d+)", query, re.IGNORECASE)
        if vcv_match or query.isdigit():
            variation_id = (
                str(int(vcv_match.group(1))) if vcv_match else str(int(query))
            )
            clauses.append("variation_id = ?")
            parameters.append(variation_id)
        elif rs_match:
            clauses.append("(old_rs_ids = ? OR new_rs_ids = ?)")
            parameters.extend([rs_match.group(1)] * 2)
        elif allele_match:
            clauses.append("(old_allele_ids = ? OR new_allele_ids = ?)")
            parameters.extend([allele_match.group(1)] * 2)
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,29}", query):
            clauses.append("(old_gene_symbols = ? OR new_gene_symbols = ?)")
            parameters.extend([query.upper()] * 2)
        else:
            clauses.append("(old_names LIKE ? OR new_names LIKE ?)")
            parameters.extend([f"%{query}%"] * 2)
    if change_status == "VUS_updated":
        clauses.append(
            "change_status = 'Classification_changed' "
            "AND old_classifications = 'Uncertain significance'"
        )
    elif change_status:
        clauses.append("change_status = ?")
        parameters.append(change_status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    offset = (page - 1) * page_size
    with _connect_read_only(database_path) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM variant_index{where}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT {','.join(INDEX_COLUMNS)} FROM variant_index{where} "
            "ORDER BY variation_sort, variation_id LIMIT ? OFFSET ?",
            [*parameters, page_size, offset],
        ).fetchall()
    return {
        "rows": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": (total + page_size - 1) // page_size,
    }


def historical_variant_detail(
    database_path: Path, variation_id: str
) -> dict[str, object]:
    """Return all collapsed release fields for one exact Variation ID."""
    variation_id = variation_id.strip()
    if not variation_id.isdigit():
        raise HistoricalVariantDatabaseError("Variation ID must contain only digits.")
    with _connect_read_only(database_path) as connection:
        index = connection.execute(
            f"SELECT {','.join(INDEX_COLUMNS)} FROM variant_index "
            "WHERE variation_id = ?",
            (variation_id,),
        ).fetchone()
        if index is None:
            raise HistoricalVariantDatabaseError("Variation ID was not found.")
        snapshots = connection.execute(
            "SELECT * FROM variant_release WHERE variation_id = ? "
            "ORDER BY release_date",
            (variation_id,),
        ).fetchall()
    return {"variant": dict(index), "snapshots": [dict(row) for row in snapshots]}
