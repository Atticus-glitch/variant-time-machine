#!/usr/bin/env python3
"""Preview current ClinVar candidates without selecting or saving one."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.clinvar_api import (  # noqa: E402
    CLINVAR_ESEARCH_URL,
    CLINVAR_ESUMMARY_URL,
    ClinVarAPIError,
    ClinVarVariant,
    lookup_clinvar_variant,
    normalize_variant_identifier,
    search_clinvar_gene,
)
from variant_time_machine.config import PILOT_CURRENT_API_ESTIMATE_BYTES  # noqa: E402
from variant_time_machine.download import transfer_plan_message  # noqa: E402


def display_variant(variant: ClinVarVariant, number: int | None = None) -> None:
    """Print only current fields returned by the official API."""
    if number is not None:
        print(f"\nCandidate {number}")
    print(f"Variant ID: {variant.variation_id}")
    print(f"VCV accession: {variant.variant_identifier}")
    print(f"Gene: {variant.gene_name or 'Not listed'}")
    print(f"Classification: {variant.classification or 'Not listed'}")
    print(f"Review status: {variant.review_status or 'Not listed'}")
    print(
        "Conditions: "
        + (
            "; ".join(variant.associated_conditions)
            if variant.associated_conditions
            else "Not listed"
        )
    )
    print(f"Source URL: {variant.source_url}")


def main(argv: list[str] | None = None) -> int:
    """Plan and optionally perform a small candidate preview."""
    parser = argparse.ArgumentParser(description=__doc__)
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--variation-id")
    query.add_argument("--vcv")
    query.add_argument("--gene")
    parser.add_argument(
        "--confirm-api-requests",
        action="store_true",
        help="Confirm the displayed current-record API requests",
    )
    args = parser.parse_args(argv)

    try:
        if args.gene:
            source = (
                f"{CLINVAR_ESEARCH_URL} plus at most five "
                f"{CLINVAR_ESUMMARY_URL} requests"
            )
            estimated_size = PILOT_CURRENT_API_ESTIMATE_BYTES * 6
            reason = f"Preview up to five current ClinVar candidates for {args.gene}"
            identifiers: tuple[str, ...] | None = None
        else:
            identifier = args.variation_id or args.vcv
            normalized = normalize_variant_identifier(identifier)
            source = f"{CLINVAR_ESUMMARY_URL}?db=clinvar&id={normalized}&retmode=json"
            estimated_size = PILOT_CURRENT_API_ESTIMATE_BYTES
            reason = "Preview one current ClinVar candidate"
            identifiers = (normalized,)
    except ClinVarAPIError as exc:
        print(f"Selection input error: {exc}", file=sys.stderr)
        return 1

    print(transfer_plan_message(source, estimated_size, reason))
    if not args.confirm_api_requests:
        print(
            "No request started. Add --confirm-api-requests after reviewing the plan."
        )
        return 0

    try:
        if identifiers is None:
            identifiers = search_clinvar_gene(args.gene)
        if not identifiers:
            print("No current ClinVar candidates were found for that gene.")
            return 0
        for number, identifier in enumerate(identifiers, start=1):
            display_variant(
                lookup_clinvar_variant(identifier),
                number if args.gene else None,
            )
    except (ClinVarAPIError, ValueError) as exc:
        print(f"Candidate lookup failed: {exc}", file=sys.stderr)
        return 1

    print("\nPreview only. No variant was accepted or saved as a research example.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
