#!/usr/bin/env python3
"""Train AI Holdout V5 without opening its fresh hidden test."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.ai_holdout_v5 import train_ai_holdout_v5  # noqa: E402
from variant_time_machine.config import (  # noqa: E402
    AI_HOLDOUT_V4_RESULTS_DIR,
    AI_HOLDOUT_V5_RESULTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)


def main() -> int:
    summary = train_ai_holdout_v5(
        RESOLVED_DIRECTION_RESULTS_DB_PATH,
        AI_HOLDOUT_V5_RESULTS_DIR,
        AI_HOLDOUT_V4_RESULTS_DIR / "partition_manifest.json",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
