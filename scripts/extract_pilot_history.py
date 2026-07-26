#!/usr/bin/env python3
"""Inspect or stream the two official ClinVar XML archives for the small pilot."""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import (  # noqa: E402
    PILOT_EXTRACTED_DIR,
    PILOT_MAX_TEMP_BYTES,
    PILOT_VARIANTS_PATH,
    PILOT_XML_RELEASES,
)
from variant_time_machine.pilot import (  # noqa: E402
    compare_pilot_records,
    read_pilot_rows,
    write_extraction_outputs,
    write_json_atomic,
)
from variant_time_machine.remote_archive import (  # noqa: E402
    RemoteArchiveError,
    extract_remote_records,
    inspect_remote_release,
)
from variant_time_machine.utils import configure_logging  # noqa: E402

LOGGER = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--dry-run",
        action="store_true",
        help="Check headers and official MD5 metadata without streaming an archive",
    )
    action.add_argument(
        "--confirm-large-transfer",
        action="store_true",
        help="Confirm that up to about 7.9 GB may be transferred",
    )
    parser.add_argument("--pilot-csv", type=Path, default=PILOT_VARIANTS_PATH)
    parser.add_argument("--output-dir", type=Path, default=PILOT_EXTRACTED_DIR)
    parser.add_argument(
        "--max-output-mb",
        type=float,
        default=PILOT_MAX_TEMP_BYTES / (1024 * 1024),
        help="Hard limit for each retained output file",
    )
    parser.add_argument(
        "--max-transfer-gb",
        type=float,
        default=None,
        help="Optional hard compressed-byte limit for each release scan",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run metadata inspection or confirmed bounded streaming extraction."""
    configure_logging()
    args = _parser().parse_args(argv)
    try:
        pilot_rows = read_pilot_rows(args.pilot_csv)
        identifiers = [row["variation_id"] for row in pilot_rows]
        if args.max_output_mb <= 0:
            raise ValueError("--max-output-mb must be greater than zero.")
        if args.max_transfer_gb is not None and args.max_transfer_gb <= 0:
            raise ValueError("--max-transfer-gb must be greater than zero.")
        max_output_bytes = int(args.max_output_mb * 1024 * 1024)
        max_transfer_bytes = (
            int(args.max_transfer_gb * 1_000_000_000)
            if args.max_transfer_gb is not None
            else None
        )

        if args.dry_run:
            metadata = [
                inspect_remote_release(PILOT_XML_RELEASES[label])
                for label in ("older", "newer")
            ]
            print(json.dumps([item.__dict__ for item in metadata], indent=2))
            print(
                "Dry run complete. No archive body was requested and no archive "
                "was saved."
            )
            return 0

        total_gb = (
            sum(
                release.compressed_size_bytes for release in PILOT_XML_RELEASES.values()
            )
            / 1_000_000_000
        )
        LOGGER.warning(
            "Confirmed scan may transfer up to %.2f GB if requested records are not "
            "found early. Full archives will not be retained.",
            total_gb,
        )
        results = {
            label: extract_remote_records(
                PILOT_XML_RELEASES[label],
                identifiers,
                confirmed=True,
                max_output_bytes=max_output_bytes,
                max_transfer_bytes=max_transfer_bytes,
            )
            for label in ("older", "newer")
        }

        created: list[Path] = []
        try:
            for label in ("older", "newer"):
                paths = write_extraction_outputs(
                    args.output_dir,
                    PILOT_XML_RELEASES[label],
                    results[label],
                    max_bytes=max_output_bytes,
                )
                created.extend(paths)
            comparisons = compare_pilot_records(
                identifiers,
                results["older"].records,
                results["newer"].records,
                older_release_date=PILOT_XML_RELEASES["older"].release_date.isoformat(),
                newer_release_date=PILOT_XML_RELEASES["newer"].release_date.isoformat(),
            )
            comparison_path = args.output_dir / "pilot_comparisons.json"
            write_json_atomic(
                comparison_path,
                {
                    "scientific_verification": "Requires manual review",
                    "comparisons": comparisons,
                },
                max_bytes=max_output_bytes,
            )
            created.append(comparison_path)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

        LOGGER.info("Saved %d small output files in %s", len(created), args.output_dir)
        return 0
    except (OSError, ValueError, RemoteArchiveError, json.JSONDecodeError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
