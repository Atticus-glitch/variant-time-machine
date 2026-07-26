#!/usr/bin/env python3
"""Test one live connection to the official NCBI ClinVar ESummary API."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.clinvar_api import (  # noqa: E402
    ClinVarAPIError,
    lookup_clinvar_variant,
)

DOCUMENTED_EXAMPLE_VARIATION_ID = "14206"


def _display(value: object) -> str:
    """Return readable text for a possibly unavailable API value."""
    if value is None or value == () or value == []:
        return "Not available"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    """Run one live lookup and report success or an honest failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variant",
        nargs="?",
        default=DOCUMENTED_EXAMPLE_VARIATION_ID,
        help="Numeric Variation ID or VCV accession",
    )
    args = parser.parse_args(argv)

    print("Variant Time Machine ClinVar connection test")
    print(f"Query: {args.variant}")
    try:
        result = lookup_clinvar_variant(args.variant)
    except ClinVarAPIError as exc:
        print("Connection status: Not connected")
        print(f"Reason: {exc}")
        return 1

    print("Connection status: Connected")
    print(f"Variant: {_display(result.variant_identifier)}")
    print(f"Variation ID: {_display(result.variation_id)}")
    print(f"Gene: {_display(result.gene_name)}")
    print(f"Classification: {_display(result.classification)}")
    print(f"Associated conditions: {_display(result.associated_conditions)}")
    print(f"Review status: {_display(result.review_status)}")
    print(f"Evidence summary: {_display(result.evidence_summary)}")
    print(f"Source: {result.source_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
