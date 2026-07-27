#!/usr/bin/env python3
"""Retrieve and save one explicitly selected current ClinVar pilot record."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts.select_pilot_variant import display_variant  # noqa: E402
from variant_time_machine.clinvar_api import (  # noqa: E402
    CLINVAR_ESUMMARY_URL,
    ClinVarAPIError,
    lookup_clinvar_variant,
    normalize_variant_identifier,
)
from variant_time_machine.config import (  # noqa: E402
    PILOT_CURRENT_API_ESTIMATE_BYTES,
    PILOT_RECORD_PATH,
)
from variant_time_machine.download import transfer_plan_message  # noqa: E402
from variant_time_machine.pilot_record import (  # noqa: E402
    build_pilot_record,
    load_pilot_record,
    save_pilot_record,
)


def _yes(answer: str) -> bool:
    return answer.strip().casefold() in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    """Run an interactive or explicitly confirmed one-variant workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier", nargs="?")
    parser.add_argument("--reason")
    parser.add_argument("--output", type=Path, default=PILOT_RECORD_PATH)
    parser.add_argument("--confirm-api-request", action="store_true")
    parser.add_argument("--confirm-selection", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    interactive = args.identifier is None
    identifier = args.identifier or input("ClinVar Variation ID or VCV accession: ")
    reason = args.reason or (
        input("Why is this a useful first pilot variant? ") if interactive else ""
    )
    if not reason.strip():
        print("A selection reason is required.", file=sys.stderr)
        return 1

    try:
        variation_id = normalize_variant_identifier(identifier)
        existing = load_pilot_record(args.output)
    except (OSError, ValueError, ClinVarAPIError) as exc:
        print(f"Pilot input error: {exc}", file=sys.stderr)
        return 1
    if existing["variant_id"] and not args.overwrite:
        print(
            f"A pilot variant is already saved at {args.output}. "
            "Use --overwrite only after reviewing it.",
            file=sys.stderr,
        )
        return 1

    source = f"{CLINVAR_ESUMMARY_URL}?db=clinvar&id={variation_id}&retmode=json"
    print(
        transfer_plan_message(
            source,
            PILOT_CURRENT_API_ESTIMATE_BYTES,
            "Retrieve current metadata for the explicitly chosen first pilot variant",
        )
    )
    request_confirmed = args.confirm_api_request
    if interactive and not request_confirmed:
        request_confirmed = _yes(input("Start this small API request? [y/N]: "))
    if not request_confirmed:
        print("No request started and no pilot record changed.")
        return 0

    try:
        variant = lookup_clinvar_variant(variation_id)
    except ClinVarAPIError as exc:
        print(f"Current ClinVar lookup failed: {exc}", file=sys.stderr)
        return 1
    print("\nCurrent ClinVar preview")
    display_variant(variant)

    selection_confirmed = args.confirm_selection
    if interactive and not selection_confirmed:
        selection_confirmed = _yes(
            input("Save this as pilot_variant_001 for manual research? [y/N]: ")
        )
    if not selection_confirmed:
        print("Variant was previewed but not selected or saved.")
        return 0

    try:
        record = build_pilot_record(variant, reason)
        save_pilot_record(args.output, record)
    except (OSError, ValueError) as exc:
        print(f"Could not save pilot record: {exc}", file=sys.stderr)
        return 1

    print("\nPilot variant created:")
    print(f"Gene: {record['gene'] or 'Not listed'}")
    print(f"Classification: {record['current_classification'] or 'Not listed'}")
    print(f"Source: {record['sources'][0]}")
    print(f"Verification status: {record['verification_status']}")
    print("Historical records found: 0; manual investigation is still pending.")
    print(f"Saved: {args.output}")
    print("The dashboard reads this file automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
