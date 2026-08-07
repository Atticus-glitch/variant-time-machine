#!/usr/bin/env python3
"""Finalize fully nested V9.1 evidence from an authenticated trial."""

import argparse
from pathlib import Path

from variant_time_machine.v9_1_finalize import finalize_v9_1_trial

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = finalize_v9_1_trial(
        root,
        args.trial_dir,
        output_dir=args.output_dir,
        publish=args.publish,
    )
    print(f"Selected full-development family: {result['selected_family']}")
    print("Official V9.1 model: false. Final test evaluated: false.")
