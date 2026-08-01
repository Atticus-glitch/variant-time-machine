# Test-Set Expansion Plan

## Purpose

The 100-record V4 and V5 tests were useful internal checks, but they were too small and
used distinct test groups. The implemented next step was V6: a separately frozen model
trained around a precommitted 1,000-record holdout. The earlier proposed 500-record
stage was not run and no 500-record result should be implied.

## Frozen Rules

- Use only fields available in the January 6, 2022 predictor snapshot.
- Keep the outcome definition tied to the January 4, 2024 snapshot.
- Keep complete connected older-gene groups on one side of the split.
- Exclude every V4 and V5 test group from V6 training and V6 testing.
- Keep the V6 test disjoint from all prior test groups and V6 training.
- Select groups without looking at labels, predictions, or outcomes.
- Freeze code, features, preprocessing, threshold, random or hash salts, and manifests
  before opening answers.
- Calculate no test metric during training.
- Save checksums for source data, configuration, model, and partition manifests when
  available.
- Report every result, including a worse result or a failed run.

## Implemented V6: 1,000 Held-Out Records

1. Freeze the complete protocol and current source hash before fitting.
2. Deterministically select 1,000 representatives from fresh connected groups.
3. Quarantine all 4,672 companion records linked to those groups.
4. Exclude all 628 records in V4/V5 test-connected groups from V6 entirely.
5. Confirm zero shared Variation IDs and zero shared connected groups across V6
   training, V6 testing, and prior tests.
6. Train once on the remaining 2,518 records and save the fitted model before testing.
7. Evaluate once and preserve all 1,000 predictions and metrics.

The resulting 75.6% accuracy and 74.4% balanced accuracy are internal validation, not
independent or medical validation. Individual test predictions must not become future
training examples under the same claimed evaluation.

## Next Gate

Complete structured V6 error review and calibration analysis before changing features,
thresholds, or architecture. Give any changed model a new version. Prefer a genuinely
later untouched cohort for the next major test instead of another split of V2.

## Required Reporting

For each stage, report `TN`, `FP`, `FN`, and `TP` with pathogenic as the positive class;
accuracy; balanced accuracy; class-specific precision and recall; class counts; and
confidence intervals. Add ROC AUC, average precision, Brier score, and calibration
plots if saved probabilities support them. Keep matching exclusions and missing-data
counts visible.

## Limits

Both stages remain internal conditional tests of the 2022-to-2024 resolved cohort.
They cannot show performance on all VUS records, cannot test whether a VUS resolves,
and are not independent temporal, clinical, or medical validation. A later untouched
snapshot and external review would still be needed.
