"""Conservative proof-of-concept cross-release matching functions."""

from collections import defaultdict
from datetime import date

import pandas as pd

REQUIRED_COLUMNS = ("AlleleID", "VariationID", "ClinicalSignificance")
TIMELINE_COLUMNS = (
    "variant_id",
    "allele_id",
    "matched_variant_id",
    "gene",
    "old_classification",
    "new_classification",
    "old_review_status",
    "new_review_status",
    "old_submission_count",
    "new_submission_count",
    "old_release_date",
    "new_release_date",
    "classification_change",
    "match_status",
    "candidate_count",
    "old_source_row_count",
    "new_source_row_count",
    "old_source_row_ids",
    "new_source_row_ids",
    "old_assemblies",
    "new_assemblies",
)


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


def _normalized_identifier(value: object) -> str | None:
    """Return a clean identifier string or ``None`` for a missing value."""
    if pd.isna(value):
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith(".0") and normalized[:-2].isdigit():
        return normalized[:-2]
    return normalized


def _joined_values(values: pd.Series) -> str | None:
    """Join distinct nonempty values without hiding disagreement."""
    unique_values = sorted(
        {
            str(value).strip()
            for value in values
            if pd.notna(value) and str(value).strip()
        }
    )
    return " | ".join(unique_values) if unique_values else None


def _collapsed_entities(snapshot: pd.DataFrame, label: str) -> list[dict[str, object]]:
    """Collapse assembly duplicates while retaining differing metadata values."""
    required = {"variant_id", "allele_id", "classification", "release_date"}
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(f"{label} snapshot is missing columns: {', '.join(missing)}")

    prepared = snapshot.copy()
    prepared["variant_id"] = prepared["variant_id"].map(_normalized_identifier)
    prepared["allele_id"] = prepared["allele_id"].map(_normalized_identifier)
    for optional_column in (
        "gene",
        "review_status",
        "submission_count",
        "source_row_id",
        "assembly",
    ):
        if optional_column not in prepared.columns:
            prepared[optional_column] = pd.NA

    release_values = {
        str(value).strip()
        for value in prepared["release_date"]
        if pd.notna(value) and str(value).strip()
    }
    if len(release_values) != 1:
        raise ValueError(
            f"{label} snapshot must contain exactly one nonempty release date; "
            f"found {sorted(release_values)}."
        )
    release_date = next(iter(release_values))

    def build_entity(
        group: pd.DataFrame,
        allele_id: str | None,
        variant_id: str | None,
        *,
        is_complex_variant: bool,
    ) -> dict[str, object]:
        return {
            "allele_id": allele_id,
            "variant_id": variant_id,
            "gene": _joined_values(group["gene"]),
            "classification": _joined_values(group["classification"]),
            "review_status": _joined_values(group["review_status"]),
            "submission_count": _joined_values(group["submission_count"]),
            "source_row_ids": _joined_values(group["source_row_id"]),
            "assemblies": _joined_values(group["assembly"]),
            "release_date": release_date,
            "source_row_count": len(group),
            "is_complex_variant": is_complex_variant,
        }

    entities: list[dict[str, object]] = []
    by_variation = prepared.groupby("variant_id", dropna=False, sort=True)
    for raw_variant_id, variation_group in by_variation:
        variant_id = _normalized_identifier(raw_variant_id)
        allele_ids = sorted(
            {
                identifier
                for identifier in variation_group["allele_id"].map(
                    _normalized_identifier
                )
                if identifier is not None
            }
        )
        if variant_id is not None and len(allele_ids) > 1:
            entities.append(
                build_entity(
                    variation_group,
                    " | ".join(allele_ids),
                    variant_id,
                    is_complex_variant=True,
                )
            )
            continue

        by_allele = variation_group.groupby("allele_id", dropna=False, sort=True)
        for raw_allele_id, allele_group in by_allele:
            entities.append(
                build_entity(
                    allele_group,
                    _normalized_identifier(raw_allele_id),
                    variant_id,
                    is_complex_variant=False,
                )
            )
    return entities


def _is_vus(classification: object) -> bool:
    """Return whether a classification is an exact supported VUS term."""
    if classification is None or pd.isna(classification):
        return False
    normalized = str(classification).strip().casefold()
    return normalized in {
        "uncertain significance",
        "vus-high",
        "vus-mid",
        "vus-low",
    }


def classify_vus_change(new_classification: object, match_status: str) -> str:
    """Map a verified later classification to one conservative VUS outcome."""
    if match_status in {
        "ambiguous_multiple_candidates",
        "conflicting_identifiers",
        "unsupported_complex_identifier",
        "missing_identifier",
        "unmatched",
    }:
        return "Unable_to_Verify"
    if new_classification is None or pd.isna(new_classification):
        return "Unable_to_Verify"

    normalized = str(new_classification).strip().casefold()
    outcomes = {
        "pathogenic": "VUS_to_Pathogenic",
        "likely pathogenic": "VUS_to_Likely_Pathogenic",
        "benign": "VUS_to_Benign",
        "likely benign": "VUS_to_Likely_Benign",
        "uncertain significance": "VUS_to_Still_Uncertain",
        "vus-high": "VUS_to_Still_Uncertain",
        "vus-mid": "VUS_to_Still_Uncertain",
        "vus-low": "VUS_to_Still_Uncertain",
    }
    if normalized in outcomes:
        return outcomes[normalized]
    if "conflict" in normalized or " | " in normalized:
        return "VUS_to_Conflicting"
    return "Unable_to_Verify"


def match_variants_across_releases(
    older: pd.DataFrame, newer: pd.DataFrame
) -> pd.DataFrame:
    """Build an auditable timeline for variants that were initially VUS.

    Exact Variation ID and Allele ID pairs are preferred. A unique Allele ID can
    support a flagged changed-Variation-ID match. All other uncertain cases remain
    conflicting or unable to match. No coordinate inference is performed.
    """
    all_older_entities = _collapsed_entities(older, "Older")
    newer_entities = _collapsed_entities(newer, "Newer")
    older_entities = [
        entity for entity in all_older_entities if _is_vus(entity["classification"])
    ]

    try:
        older_date = date.fromisoformat(str(all_older_entities[0]["release_date"]))
        newer_date = date.fromisoformat(str(newer_entities[0]["release_date"]))
    except (IndexError, ValueError) as exc:
        raise ValueError("Release dates must use valid YYYY-MM-DD values.") from exc
    if older_date >= newer_date:
        raise ValueError(
            f"Older release date {older_date} must be before newer release date "
            f"{newer_date}."
        )
    if not older_entities:
        return pd.DataFrame(columns=TIMELINE_COLUMNS)

    by_pair: dict[tuple[str | None, str | None], list[dict[str, object]]] = defaultdict(
        list
    )
    by_variant: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    by_allele: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for entity in newer_entities:
        pair = (entity["allele_id"], entity["variant_id"])
        by_pair[pair].append(entity)
        if entity["variant_id"] is not None:
            by_variant[str(entity["variant_id"])].append(entity)
        if entity["allele_id"] is not None:
            by_allele[str(entity["allele_id"])].append(entity)

    results: list[dict[str, object]] = []
    for source in older_entities:
        allele_id = source["allele_id"]
        variant_id = source["variant_id"]
        target: dict[str, object] | None = None
        candidate_count = 0

        exact_candidates = by_pair.get((allele_id, variant_id), [])
        if source["is_complex_variant"]:
            match_status = "unsupported_complex_identifier"
            candidate_count = int(source["source_row_count"])
        elif allele_id is None and variant_id is None:
            match_status = "missing_identifier"
        elif (allele_id is not None and not str(allele_id).isdigit()) or (
            variant_id is not None and not str(variant_id).isdigit()
        ):
            match_status = "unsupported_complex_identifier"
        elif len(exact_candidates) == 1:
            if exact_candidates[0]["is_complex_variant"]:
                match_status = "unsupported_complex_identifier"
            else:
                match_status = "exact_identifier_match"
                target = exact_candidates[0]
                candidate_count = 1
        elif len(exact_candidates) > 1:
            match_status = "ambiguous_multiple_candidates"
            candidate_count = len(exact_candidates)
        elif variant_id is not None and by_variant.get(str(variant_id)):
            variant_candidates = by_variant[str(variant_id)]
            candidate_count = len(variant_candidates)
            if (
                len(variant_candidates) == 1
                and variant_candidates[0]["is_complex_variant"]
            ):
                match_status = "unsupported_complex_identifier"
            elif len(variant_candidates) == 1 and allele_id is None:
                match_status = "exact_variation_id_match"
                target = variant_candidates[0]
            else:
                match_status = "conflicting_identifiers"
        elif allele_id is not None and by_allele.get(str(allele_id)):
            allele_candidates = by_allele[str(allele_id)]
            candidate_count = len(allele_candidates)
            if len(allele_candidates) == 1:
                match_status = "allele_id_match_variation_changed"
                target = allele_candidates[0]
            else:
                match_status = "ambiguous_multiple_candidates"
        else:
            match_status = "unmatched"

        new_classification = target["classification"] if target else None
        results.append(
            {
                "variant_id": variant_id,
                "allele_id": allele_id,
                "matched_variant_id": target["variant_id"] if target else None,
                "gene": source["gene"],
                "old_classification": source["classification"],
                "new_classification": new_classification,
                "old_review_status": source["review_status"],
                "new_review_status": target["review_status"] if target else None,
                "old_submission_count": source["submission_count"],
                "new_submission_count": (
                    target["submission_count"] if target else None
                ),
                "old_release_date": source["release_date"],
                "new_release_date": (
                    target["release_date"]
                    if target
                    else newer_entities[0]["release_date"]
                    if newer_entities
                    else None
                ),
                "classification_change": classify_vus_change(
                    new_classification, match_status
                ),
                "match_status": match_status,
                "candidate_count": candidate_count,
                "old_source_row_count": source["source_row_count"],
                "new_source_row_count": (
                    target["source_row_count"] if target else None
                ),
                "old_source_row_ids": source["source_row_ids"],
                "new_source_row_ids": target["source_row_ids"] if target else None,
                "old_assemblies": source["assemblies"],
                "new_assemblies": target["assemblies"] if target else None,
            }
        )

    return pd.DataFrame.from_records(results, columns=TIMELINE_COLUMNS)
