"""Parse ClinVar summary files into an auditable internal table."""

import re
from datetime import date
from pathlib import Path

import pandas as pd

STANDARD_COLUMNS: tuple[str, ...] = (
    "data_notice",
    "source_row_id",
    "variant_id",
    "allele_id",
    "variation_id",
    "gene",
    "assembly",
    "chromosome",
    "chromosome_accession",
    "position",
    "stop_position",
    "reference_allele",
    "alternate_allele",
    "classification",
    "review_status",
    "submission_count",
    "condition_accessions",
    "phenotype_list",
    "release_date",
)

RAW_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "allele_id": ("#AlleleID", "AlleleID"),
    "variation_id": ("VariationID",),
    "gene": ("GeneSymbol",),
    "assembly": ("Assembly",),
    "chromosome": ("Chromosome",),
    "chromosome_accession": ("ChromosomeAccession",),
    "position": ("Start",),
    "stop_position": ("Stop",),
    "reference_allele": ("ReferenceAllele",),
    "alternate_allele": ("AlternateAllele",),
    "classification": ("ClinicalSignificance",),
    "review_status": ("ReviewStatus",),
    "submission_count": ("NumberSubmitters",),
    "condition_accessions": ("RCVaccession",),
    "phenotype_list": ("PhenotypeList",),
}

REQUIRED_RAW_FIELDS: tuple[str, ...] = (
    "allele_id",
    "variation_id",
    "gene",
    "assembly",
    "chromosome",
    "position",
    "stop_position",
    "reference_allele",
    "alternate_allele",
    "classification",
    "review_status",
    "submission_count",
)


def _clean_text(series: pd.Series) -> pd.Series:
    """Trim text and represent empty strings as missing values."""
    cleaned = series.astype("string").str.strip()
    return cleaned.mask(cleaned == "")


def _first_available_column(
    table: pd.DataFrame, candidates: tuple[str, ...]
) -> pd.Series:
    """Return the first named source column or a missing-value series."""
    for candidate in candidates:
        if candidate in table.columns:
            return _clean_text(table[candidate])
    return pd.Series(pd.NA, index=table.index, dtype="string")


def _normalize_standard_table(
    table: pd.DataFrame, release_date: date | str | None
) -> pd.DataFrame:
    """Normalize a table that already uses internal column names."""
    normalized = table.copy()
    for column in STANDARD_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA

    if release_date is not None:
        release_value = (
            release_date.isoformat() if isinstance(release_date, date) else release_date
        )
        normalized["release_date"] = normalized["release_date"].fillna(release_value)

    normalized["variant_id"] = _clean_text(normalized["variant_id"])
    normalized["allele_id"] = _clean_text(normalized["allele_id"])
    normalized["variation_id"] = _clean_text(normalized["variation_id"])
    normalized["classification"] = _clean_text(normalized["classification"])
    normalized["release_date"] = _clean_text(normalized["release_date"])
    normalized["submission_count"] = pd.to_numeric(
        normalized["submission_count"], errors="coerce"
    ).astype("Int64")
    normalized["position"] = pd.to_numeric(
        normalized["position"], errors="coerce"
    ).astype("Int64")
    normalized["stop_position"] = pd.to_numeric(
        normalized["stop_position"], errors="coerce"
    ).astype("Int64")
    return normalized.loc[:, STANDARD_COLUMNS]


def parse_variant_summary(
    table: pd.DataFrame, release_date: date | str
) -> pd.DataFrame:
    """Convert an NCBI ``variant_summary`` table to the internal schema."""
    release_value = (
        release_date.isoformat() if isinstance(release_date, date) else release_date
    )
    if not release_value:
        raise ValueError("A release date is required for a ClinVar archive table.")

    missing_headers = [
        field
        for field in REQUIRED_RAW_FIELDS
        if not any(
            candidate in table.columns for candidate in RAW_COLUMN_CANDIDATES[field]
        )
    ]
    if missing_headers:
        raise ValueError(
            "ClinVar table is missing required fields: " + ", ".join(missing_headers)
        )

    parsed = pd.DataFrame(index=table.index)
    parsed["data_notice"] = pd.NA
    parsed["source_row_id"] = table.index.astype("string")
    for target, candidates in RAW_COLUMN_CANDIDATES.items():
        parsed[target] = _first_available_column(table, candidates)

    if parsed["variation_id"].isna().all():
        raise ValueError(
            "ClinVar table does not contain a VariationID column. Check the file "
            "format and header."
        )
    if parsed["classification"].isna().all():
        raise ValueError(
            "ClinVar table does not contain a ClinicalSignificance column."
        )

    parsed["variant_id"] = parsed["variation_id"]
    parsed["release_date"] = release_value
    return _normalize_standard_table(parsed, release_value)


def parse_clinvar_release(
    input_path: Path, release_date: date | str | None = None
) -> pd.DataFrame:
    """Read a TSV, compressed TSV, or standardized CSV into the internal schema."""
    input_path = Path(input_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"ClinVar input file does not exist: {input_path}")

    is_csv = input_path.suffix.lower() == ".csv"
    separator = "," if is_csv else "\t"
    table = pd.read_csv(
        input_path,
        sep=separator,
        dtype="string",
        keep_default_na=False,
        low_memory=False,
    )

    if {"variant_id", "classification"}.issubset(table.columns):
        return _normalize_standard_table(table, release_date)
    if release_date is None:
        raise ValueError(
            "A release date is required when parsing a raw ClinVar archive file."
        )
    release_value = (
        release_date.isoformat() if isinstance(release_date, date) else release_date
    )
    archive_month = re.search(r"variant_summary_(\d{4}-\d{2})", input_path.name)
    if archive_month and archive_month.group(1) != release_value[:7]:
        raise ValueError(
            f"Release date {release_value} does not match archive filename "
            f"{input_path.name}."
        )
    return parse_variant_summary(table, release_value)
