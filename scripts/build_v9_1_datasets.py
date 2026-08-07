#!/usr/bin/env python3
"""Build lossless V9.1 dataset views."""

from pathlib import Path

from variant_time_machine.v9_1_dataset import build_v9_1_datasets

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = build_v9_1_datasets(root)
    print(result["counts"])
    print("Official model selection allowed: false. Final test allowed: false.")
