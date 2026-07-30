#!/usr/bin/env python3
"""Run the frozen learned-weight Version 3 experiment."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import (  # noqa: E402
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
    STATISTICAL_MODEL_V3_RESULTS_DIR,
)
from variant_time_machine.statistical_model_v3 import (  # noqa: E402
    run_statistical_model_v3,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=RESOLVED_DIRECTION_RESULTS_DB_PATH
    )
    parser.add_argument("--output", type=Path, default=STATISTICAL_MODEL_V3_RESULTS_DIR)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Reproduce an existing frozen run; never use this to tune from test "
            "results."
        ),
    )
    arguments = parser.parse_args()
    summary = run_statistical_model_v3(
        arguments.source, arguments.output, overwrite=arguments.overwrite
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
