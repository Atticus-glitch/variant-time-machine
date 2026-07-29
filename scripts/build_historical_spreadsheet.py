#!/usr/bin/env python3
"""Build the searchable historical ClinVar spreadsheet database."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import (  # noqa: E402
    CLINVAR_RELEASES,
    HISTORICAL_RAW_DATA_DIR,
    HISTORICAL_VARIANT_DB_PATH,
)
from variant_time_machine.historical_variants import (  # noqa: E402
    build_historical_variant_database,
)


def main(argv: list[str] | None = None) -> int:
    """Build the fixed two-release index and print measured progress."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HISTORICAL_VARIANT_DB_PATH)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    archives = {
        role: HISTORICAL_RAW_DATA_DIR / release.filename
        for role, release in CLINVAR_RELEASES.items()
    }

    def progress(event: dict[str, object]) -> None:
        stage = event["stage"]
        if stage == "ingest":
            print(f"{event['role']}: {int(event['rows']):,} source rows")
        elif stage == "ingest_complete":
            print(f"{event['role']} complete: {int(event['rows']):,} source rows")
        else:
            print("Building searchable variant summaries and indexes...")

    try:
        metadata = build_historical_variant_database(
            archives,
            args.output,
            overwrite=args.overwrite,
            progress=progress,
        )
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Variants indexed: {int(metadata['variant_count']):,}")
    print(f"Saved: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
