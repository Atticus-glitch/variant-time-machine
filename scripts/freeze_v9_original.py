#!/usr/bin/env python3
"""Freeze the original opened-data V9 exploration in the model registry."""

from pathlib import Path

from variant_time_machine.v9_original import freeze_original_v9

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(freeze_original_v9(root).relative_to(root))
