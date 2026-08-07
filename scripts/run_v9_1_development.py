#!/usr/bin/env python3
"""Run preregistered V9.1 internal development without a final test."""

import argparse
from pathlib import Path

from variant_time_machine.v9_1 import run_v9_1_development

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = run_v9_1_development(
        root,
        output_dir=args.output_dir,
        publish=args.publish,
    )
    print(f"Selected internal candidate: {result['selected_family']}")
    print("Official V9.1 model: false. Final test evaluated: false.")
