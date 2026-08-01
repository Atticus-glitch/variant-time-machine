# V4 Evaluation Log

> Reconstructed from existing artifacts; this is not the original runtime log.

- Model: AI Holdout V4
- Dataset: {"answer_snapshot": "2024-01-04", "dates_inherited_from": "Resolved Direction V2 source cohort", "prediction_snapshot": "2022-01-06", "source_database_sha256": "b923497cb638cb8252a41744009980eb7210e786e1de0f9a9bdb19d19a4524bd"}
- Test records: 100
- Accuracy: 0.76
- Balanced accuracy: 0.625
- Leakage audit: pass
- Warnings: This is an internal holdout from the already inspected Resolved Direction V2 cohort, not independent temporal or clinical validation.; Recorded configuration frozen_at_utc occurs after the recorded training timestamp; chronology is inconsistent and was not rewritten.; Training summary retains trained_hidden_test_unopened, but a saved test_metrics.json establishes that the effective state is tested.
