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

I ran a fixed exploratory comparison on the 1,000 previously opened V8 records. I used
five outer component-grouped folds and four inner grouped folds for elastic-net logistic
regression, calibrated histogram gradient boosting, and ExtraTrees. I also scored
consequence-only, majority, frozen V8, and Clue Score V1 baselines. This run did not use
the empty clean-reviewed dataset and cannot select an official V9 model.

| Candidate | Component-weighted balanced accuracy | Row balanced accuracy | Macro F1 | Brier score | TN / FP / FN / TP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen V8 reference | 88.22% | 87.12% | 84.04% | 0.0633 | 740 / 74 / 31 / 155 |
| Elastic-net logistic | 87.35% | 85.80% | 80.18% | 0.0687 | 701 / 113 / 27 / 159 |
| Histogram gradient boosting | 86.17% | 86.15% | 81.13% | 0.0707 | 711 / 103 / 28 / 158 |
| ExtraTrees | 85.70% | 84.99% | 78.13% | 0.0638 | 679 / 135 / 25 / 161 |
| Consequence only | 84.29% | 83.50% | 75.09% | 0.1910 | 646 / 168 / 23 / 163 |
| Majority | 50.00% | 50.00% | 44.87% | 0.1860 | 814 / 0 / 186 / 0 |

Elastic net led the new candidate families, with outer-fold component-weighted balanced
accuracy ranging from 84.77% to 90.46%. Frozen V8 still had the higher same-record point
estimate and better macro F1 and Brier score. I therefore call V8 the strongest
same-record reference, not elastic net the overall winner.

Clue Score V1 made directional calls for 450 of 1,000 records and abstained on 550. It
was correct on 446 of the 450 covered records, but that 45% coverage was selected by the
score's directional thresholds. I report it only as a coverage-conditioned baseline and
do not rank its 99.45% covered-record component-weighted balanced accuracy against models
that predict every row.

## 10. V9 Model Selection Rule

I left the official gates in `research/v9-model-selection-plan.md` locked and used the
separate opened-data protocol in `config/v9_exploratory.json`. The outer and inner folds
were grouped by connected component, each component had equal total weight, and
calibration and threshold selection stayed inside each outer training partition. The
fixed exploratory rule named elastic net the leader among new candidate families.
Frozen V8 and coverage-conditioned Clue Score V1 were references, not rank-eligible new
candidates. I cannot use final-test labels in selection.

## 11. Final V9 Results

I still have no final V9 metrics. The manual-review minimum is not met, the dataset
manifest sets `training_eligible` and `final_test_allowed` to false, the official winner
is `null`, and `final_test_evaluated` is false. The values above are nested out-of-fold
development estimates on opened V8 records, not final V9 results.

## 12. Comparison To V8 And V7

I am keeping V8 frozen at 89.5% accuracy and 87.12% row balanced accuracy with TN 740,
FP 74, FN 31, and TP 155. Its component-weighted balanced accuracy on these records was
88.22%, compared with 87.35% for exploratory elastic net. The 10,000-component bootstrap
interval for elastic net minus V8 was -3.35 to +1.74 percentage points, which crosses
zero. This bootstrap conditions on fixed out-of-fold predictions and does not include
all model-selection uncertainty. Also, the comparison is asymmetric: V8 was evaluated
while sealed, while the exploratory candidates were developed with folds drawn from the
already opened V8 labels. I do not claim that elastic net improves on V8.

## 13. Error Analysis

I queued all 105 V8 errors. An AI-assisted evidence review marked 96 as likely genuine
model errors, 8 as condition-scope ambiguities, and 1 as needing expert provenance
review. Every suggestion still requires human confirmation and did not alter the human
review ledger. The new candidates traded fewer false negatives for many more false
positives: elastic net reduced FN from 31 to 27 but increased FP from 74 to 113.

## 14. Limitations

My task is retrospective and outcome-selected. It does not predict whether a VUS will
resolve. The exploratory labels were already opened, manual review is incomplete, fold
estimates reuse the same 1,000-record cohort, and no later untouched component-disjoint
cohort exists. Later condition and review-status fields were not retained in the frozen
V8 artifact and remain `not recorded`. I previously accessed the July 2026 archive for
V7, and V8 membership is reconstructible. The run used Python 3.14.4 even though the
documented project environment is Python 3.12. Nothing here supports clinical use.

## 15. Strongest Truthful Claim

My V9 preparation now preserves every V8 record, separates review decisions from frozen
labels, and provides an authenticated nested grouped exploratory comparison. Elastic net
was the strongest new candidate family, but frozen V8 had the stronger same-record point
estimate and the paired uncertainty crossed zero. No official or validated V9 model
exists.

## 16. Next Step

My next step is to complete all 31 false-negative and 6 high-confidence false-positive
reviews, review at least 25 true negatives and 25 true positives, resolve or explicitly
queue all 119 V8/V7 disagreements, rebuild the manifest, and inspect exclusion balance.
Until that gate is met, I must use this label: **V9 dataset preparation complete; final V9 model not yet valid.**
