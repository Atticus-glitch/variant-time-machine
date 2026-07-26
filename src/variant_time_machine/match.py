"""Conservative proof-of-concept cross-release matching functions."""

from collections import defaultdict

import pandas as pd

REQUIRED_COLUMNS = ("AlleleID", "VariationID", "ClinicalSignificance")


def _prepare_snapshot(snapshot: pd.DataFrame, label: str) -> pd.DataFrame:
    """Validate and normalize identifier columns without changing the input."""
    missing = [column for column in REQUIRED_COLUMNS if column not in snapshot.columns]
    if missing:
        raise ValueError(f"{label} snapshot is missing columns: {', '.join(missing)}")

    prepared = snapshot.loc[:, REQUIRED_COLUMNS].copy()
    for column in ("AlleleID", "VariationID"):
        prepared[column] = (
            prepared[column]
            .astype("string")
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )
    prepared["ClinicalSignificance"] = prepared["ClinicalSignificance"].astype("string")
    return prepared


def _classification_by_entity(snapshot: pd.DataFrame) -> dict[tuple[str, str], str]:
    """Collect unique classifications for each AlleleID/VariationID entity."""
    classifications: dict[tuple[str, str], str] = {}
    for identifiers, group in snapshot.groupby(
        ["AlleleID", "VariationID"], dropna=False, sort=True
    ):
        values = sorted(group["ClinicalSignificance"].dropna().unique())
        classifications[identifiers] = "; ".join(values)
    return classifications


def match_variant_summary_snapshots(
    older: pd.DataFrame, newer: pd.DataFrame
) -> pd.DataFrame:
    """Match tiny ``variant_summary``-like snapshots using identifiers only.

    Duplicate rows for genome assemblies collapse into one entity. Exact AlleleID and
    VariationID pairs are preferred. A unique AlleleID candidate is retained but
    marked as an aggregation change. Ambiguous or conflicting identifiers are never
    resolved arbitrarily. This proof of concept does not infer record mergers, use
    coordinate fallback, or assign biological reclassification outcomes.
    """
    older_prepared = _prepare_snapshot(older, "Older")
    newer_prepared = _prepare_snapshot(newer, "Newer")

    older_classifications = _classification_by_entity(older_prepared)
    newer_classifications = _classification_by_entity(newer_prepared)
    newer_pairs = set(newer_classifications)

    variations_by_allele: defaultdict[str, set[str]] = defaultdict(set)
    alleles_by_variation: defaultdict[str, set[str]] = defaultdict(set)
    for allele_id, variation_id in newer_pairs:
        if pd.notna(allele_id) and pd.notna(variation_id):
            variations_by_allele[allele_id].add(variation_id)
            alleles_by_variation[variation_id].add(allele_id)

    source_row_counts = older_prepared.value_counts(
        subset=["AlleleID", "VariationID"], dropna=False
    )
    results: list[dict[str, object]] = []

    for (allele_id, variation_id), older_classification in sorted(
        older_classifications.items(), key=lambda item: tuple(map(str, item[0]))
    ):
        target_variation_id: str | None = None
        newer_classification: str | None = None
        candidate_count = 0

        if pd.isna(allele_id) or pd.isna(variation_id):
            status = "missing_identifier"
        elif not allele_id.isdigit() or not variation_id.isdigit():
            status = "unsupported_complex_identifier"
        elif (allele_id, variation_id) in newer_pairs:
            status = "exact_identifier_match"
            target_variation_id = variation_id
            newer_classification = newer_classifications[(allele_id, variation_id)]
            candidate_count = 1
        else:
            allele_candidates = variations_by_allele.get(allele_id, set())
            candidate_count = len(allele_candidates)
            if len(allele_candidates) == 1:
                status = "allele_id_match_variation_changed"
                target_variation_id = next(iter(allele_candidates))
                newer_classification = newer_classifications[
                    (allele_id, target_variation_id)
                ]
            elif len(allele_candidates) > 1:
                status = "ambiguous_multiple_candidates"
            elif variation_id in alleles_by_variation:
                status = "conflicting_identifiers"
                candidate_count = len(alleles_by_variation[variation_id])
            else:
                status = "unmatched"

        results.append(
            {
                "source_allele_id": allele_id,
                "source_variation_id": variation_id,
                "target_variation_id": target_variation_id,
                "older_classification": older_classification,
                "newer_classification": newer_classification,
                "match_status": status,
                "candidate_count": candidate_count,
                "source_row_count": int(
                    source_row_counts.loc[(allele_id, variation_id)]
                ),
            }
        )

    return pd.DataFrame.from_records(results)


def match_variants_across_releases() -> None:
    """Build a full timeline only after the proof of concept is manually audited."""
    raise NotImplementedError(
        "Full cross-release timeline construction remains intentionally unimplemented. "
        "Only the identifier-only proof-of-concept matcher is currently available."
    )
