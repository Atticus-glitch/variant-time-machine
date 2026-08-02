#!/usr/bin/env python3
"""Run separated V8 vault, development, sealing, and evaluation stages."""

import argparse
import json

from variant_time_machine.ai_temporal_v8 import (
    develop_and_seal_v8_predictions,
    evaluate_v8_once,
    seal_v8_label_vault,
)
from variant_time_machine.config import (
    AI_TEMPORAL_V8_CONFIG_PATH,
    AI_TEMPORAL_V8_RESULTS_DIR,
    HISTORICAL_RAW_DATA_DIR,
    HISTORICAL_VARIANT_DB_PATH,
    OUTPUTS_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("seal-vault", "develop", "evaluate"))
    args = parser.parse_args()
    if args.stage == "seal-vault":
        result = seal_v8_label_vault(
            RESOLVED_DIRECTION_RESULTS_DB_PATH,
            HISTORICAL_VARIANT_DB_PATH,
            OUTPUTS_DIR / "ai_temporal_v7/sealed_candidate_predictions.sqlite3",
            OUTPUTS_DIR / "ai_temporal_v7/temporal_test_predictions.csv",
            HISTORICAL_RAW_DATA_DIR / "variant_summary_2026-07.txt.gz",
            AI_TEMPORAL_V8_RESULTS_DIR / "label_vault.sqlite3",
            OUTPUTS_DIR / "evaluations/frozen/v8_vault_commitment.json",
            config_path=AI_TEMPORAL_V8_CONFIG_PATH,
        )
    elif args.stage == "develop":
        result = develop_and_seal_v8_predictions(
            RESOLVED_DIRECTION_RESULTS_DB_PATH,
            HISTORICAL_VARIANT_DB_PATH,
            OUTPUTS_DIR / "ai_temporal_v7/temporal_test_predictions.csv",
            OUTPUTS_DIR / "ai_temporal_v7/sealed_candidate_predictions.sqlite3",
            AI_TEMPORAL_V8_RESULTS_DIR,
            OUTPUTS_DIR / "evaluations/frozen/v8_model_commitment.json",
            config_path=AI_TEMPORAL_V8_CONFIG_PATH,
        )
    else:
        result = evaluate_v8_once(
            AI_TEMPORAL_V8_RESULTS_DIR,
            AI_TEMPORAL_V8_RESULTS_DIR / "label_vault.sqlite3",
            OUTPUTS_DIR / "evaluations/frozen/v8_vault_commitment.json",
            OUTPUTS_DIR / "evaluations/frozen/v8_model_commitment.json",
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
