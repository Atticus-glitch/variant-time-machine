# V5 Evaluation Log

> Reconstructed from existing artifacts; this is not the original runtime log.

- Model: AI Holdout V5
- Dataset: {"answer_snapshot": "2024-01-04", "dates_inherited_from": "Resolved Direction V2 source cohort", "prediction_snapshot": "2022-01-06", "source_database_sha256": "b923497cb638cb8252a41744009980eb7210e786e1de0f9a9bdb19d19a4524bd"}
- Test records: 100
- Accuracy: 0.82
- Balanced accuracy: 0.8219780219780219
- Leakage audit: pass
- Warnings: V5 was designed after V4 aggregate results were known. Its fresh holdout is unseen by V5 and disjoint from V4 test groups, but it is still internal to the already inspected V2 cohort.; Recorded configuration frozen_at_utc occurs after the recorded training timestamp; chronology is inconsistent and was not rewritten.; Training summary retains trained_hidden_test_unopened, but a saved test_metrics.json establishes that the effective state is tested.
