#!/usr/bin/env python3
"""Explicit command-line downloader for configured ClinVar releases."""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import CLINVAR_RELEASES, RAW_DATA_DIR  # noqa: E402
from variant_time_machine.download import download_clinvar_release  # noqa: E402
from variant_time_machine.utils import configure_logging  # noqa: E402

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Download one named release only after an explicit confirmation flag."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", choices=sorted(CLINVAR_RELEASES))
    parser.add_argument("--destination", type=Path, default=RAW_DATA_DIR)
    parser.add_argument(
        "--confirm-large-download",
        action="store_true",
        help="Confirm that the URL, size, disk space, and download were reviewed",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--reason",
        default="Create a fixed historical ClinVar summary snapshot",
        help="Explain why this transfer is needed",
    )
    args = parser.parse_args(argv)

    try:
        download_clinvar_release(
            CLINVAR_RELEASES[args.release],
            args.destination,
            confirm=args.confirm_large_download,
            overwrite=args.overwrite,
            reason=args.reason,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
