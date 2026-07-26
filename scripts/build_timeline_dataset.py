#!/usr/bin/env python3
"""Build an auditable historical VUS timeline from two input files."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.match import match_variants_across_releases  # noqa: E402
from variant_time_machine.parse import parse_clinvar_release  # noqa: E402
from variant_time_machine.utils import configure_logging  # noqa: E402

LOGGER = logging.getLogger(__name__)


def _release_date(value: str) -> date:
    """Parse an ISO release date for argparse."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Release date must use YYYY-MM-DD format: {value}"
        ) from exc


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Match variants that were VUS in an older ClinVar file to a newer file."
        )
    )
    parser.add_argument("older_file", type=Path, help="Older TSV, TSV.GZ, or CSV file")
    parser.add_argument("newer_file", type=Path, help="Newer TSV, TSV.GZ, or CSV file")
    parser.add_argument("--output", required=True, type=Path, help="Output CSV path")
    parser.add_argument(
        "--older-release-date",
        type=_release_date,
        help="Required for a raw older ClinVar file: YYYY-MM-DD",
    )
    parser.add_argument(
        "--newer-release-date",
        type=_release_date,
        help="Required for a raw newer ClinVar file: YYYY-MM-DD",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file",
    )
    return parser


def _print_summary(timeline: object) -> None:
    """Print counts calculated from the generated timeline."""
    import pandas as pd

    if not isinstance(timeline, pd.DataFrame):
        raise TypeError("Timeline summary requires a pandas DataFrame.")

    matched_statuses = {
        "exact_identifier_match",
        "exact_variation_id_match",
        "allele_id_match_variation_changed",
    }
    changed_outcomes = {
        "VUS_to_Pathogenic",
        "VUS_to_Likely_Pathogenic",
        "VUS_to_Benign",
        "VUS_to_Likely_Benign",
    }
    ambiguous_statuses = {
        "ambiguous_multiple_candidates",
        "conflicting_identifiers",
        "unsupported_complex_identifier",
    }

    print(f"Variants processed: {len(timeline)}")
    print(f"Variants matched: {timeline['match_status'].isin(matched_statuses).sum()}")
    print(
        "Variants changed: "
        f"{timeline['classification_change'].isin(changed_outcomes).sum()}"
    )
    ambiguous = (
        timeline["match_status"].isin(ambiguous_statuses)
        | timeline["classification_change"].eq("VUS_to_Conflicting")
    ).sum()
    print(f"Variants ambiguous: {ambiguous}")


def main(argv: list[str] | None = None) -> int:
    """Parse two snapshots, match historical VUS records, and save a CSV."""
    configure_logging()
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    output_path = args.output.resolve()
    input_paths = {args.older_file.resolve(), args.newer_file.resolve()}

    if output_path.exists() and not args.overwrite:
        LOGGER.error(
            "Output already exists: %s. Use --overwrite only after checking it.",
            output_path,
        )
        return 1
    if output_path in input_paths:
        LOGGER.error("Output path must not replace either input file: %s", output_path)
        return 1

    partial_output = output_path.with_suffix(f"{output_path.suffix}.part")
    try:
        older = parse_clinvar_release(args.older_file, args.older_release_date)
        newer = parse_clinvar_release(args.newer_file, args.newer_release_date)
        timeline = match_variants_across_releases(older, newer)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timeline.to_csv(partial_output, index=False)
        partial_output.replace(output_path)
    except (FileNotFoundError, OSError, ValueError) as exc:
        partial_output.unlink(missing_ok=True)
        LOGGER.error("Timeline build failed: %s", exc)
        return 1

    LOGGER.info("Saved timeline to %s", output_path)
    _print_summary(timeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
