"""Frozen, leakage-safe Clue Score V1 rules and outcome comparison."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from variant_time_machine.config import PROJECT_ROOT

CLUE_SCORE_V1_PATH = PROJECT_ROOT / "config" / "clue_score_v1.yaml"
OLDER_SCORING_FIELDS: tuple[str, ...] = (
    "variation_id",
    "allele_ids",
    "variant_types",
    "names",
    "gene_symbols",
    "clinical_significances",
    "last_evaluated_dates",
    "review_statuses",
    "submitter_counts",
    "phenotypes",
    "coordinates",
    "guidelines_values",
    "origin_simple_values",
    "release_date",
)
FORBIDDEN_SCORING_FIELD_FRAGMENTS: tuple[str, ...] = (
    "new_",
    "newer",
    "2024",
    "outcome",
    "answer",
    "actual",
)

PredictionDirection = Literal[
    "pathogenic_direction",
    "benign_direction",
    "remain_uncertain",
    "no_prediction",
]
OutcomeGroup = Literal[
    "moved_toward_pathogenic",
    "moved_toward_benign",
    "remained_uncertain",
    "conflicting_or_unusable",
]


class ClueScoreError(ValueError):
    """Raised when frozen scoring configuration or input is unsafe."""


@dataclass(frozen=True)
class OlderSnapshot:
    """Explicit whitelist of fields available at the prediction snapshot."""

    variation_id: str
    allele_ids: str | None
    variant_types: str | None
    names: str | None
    gene_symbols: str | None
    clinical_significances: str | None
    last_evaluated_dates: str | None
    review_statuses: str | None
    submitter_counts: str | None
    phenotypes: str | None
    coordinates: str | None
    guidelines_values: str | None
    origin_simple_values: str | None
    release_date: str


@dataclass(frozen=True)
class ClueResult:
    """One auditable clue evaluation."""

    clue: str
    older_value: str | None
    points: int
    explanation: str
    source_field: str
    available: bool
    applied: bool


@dataclass(frozen=True)
class Prediction:
    """Prediction produced before any newer-snapshot outcome is loaded."""

    variation_id: str
    total_score: int
    predicted_direction: PredictionDirection
    confidence: str
    consequence: str
    clues: tuple[ClueResult, ...]
    clues_used: tuple[str, ...]
    clues_missing: tuple[str, ...]
    warnings: tuple[str, ...]
    arithmetic: str
    scoring_version: str
    config_sha256: str


@dataclass(frozen=True)
class NormalizedOutcome:
    """Strict interpretation of newer aggregate classification text."""

    original_classification: str | None
    group: OutcomeGroup
    reason_code: str
    rule: str
    scorable: bool


@dataclass(frozen=True)
class Comparison:
    """Directional correctness assigned after prediction is frozen."""

    result: str
    reason_code: str
    correct: bool | None


def load_clue_score_config(path: Path = CLUE_SCORE_V1_PATH) -> dict[str, Any]:
    """Load the JSON-compatible YAML without adding a runtime YAML dependency."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClueScoreError(f"Could not load Clue Score V1: {exc}") from exc
    if not isinstance(config, dict) or config.get("scoring_version") != "Clue Score V1":
        raise ClueScoreError("Clue Score V1 configuration is invalid.")
    if config.get("status") != "frozen":
        raise ClueScoreError("Scoring configuration must be frozen before evaluation.")
    return config


def config_sha256(path: Path = CLUE_SCORE_V1_PATH) -> str:
    """Return the permanent content identity of the frozen scoring file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_leakage_safe_fields(fields: tuple[str, ...] = OLDER_SCORING_FIELDS) -> None:
    """Fail if a declared scoring input resembles outcome-snapshot information."""
    unsafe = [
        field
        for field in fields
        if any(
            fragment in field.casefold()
            for fragment in FORBIDDEN_SCORING_FIELD_FRAGMENTS
        )
    ]
    if unsafe:
        raise ClueScoreError(
            "Future-information scoring fields are forbidden: " + ", ".join(unsafe)
        )


def older_snapshot_from_row(row: Mapping[str, object]) -> OlderSnapshot:
    """Copy only the explicit older whitelist from a database row."""
    assert_leakage_safe_fields()

    def text(field: str) -> str | None:
        value = row.get(field)
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    variation_id = text("variation_id")
    release_date = text("release_date")
    if variation_id is None or release_date is None:
        raise ClueScoreError("Older Variation ID and release date are required.")
    values = {field: text(field) for field in OLDER_SCORING_FIELDS}
    return OlderSnapshot(
        variation_id=variation_id,
        allele_ids=values["allele_ids"],
        variant_types=values["variant_types"],
        names=values["names"],
        gene_symbols=values["gene_symbols"],
        clinical_significances=values["clinical_significances"],
        last_evaluated_dates=values["last_evaluated_dates"],
        review_statuses=values["review_statuses"],
        submitter_counts=values["submitter_counts"],
        phenotypes=values["phenotypes"],
        coordinates=values["coordinates"],
        guidelines_values=values["guidelines_values"],
        origin_simple_values=values["origin_simple_values"],
        release_date=release_date,
    )


def _is_missing(value: str | None) -> bool:
    return value is None or value.strip().casefold() in {"", "-", "na", "not provided"}


def _consequence(name: str | None) -> str:
    """Assign one conservative HGVS consequence using frozen precedence."""
    if _is_missing(name):
        return "unrecognized"
    value = str(name)
    protein = re.search(r"p\.\(?([^)\s,;]+)\)?", value, re.IGNORECASE)
    protein_text = protein.group(1) if protein else ""
    if re.search(r"fs(?:Ter|\*|\d|$)", protein_text, re.IGNORECASE) or re.search(
        r"(?:[A-Z][a-z]{2}|[A-Z])\d+(?:Ter|\*)", protein_text
    ):
        return "loss_of_function"
    if re.search(
        r"(?:\+|-)(?:1|2)(?:[A-Z]>[A-Z]|_|del|dup|ins)", value, re.IGNORECASE
    ) or re.search(r"splice[ _-]?(?:donor|acceptor)", value, re.IGNORECASE):
        return "canonical_splice"
    if "=" in protein_text or "synonymous" in value.casefold():
        return "synonymous"
    if re.search(r"p\.\(?.*(?:delins|del|dup|ins)", value, re.IGNORECASE):
        return "inframe_indel"
    if protein and re.fullmatch(
        r"(?:[A-Z][a-z]{2}|[A-Z])\d+(?:[A-Z][a-z]{2}|[A-Z])",
        protein_text,
    ):
        return "missense"
    if re.search(r"\bNR_\d+", value, re.IGNORECASE) or re.search(
        r":(?:n\.|c\.(?:-|\*))", value, re.IGNORECASE
    ):
        return "noncoding"
    intronic = re.search(r"c\.\d+(?:\+|-)(\d+)", value, re.IGNORECASE)
    if intronic and int(intronic.group(1)) > 2:
        return "noncoding"
    return "unrecognized"


def _max_submitters(value: str | None) -> int | None:
    if _is_missing(value):
        return None
    numbers = [int(item) for item in re.findall(r"\d+", str(value))]
    return max(numbers) if numbers else None


def _classification_age(
    value: str | None, snapshot_date: str
) -> tuple[int | None, str]:
    if _is_missing(value):
        return None, "No single parseable LastEvaluated date was available."
    try:
        evaluated = datetime.strptime(str(value), "%b %d, %Y").date()
        snapshot = date.fromisoformat(snapshot_date)
    except ValueError:
        return None, "No single parseable LastEvaluated date was available."
    age = (snapshot - evaluated).days
    if age < 0:
        return None, "LastEvaluated was after the snapshot date and was not used."
    return age, f"The classification was last evaluated {age} days before the snapshot."


def _clue(
    name: str,
    value: str | None,
    points: int,
    explanation: str,
    source: str,
    *,
    available: bool,
    applied: bool,
) -> ClueResult:
    return ClueResult(
        name, value, points if applied else 0, explanation, source, available, applied
    )


def score_older_snapshot(
    older: OlderSnapshot,
    config: Mapping[str, Any] | None = None,
    frozen_config_sha256: str | None = None,
) -> Prediction:
    """Score one older snapshot without accepting or reading newer fields."""
    assert_leakage_safe_fields()
    rules = dict(config or load_clue_score_config())
    if older.clinical_significances != rules["eligible_older_classification"]:
        raise ClueScoreError("Scoring requires exact older Uncertain significance.")
    if older.release_date != rules["prediction_date"]:
        raise ClueScoreError("Older snapshot date does not match the frozen formula.")

    consequence = _consequence(older.names)
    clue_results: list[ClueResult] = []
    consequence_rules = {
        "loss_of_function": ("loss_of_function_consequence", 4),
        "canonical_splice": ("canonical_splice_consequence", 3),
        "missense": ("missense_consequence", 1),
        "synonymous": ("synonymous_consequence", -3),
        "noncoding": ("noncoding_consequence", -1),
    }
    for category, (name, points) in consequence_rules.items():
        applied = consequence == category
        clue_results.append(
            _clue(
                name,
                older.names,
                points,
                f"Consequence was classified as {consequence} from older HGVS text.",
                "names",
                available=not _is_missing(older.names),
                applied=applied,
            )
        )

    review = (older.review_statuses or "").casefold()
    submitters = _max_submitters(older.submitter_counts)
    expert = review == "reviewed by expert panel"
    multiple = review == "criteria provided, multiple submitters, no conflicts" and (
        submitters is not None and submitters >= 2
    )
    conflict = ("conflicting" in review or "conflicts" in review) and (
        "no conflicts" not in review
    )
    criteria = review.startswith("criteria provided") and not conflict
    clue_results.extend(
        (
            _clue(
                "expert_panel_review",
                older.review_statuses,
                2,
                "Older review status was checked for exact expert-panel review.",
                "review_statuses",
                available=bool(review),
                applied=expert,
            ),
            _clue(
                "multiple_agreeing_submitters",
                older.submitter_counts,
                1,
                "Required multiple submitters, criteria, and no aggregate conflict.",
                "review_statuses, submitter_counts",
                available=bool(review) and submitters is not None,
                applied=multiple,
            ),
            _clue(
                "criteria_without_conflict",
                older.review_statuses,
                1,
                "Older review status was checked for provided criteria without "
                "conflict.",
                "review_statuses",
                available=bool(review),
                applied=criteria,
            ),
            _clue(
                "conflict_warning",
                older.review_statuses,
                0,
                "Conflict changes confidence but never adds directional points.",
                "review_statuses",
                available=bool(review),
                applied=conflict,
            ),
        )
    )

    age_days, age_explanation = _classification_age(
        older.last_evaluated_dates, older.release_date
    )
    clue_results.append(
        _clue(
            "classification_age",
            older.last_evaluated_dates,
            0,
            age_explanation,
            "last_evaluated_dates",
            available=age_days is not None,
            applied=age_days is not None,
        )
    )
    completeness_values = {
        "gene_symbols": older.gene_symbols,
        "coordinates": older.coordinates,
        "phenotypes": older.phenotypes,
        "review_statuses": older.review_statuses,
        "submitter_counts": older.submitter_counts,
        "names": older.names,
    }
    missing = tuple(
        name for name, value in completeness_values.items() if _is_missing(value)
    )
    clue_results.append(
        _clue(
            "record_completeness",
            ", ".join(missing) if missing else "No core older fields missing",
            0,
            "Missing older fields lower confidence but do not change direction.",
            ", ".join(completeness_values),
            available=True,
            applied=True,
        )
    )

    total = sum(item.points for item in clue_results)
    informative = [item for item in clue_results if item.applied and item.points != 0]
    thresholds = rules["thresholds"]
    if not informative:
        direction: PredictionDirection = "no_prediction"
    elif total >= int(thresholds["pathogenic_minimum"]):
        direction = "pathogenic_direction"
    elif total <= int(thresholds["benign_maximum"]):
        direction = "benign_direction"
    else:
        direction = "remain_uncertain"

    warnings: list[str] = []
    if consequence == "unrecognized":
        warnings.append(
            "Molecular consequence was not recognized from older HGVS text."
        )
    if consequence == "inframe_indel":
        warnings.append("In-frame indel was recognized but has zero Version 1 points.")
    if conflict:
        warnings.append("Older review status reported conflict.")
    if missing:
        warnings.append("Missing older fields: " + ", ".join(missing))
    if older.origin_simple_values not in {None, "germline"}:
        warnings.append("Older origin scope was not exclusively germline.")
    if direction == "no_prediction":
        confidence = "No prediction"
    elif expert or (abs(total) >= 4 and len(informative) >= 2 and not warnings):
        confidence = "High confidence"
    elif len(informative) >= 2 and not conflict:
        confidence = "Medium confidence"
    else:
        confidence = "Low confidence"
    terms = [f"{item.points:+d}" for item in clue_results if item.applied]
    arithmetic = " ".join(terms) + f" = {total:+d}" if terms else f"0 = {total:+d}"
    return Prediction(
        variation_id=older.variation_id,
        total_score=total,
        predicted_direction=direction,
        confidence=confidence,
        consequence=consequence,
        clues=tuple(clue_results),
        clues_used=tuple(item.clue for item in informative),
        clues_missing=missing,
        warnings=tuple(warnings),
        arithmetic=arithmetic,
        scoring_version=str(rules["scoring_version"]),
        config_sha256=frozen_config_sha256 or config_sha256(),
    )


def normalize_newer_outcome(classification: object) -> NormalizedOutcome:
    """Map exact newer aggregate text into one strict directional answer group."""
    if (
        classification is None
        or not str(classification).strip()
        or str(classification).strip() == "-"
    ):
        return NormalizedOutcome(
            None,
            "conflicting_or_unusable",
            "missing_classification",
            "Missing newer classification is not scorable.",
            False,
        )
    original = str(classification).strip()
    normalized = re.sub(r"\s+", " ", original).casefold()
    pathogenic = {
        "pathogenic",
        "likely pathogenic",
        "pathogenic/likely pathogenic",
        "likely pathogenic/pathogenic",
    }
    benign = {"benign", "likely benign", "benign/likely benign", "likely benign/benign"}
    if normalized in pathogenic:
        return NormalizedOutcome(
            original,
            "moved_toward_pathogenic",
            "compatible_pathogenic",
            "Exact compatible pathogenic category.",
            True,
        )
    if normalized in benign:
        return NormalizedOutcome(
            original,
            "moved_toward_benign",
            "compatible_benign",
            "Exact compatible benign category.",
            True,
        )
    if normalized == "uncertain significance":
        return NormalizedOutcome(
            original,
            "remained_uncertain",
            "exact_uncertain",
            "Exact uncertain-significance category.",
            True,
        )
    if "conflict" in normalized:
        reason = "conflicting_classification"
    elif any(
        term in normalized
        for term in ("protective", "risk factor", "drug response", "association")
    ):
        reason = "non_directional_germline_category"
    elif any(term in normalized for term in ("somatic", "oncogenic")):
        reason = "non_germline_scope"
    elif any(separator in normalized for separator in (";", ",", "|")):
        reason = "mixed_classification"
    else:
        reason = "unrecognized_classification"
    return NormalizedOutcome(
        original,
        "conflicting_or_unusable",
        reason,
        "Classification was preserved but not forced into a directional outcome.",
        False,
    )


def compare_prediction(
    prediction: Prediction, outcome: NormalizedOutcome, *, match_safe: bool = True
) -> Comparison:
    """Compare a precomputed prediction with a separately loaded answer key."""
    if not match_safe:
        return Comparison("Not Scorable", "unsafe_cross_snapshot_match", None)
    if not outcome.scorable:
        return Comparison("Not Scorable", outcome.reason_code, None)
    if prediction.predicted_direction == "no_prediction":
        return Comparison("No Prediction", "insufficient_directional_clues", None)
    expected = {
        "pathogenic_direction": "moved_toward_pathogenic",
        "benign_direction": "moved_toward_benign",
        "remain_uncertain": "remained_uncertain",
    }
    correct = expected[prediction.predicted_direction] == outcome.group
    return Comparison(
        "Correct" if correct else "Wrong",
        "direction_matched" if correct else "direction_mismatch",
        correct,
    )


def prediction_to_dict(prediction: Prediction) -> dict[str, Any]:
    """Serialize a prediction and every clue for storage and display."""
    value = asdict(prediction)
    value["clues"] = [asdict(clue) for clue in prediction.clues]
    return value
