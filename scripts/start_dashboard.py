#!/usr/bin/env python3
"""Start the local Variant Time Machine research dashboard."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from website.dashboard.app import run_dashboard  # noqa: E402

if __name__ == "__main__":
    run_dashboard()
