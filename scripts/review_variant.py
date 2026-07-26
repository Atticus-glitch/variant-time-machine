#!/usr/bin/env python3
"""Display current ClinVar data and a historical manual-review checklist."""

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
from variant_time_machine.config import (  # noqa: E402
    NEWER_CLINVAR_RELEASE,
    OLDER_CLINVAR_RELEASE,
)

CHECKLIST: tuple[str, ...] = (
    "Correct variant identifier",
    "Correct gene",
    "Correct old classification",
    "Correct new classification",
    "Sources recorded",
    "Ambiguities documented",
)


def _display(value: object) -> str:
    """Return readable text for a missing or repeated value."""
    if value is None or value == () or value == []:
        return "Not available"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    """Look up one current record and print fields that still need verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variant",
        nargs="?",
        help="Numeric Variation ID or VCV accession; prompts when omitted",
    )
    args = parser.parse_args(argv)
    identifier = args.variant or input(
        "Enter a ClinVar Variation ID or VCV accession: "
    )

    print("\nCurrent ClinVar information")
    print("This is a live current record, not proof of historical classification.")
    try:
        variant = lookup_clinvar_variant(identifier)
    except ClinVarAPIError as exc:
        print("Connection status: Not connected")
        print(f"Reason: {exc}")
        return 1

    print("Connection status: Connected")
    print(f"Variant: {_display(variant.variant_identifier)}")
    print(f"Variation ID: {_display(variant.variation_id)}")
    print(f"Gene: {_display(variant.gene_name)}")
    print(f"Current classification: {_display(variant.classification)}")
    print(f"Associated conditions: {_display(variant.associated_conditions)}")
    print(f"Review status: {_display(variant.review_status)}")
    print(f"Evidence summary: {_display(variant.evidence_summary)}")
    print(f"Current source: {variant.source_url}")
    print(f"Retrieved at: {variant.retrieved_at_utc}")

    print("\nFields needed for the fixed historical comparison")
    print(f"variant_id: {variant.variation_id}")
    print(f"gene: {_display(variant.gene_name)}")
    print(f"old_release_date: {OLDER_CLINVAR_RELEASE.isoformat()} (verify in archive)")
    print(f"new_release_date: {NEWER_CLINVAR_RELEASE.isoformat()} (verify in archive)")
    print("old_classification: [verify from older archived release]")
    print("new_classification: [verify from newer archived release]")
    print("verification_source: [record both official archive references]")
    print("notes: [record identifier changes, conflicts, conditions, and uncertainty]")

    print("\nManual verification checklist")
    for item in CHECKLIST:
        print(f"[ ] {item}")

    print("\nDo not add a CSV row until every checklist item is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
