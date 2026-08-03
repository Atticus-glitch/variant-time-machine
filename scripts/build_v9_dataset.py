#!/usr/bin/env python3
"""Build current V9 preparation datasets from frozen V8 evidence and reviews."""

from pathlib import Path

from variant_time_machine.v9_dataset import build_v9_datasets

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    manifest = build_v9_datasets(root)
    print(manifest["headline"])
    print(
        f"Messy: {manifest['number_included_messy']}; "
        f"clean: {manifest['number_included_clean']}; "
        f"excluded/pending: {manifest['number_excluded']}."
    )
