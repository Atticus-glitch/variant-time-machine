# V7 Evaluation Log

> Reconstructed from existing artifacts; this is not the original runtime log.

- Model: AI Temporal V7
- Dataset: {"answer_snapshot": "2026-07-02", "prediction_snapshot": "2024-01-04", "source_database_sha256": "d9d66ba2384f2d9e0b8cb55be43432f8e02fdd8fcd70ecd2266d65e52af73a04"}
- Test records: 1000
- Accuracy: 0.785
- Balanced accuracy: 0.7906832298136646
- Leakage audit: pass
- Warnings: V7 is an external temporal test at the record level, but still uses aggregate ClinVar classifications and an outcome-selected resolved subset. Same-gene overlap with development is allowed and will be reported. It is not clinical validation.; All test Variation IDs were absent from development, but 69.9% of test records shared at least one gene with development.; The primary test is conditional on safe clear resolution by July 2026 and does not estimate whether a VUS will resolve.
