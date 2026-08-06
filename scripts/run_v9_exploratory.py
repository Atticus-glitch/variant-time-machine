#!/usr/bin/env python3
"""Run exploratory V9 candidates on previously opened V8 records."""

from pathlib import Path

from variant_time_machine.v9_exploratory import run_v9_exploratory

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_v9_exploratory(root)
    leader = result["manifest"]["exploratory_leader_among_new_candidate_families"]
    print(f"Exploratory leader among new candidate families: {leader}")
    print("Strongest same-record reference: frozen V8.")
    print("Official V9 winner: none. Final test evaluated: false.")
