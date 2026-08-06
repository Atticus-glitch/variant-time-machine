"""AI-assisted V8 error review suggestions from frozen snapshot evidence."""

from __future__ import annotations

import csv
import gzip
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from variant_time_machine.v8_presentation import sha256_file

QUEUE_SHA256 = "f5c3f57c3ac39cd5b3bf5b4be8405b8c8130dd62dc04ed32c9ce1174135e5a42"
ANSWER_ARCHIVE_SHA256 = (
    "b3da921c707ff50cb4822f04d961834a9e89ef864b4c28bb5308245b93ac4077"
)
REVIEWER = "OpenCode GPT-5.6 AI-assisted evidence review"


class V8AIReviewError(ValueError):
    """Raised when AI-review evidence does not match frozen sources."""


def _values(value: object, pattern: str = r"[,;]") -> set[str]:
    return {
        item.strip()
        for item in re.split(pattern, str(value or ""))
        if item.strip() and item.strip() not in {"-", "not recorded"}
    }


def _condition_terms(value: object) -> set[str]:
    ignored = {"not specified", "not provided", "see cases"}
    return {
        re.sub(r"\s+", " ", item.casefold()).strip()
        for item in _values(value, r"[;|]")
        if item.casefold().strip() not in ignored
    }


def _read_queue(path: Path) -> list[dict[str, str]]:
    if sha256_file(path) != QUEUE_SHA256:
        raise V8AIReviewError("V8 review queue hash changed.")
    with path.open(encoding="utf-8", newline="") as input_file:
        rows = [row for row in csv.DictReader(input_file) if row["correct"] == "false"]
    if len(rows) != 105:
        raise V8AIReviewError("Expected exactly 105 frozen V8 errors.")
    return rows


def _answer_evidence(
    archive: Path, identifiers: set[str]
) -> dict[str, dict[str, set[str]]]:
    if sha256_file(archive) != ANSWER_ARCHIVE_SHA256:
        raise V8AIReviewError("July 2026 answer archive hash changed.")
    evidence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    fields = {
        "allele_ids": "#AlleleID",
        "classifications": "ClinicalSignificance",
        "origins": "OriginSimple",
        "rcv_accessions": "RCVaccession",
        "conditions": "PhenotypeList",
        "review_statuses": "ReviewStatus",
        "submitter_counts": "NumberSubmitters",
        "coordinates": "PositionVCF",
        "genes": "GeneSymbol",
    }
    with gzip.open(archive, "rt", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file, delimiter="\t")
        for row in reader:
            identifier = row.get("VariationID", "")
            if identifier not in identifiers:
                continue
            for target, source in fields.items():
                value = row.get(source, "").strip()
                if value and value != "-":
                    evidence[identifier][target].add(value)
    missing = identifiers - set(evidence)
    if missing:
        raise V8AIReviewError(
            "Answer archive is missing queued IDs: " + ", ".join(sorted(missing))
        )
    return evidence


def _recommendation(row: dict[str, str], answer: dict[str, set[str]]) -> dict[str, Any]:
    old_alleles = _values(row["allele_id"])
    new_alleles = set(answer["allele_ids"])
    old_rcvs = _values(row["rcv_accessions"])
    new_rcvs = {
        accession.split(".", maxsplit=1)[0]
        for value in answer["rcv_accessions"]
        for accession in _values(value, r"[|,;]")
    }
    old_conditions = _condition_terms(row["old_condition_text"])
    new_conditions = {
        term for value in answer["conditions"] for term in _condition_terms(value)
    }
    identity_matches = old_alleles == new_alleles and bool(old_alleles)
    germline_only = {value.casefold() for value in answer["origins"]} == {"germline"}
    classifications = {value.casefold() for value in answer["classifications"]}
    clear_label = len(classifications) == 1 and not any(
        token in next(iter(classifications), "")
        for token in ("conflict", "uncertain", "risk factor", "drug response")
    )
    shared_rcvs = old_rcvs & new_rcvs
    shared_conditions = old_conditions & new_conditions
    generic_rcv_with_added_scope = (
        bool(shared_rcvs)
        and not old_conditions
        and bool(new_conditions)
        and bool(new_rcvs - old_rcvs)
    )
    scope_supported = bool(
        shared_conditions or (shared_rcvs and not generic_rcv_with_added_scope)
    )

    if not identity_matches:
        decision = "bad_match"
        category = "poor_match"
        confidence = "high"
        note = "Old and later archived Allele-ID sets do not match exactly."
    elif not germline_only:
        decision = "exclude_non_germline_or_wrong_scope"
        category = "non_germline_scope"
        confidence = "high"
        note = "The later archived rows are not exclusively germline."
    elif not clear_label:
        decision = "possible_label_problem"
        category = "aggregate_label_ambiguous"
        confidence = "high"
        note = "The later archive does not contain one clearly usable classification."
    elif not scope_supported:
        no_assertion_criteria = any(
            "no assertion criteria" in value.casefold()
            for value in answer["review_statuses"]
        )
        decision = (
            "needs_expert_review"
            if no_assertion_criteria
            else "ambiguous_condition_scope"
        )
        category = (
            "aggregate_label_ambiguous"
            if no_assertion_criteria
            else "condition_scope_changed"
        )
        confidence = "low"
        note = (
            "Identity and later label checks pass, but comparable old/later condition "
            "scope is not established. Human expert review is required."
        )
    else:
        decision = "match_correct_model_wrong"
        category = (
            "false_negative_pathogenic_direction"
            if row["confusion_group"] == "FN"
            else "false_positive_pathogenic_direction"
        )
        confidence = "medium"
        note = (
            "Frozen identity, germline, and clear-label checks pass; archived RCV or "
            "condition scope overlaps. This is a likely genuine V8 model error, "
            "pending human confirmation."
        )

    return {
        "variation_id": row["variation_id"],
        "gene": row["gene"],
        "confusion_group": row["confusion_group"],
        "v8_prediction": row["predicted_class"],
        "automatic_outcome": row["normalized_new_outcome"],
        "v8_confidence": float(row["confidence"]),
        "old_allele_ids": sorted(old_alleles),
        "new_allele_ids": sorted(new_alleles),
        "old_rcv_accessions": sorted(old_rcvs),
        "new_rcv_accessions": sorted(new_rcvs),
        "shared_rcv_accessions": sorted(shared_rcvs),
        "old_conditions": sorted(old_conditions),
        "new_conditions": sorted(new_conditions),
        "shared_conditions": sorted(shared_conditions),
        "old_review_status": row["old_review_status"],
        "new_review_statuses": sorted(answer["review_statuses"]),
        "new_classifications": sorted(answer["classifications"]),
        "new_origins": sorted(answer["origins"]),
        "new_submitter_counts": sorted(answer["submitter_counts"]),
        "identity_check": identity_matches,
        "germline_scope_check": germline_only,
        "clear_label_check": clear_label,
        "condition_scope_support": scope_supported,
        "generic_rcv_with_added_scope": generic_rcv_with_added_scope,
        "suggested_manual_decision": decision,
        "suggested_error_category": category,
        "suggested_include_in_v9_clean_dataset": decision
        == "match_correct_model_wrong",
        "suggested_exclude_from_v9_clean_dataset": decision
        != "match_correct_model_wrong",
        "suggested_reviewer_confidence": confidence,
        "note": note,
        "requires_human_confirmation": True,
        "official_source": (
            f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{row['variation_id']}/"
        ),
    }


def build_ai_review_suggestions(project_root: Path) -> dict[str, Any]:
    """Review all frozen V8 errors without writing the human-review ledger."""
    root = project_root.resolve()
    queue_path = root / "outputs/manual_review/v8_review_queue.csv"
    answer_path = root / "data/raw/clinvar/variant_summary_2026-07.txt.gz"
    rows = _read_queue(queue_path)
    answers = _answer_evidence(answer_path, {row["variation_id"] for row in rows})
    reviews = [_recommendation(row, answers[row["variation_id"]]) for row in rows]
    decision_counts: dict[str, int] = defaultdict(int)
    group_counts: dict[str, int] = defaultdict(int)
    for review in reviews:
        decision_counts[review["suggested_manual_decision"]] += 1
        group_counts[review["confusion_group"]] += 1
    return {
        "schema_version": 1,
        "review_type": "ai_assisted_suggestion_not_human_manual_review",
        "reviewer": REVIEWER,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "records_reviewed": len(reviews),
        "confusion_groups": dict(sorted(group_counts.items())),
        "suggested_decisions": dict(sorted(decision_counts.items())),
        "source_hashes": {
            "review_queue": sha256_file(queue_path),
            "answer_archive": sha256_file(answer_path),
        },
        "method": (
            "Compare frozen predictor-time identity, RCV, and condition evidence with "
            "the exact archived July 2026 rows. Require unchanged Allele IDs, germline "
            "scope, one clear later label, and RCV or condition overlap before "
            "suggesting a genuine model error."
        ),
        "warning": (
            "These are AI-assisted triage suggestions, not human genetics review, not "
            "medical advice, and not sufficient to unlock final V9 training."
        ),
        "reviews": reviews,
    }


def write_ai_review_suggestions(project_root: Path) -> tuple[Path, dict[str, Any]]:
    """Write the separate AI suggestion artifact and return its payload."""
    root = project_root.resolve()
    payload = build_ai_review_suggestions(root)
    path = root / "outputs/manual_review/v8_ai_review_suggestions.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path, payload
