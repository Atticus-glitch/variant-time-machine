#!/usr/bin/env python3
"""Train V6 around its frozen 1,000-record holdout, then evaluate once."""

import json

from variant_time_machine.ai_holdout_v6 import (
    test_ai_holdout_v6_once,
    train_ai_holdout_v6,
)
from variant_time_machine.config import (
    AI_HOLDOUT_V4_RESULTS_DIR,
    AI_HOLDOUT_V5_RESULTS_DIR,
    AI_HOLDOUT_V6_RESULTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)


def main() -> int:
    training = train_ai_holdout_v6(
        RESOLVED_DIRECTION_RESULTS_DB_PATH,
        AI_HOLDOUT_V6_RESULTS_DIR,
        {
            "V4": AI_HOLDOUT_V4_RESULTS_DIR / "partition_manifest.json",
            "V5": AI_HOLDOUT_V5_RESULTS_DIR / "partition_manifest.json",
        },
    )
    metrics = test_ai_holdout_v6_once(
        RESOLVED_DIRECTION_RESULTS_DB_PATH, AI_HOLDOUT_V6_RESULTS_DIR
    )
    print(json.dumps({"training": training, "test": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
