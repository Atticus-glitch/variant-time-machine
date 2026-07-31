# AI Holdout V4 Training

Trained: 2026-07-31T16:53:50.078507+00:00

## State

The neural-network model is trained, but the hidden test remains unopened. No test
accuracy or per-record hidden prediction has been calculated.

- Training records: 8,325
- Hidden test records: exactly 100
- Quarantined related-gene records: 393
- Older-only hint inputs: 11
- Training iterations: 23
- Final training loss: 0.4197
- Shared connected gene groups between train and test: 0

The model and partition manifest are stored under the Git-ignored
`outputs/ai_holdout_v4/` directory. The manifest SHA-256 is
`bd4401dcec03202832bef7e524db9a449786bcdefd485bab2e6f5585ac357322`.

## Next Action

Open Prediction Results in the local dashboard, read the limitation, approve the
one-time action, and select **Test AI On 100 Unseen Records**. That action will reveal
and save accuracy for the frozen model without retraining it.

The hidden records are unseen by the fitted model, but they still belong to the
already inspected conditional 2022-to-2024 cohort and are not independent temporal or
clinical validation.
