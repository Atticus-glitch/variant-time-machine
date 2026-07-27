#!/usr/bin/env python3
"""Inspect paused ClinVar XML sources without downloading archive bodies."""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import PILOT_XML_RELEASES  # noqa: E402
from variant_time_machine.remote_archive import (  # noqa: E402
    RemoteArchiveError,
    inspect_remote_release,
)
from variant_time_machine.utils import configure_logging  # noqa: E402

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Allow metadata inspection only while full archive scanning is paused."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="Read only response headers and tiny official MD5 text files",
    )
    parser.parse_args(argv)

    try:
        metadata = [
            inspect_remote_release(PILOT_XML_RELEASES[label])
            for label in ("older", "newer")
        ]
    except RemoteArchiveError as exc:
        LOGGER.error("%s", exc)
        return 1

    print(json.dumps([item.__dict__ for item in metadata], indent=2))
    print(
        "Metadata check complete. Archive body scanning is paused by project policy. "
        "No archive body was requested or saved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
