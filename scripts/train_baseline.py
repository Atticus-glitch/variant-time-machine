#!/usr/bin/env python3
"""Intentional placeholder for future explainable baseline training."""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.train import train_baseline_models  # noqa: E402
from variant_time_machine.utils import configure_logging  # noqa: E402


def main() -> int:
    """Report that verified timeline data must precede model training."""
    configure_logging()
    try:
        train_baseline_models()
    except NotImplementedError as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
