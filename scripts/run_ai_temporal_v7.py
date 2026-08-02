#!/usr/bin/env python3
"""Run separated V7 training/sealing, download, and evaluation stages."""

import argparse
import json
from datetime import date

from variant_time_machine.ai_temporal_v7 import (
    evaluate_v7_once,
    load_ai_temporal_v7_config,
    train_and_seal_v7_predictions,
)
from variant_time_machine.config import (
    AI_TEMPORAL_V7_RESULTS_DIR,
    HISTORICAL_RAW_DATA_DIR,
    HISTORICAL_VARIANT_DB_PATH,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
    ClinVarRelease,
)
from variant_time_machine.download import download_clinvar_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("seal", "download-answer", "evaluate"))
    parser.add_argument("--confirm-large-download", action="store_true")
    args = parser.parse_args()
    config = load_ai_temporal_v7_config()
    if args.stage == "seal":
        result = train_and_seal_v7_predictions(
            RESOLVED_DIRECTION_RESULTS_DB_PATH,
            HISTORICAL_VARIANT_DB_PATH,
            AI_TEMPORAL_V7_RESULTS_DIR,
        )
    elif args.stage == "download-answer":
        answer = config["answer_archive"]
        release = ClinVarRelease(
            label="v7_answer",
            release_date=date.fromisoformat(config["answer_snapshot_date"]),
            source_url=answer["source_url"],
            expected_size_bytes=int(answer["expected_size_bytes"]),
        )
        paths = download_clinvar_release(
            release,
            HISTORICAL_RAW_DATA_DIR,
            confirm=args.confirm_large_download,
            reason="Frozen July 2026 answer snapshot for V7 temporal evaluation",
        )
        result = {"archive": str(paths[0]), "metadata": str(paths[1])}
    else:
        result = evaluate_v7_once(
            HISTORICAL_RAW_DATA_DIR / "variant_summary_2026-07.txt.gz"
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
