#!/usr/bin/env python3
"""Generate conservative AI-assisted suggestions for all frozen V8 errors."""

from pathlib import Path

from variant_time_machine.v8_ai_review import write_ai_review_suggestions

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path, payload = write_ai_review_suggestions(root)
    print(f"Reviewed {payload['records_reviewed']} V8 errors into {path}.")
    print(payload["suggested_decisions"])
