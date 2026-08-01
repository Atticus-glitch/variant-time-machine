# V6 Evaluation Log

> Reconstructed from existing artifacts; this is not the original runtime log.

- Model: AI Holdout V6
- Dataset: {"answer_snapshot": "2024-01-04", "dates_inherited_from": "Resolved Direction V2 source cohort", "prediction_snapshot": "2022-01-06", "source_database_sha256": "d9d66ba2384f2d9e0b8cb55be43432f8e02fdd8fcd70ecd2266d65e52af73a04"}
- Test records: 1000
- Accuracy: 0.756
- Balanced accuracy: 0.7435492978780002
- Leakage audit: pass
- Warnings: V6 is an internal conditional test from the previously inspected V2 cohort, not independent temporal or clinical validation. Its 1,000 records and their connected groups are excluded from V6 training, and all prior V4/V5 test groups are excluded from both V6 training and V6 testing.; This rebuilt local V2 database has the same 8,818-record cohort and IDs used by the manifests, but its byte hash differs from the source hash recorded by V4/V5. V6 freezes and reports the current hash rather than rewriting prior provenance.
