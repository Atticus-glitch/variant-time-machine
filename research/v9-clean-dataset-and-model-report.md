# V9 Clean Dataset And Model Report

## 1. Purpose

I am using this partially complete report to document the review and dataset-preparation
stage between frozen V8 and any future V9. My goal is to get better evidence and clearer
labels, not to remove difficult errors just to raise a score.

## 2. Why V8 Errors Need Manual Review

V8 evaluated 1,000 records and made 105 wrong predictions: 74 false positives and 31
false negatives. I need review to separate genuine model errors from bad matches,
condition-scope changes, aggregate-label ambiguity, missing fields, and cases requiring
expert judgment.

## 3. Manual Review Schema

I use `docs/manual-review-schema.md` and `config/manual_review_schema.yaml` to keep the
automatic fields immutable and to separate manual decisions, corrections, inclusion
flags, notes, reviewer identity, and reviewer confidence. No correction overwrites V8.

## 4. Review Queue Construction

I built the deterministic queue with all 1,000 V8 records because every row has at least
one computer suggestion, including the honestly recorded absence of a VCV accession in
the frozen V8 artifacts. I put all 31 false negatives first, followed by all 74 false
positives, V8/V7 disagreements, warning records, and seeded controls. The queue includes
seeded samples of 25 true negatives, 25 true positives, and 25 low-confidence records.

## 5. Inclusion/Exclusion Rules

I keep eligible original automatic labels in the messy dataset. For clean inclusion, I
require a completed review that approves the identity, scope, and label, explicitly
includes the record, and leaves no unresolved severe automatic flag. I keep bad matches,
wrong scope, conflicting labels, missing critical identity fields, and expert-needed
records visible in the exclusion ledger.

## 6. Dataset Counts

| Item | Current count |
| --- | ---: |
| V8 test records | 1,000 |
| TN / FP / FN / TP | 740 / 74 / 31 / 155 |
| Wrong predictions | 105 |
| Completed manual reviews | 0 |
| V9 messy rows | 1,000 |
| V9 clean reviewed rows | 0 |
| Excluded or review-pending rows | 1,000 |
| Corrected outcomes | 0 |
| Needs expert review | 0 |

The 1,000 records currently outside the clean dataset are review-pending. I have not
hidden or scientifically discarded them.

## 7. Exclusion Reasons

The current manifest reports `manual_review_pending` for all 1,000 records. I will make
future explicit exclusions retain their manual decision, category, note, original label,
and any corrected outcome. I keep pending review separate from a scientific exclusion.

## 8. Risk Of Cherry-Picking And How It Was Handled

I keep V8 metrics fixed on all 1,000 records. The builder reports class distribution,
excluded FP/FN counts, correction counts, and every exclusion reason. It always warns:

> Clean-dataset performance is not directly comparable to messy all-record performance
> if many hard or ambiguous records were excluded.

In any future V9 report, I must show all-record, clean-record, and excluded/ambiguous
results where labels permit. I must also state if cleaning disproportionately removes
V8 errors.

## 9. V9 Model Candidates

My frozen candidate plan includes elastic-net logistic regression, calibrated histogram
gradient boosting, ExtraTrees or random forest, clue-score, consequence-only, majority,
and frozen V8 same-record baselines. I have not trained any candidate.

## 10. V9 Model Selection Rule

I follow `research/v9-model-selection-plan.md`, which requires a leakage pass,
grouped-validation balanced accuracy, macro F1, pathogenic recall, calibration,
bootstrap stability, interpretability, and simplicity. I cannot use final-test labels in
selection.

## 11. Final V9 Results

I have no final V9 metrics. The manual-review minimum is not met, the manifest sets
`training_eligible` and `final_test_allowed` to false, and I have not trained or
evaluated a candidate or final model.

## 12. Comparison To V8 And V7

I am keeping V8 frozen at 89.5% accuracy and 87.12% balanced accuracy with TN 740, FP
74, FN 31, and TP 155. Same-record V7 balanced accuracy was 86.67%; the paired interval
for the V8-V7 difference crossed zero, so I do not claim clear superiority. There is no
V9 comparison yet.

## 13. Error Analysis

I queued all 105 V8 errors. Computer flags identify high-confidence wrong cases, V8/V7
disagreement, missing retained VCV accession, unrecognized consequence, and related
component groups. I treat these as suggestions for review, not conclusions.

## 14. Limitations

My task is retrospective and outcome-selected. It does not predict whether a VUS will
resolve. Later condition and review-status fields were not retained in the frozen V8
artifact and remain `not recorded`. I previously accessed the July 2026 archive for V7,
and V8 membership is reconstructible. Nothing here supports clinical use.

## 15. Strongest Truthful Claim

My V9 dataset preparation now reproducibly preserves all V8 records, queues every error,
stores review decisions separately, and can build messy, clean, excluded, and
expert-needed tables without overwriting original labels. It is not yet a trained or
validated V9 model.

## 16. Next Step

My next step is to complete all 31 false-negative and 6 high-confidence false-positive
reviews, review at least 25 true negatives and 25 true positives, resolve or explicitly
queue all 119 V8/V7 disagreements, rebuild the manifest, and inspect exclusion balance.
Until that gate is met, I must use this label: **V9 dataset preparation complete; final
V9 model not yet valid.**
