# AI Temporal V7 Results

## Why the Design Changed

V6 answered the 1,000-record question honestly, but its group-isolated split left only
2,518 training records. Error analysis found that 214 of 244 mistakes were missense
variants. Instead of tuning against those 1,000 answers and testing on them again, V7
moved the clock forward.

V7 used all 8,818 records from the 2022-to-2024 development cohort. A frozen five-fold
grouped comparison selected shallow histogram gradient boosting over regularized
logistic regression and larger boosting variants. Calibration and the 0.28 decision
threshold came only from grouped out-of-fold development predictions.

## Sealing Sequence

1. Freeze the feature list, candidate models, folds, threshold rule, snapshots, and
   exact 1,000-record selection salt.
2. Train on the complete development cohort, including previously opened V4-V6 records.
3. Identify 761,235 exact January 2024 germline VUS Variation IDs absent from the entire
   January 2022 snapshot.
4. Save and hash every candidate prediction.
5. Only then download the fixed July 2, 2026 archived `variant_summary` answer file.
6. Safely match Variation and complete Allele ID sets, require exclusively germline
   scope and one clear aggregate outcome, then hash-select exactly 1,000 outcomes.

The sealed-prediction SHA-256 is
`2ceee889b39b470c7f5b6ea59d620950ab861068014d40344506acacac3bc4bf`.
The July 2026 answer SHA-256 is
`b3da921c707ff50cb4822f04d961834a9e89ef864b4c28bb5308245b93ac4077`.
Development/test Variation ID overlap is zero.

## Frozen Result

| Metric | Result |
| --- | ---: |
| Test records | 1,000 |
| Accuracy | 78.5% |
| Balanced accuracy | 79.1% |
| Macro F1 | 72.3% |
| ROC AUC | 0.885 |
| Average precision | 0.750 |
| Brier score | 0.086 |
| Benign recall | 78.1% |
| Pathogenic recall | 80.0% |

The test contained 805 benign-direction and 195 pathogenic-direction outcomes. The
confusion matrix was `TN 629, FP 176, FN 39, TP 156`.

The majority-benign baseline had higher raw accuracy, 80.5%, but only 50% balanced
accuracy and 0% pathogenic recall. V7 deliberately traded some benign accuracy for
detecting 156 of 195 pathogenic-direction outcomes. That trade is visible rather than
hidden behind one metric.

## Error Pattern

Missense remained the hard problem: 186 of 215 V7 errors were missense records. In
contrast, accuracy exceeded 94% for loss-of-function, canonical splice, synonymous,
and noncoding groups. The model was strongest at probability extremes and overestimated
pathogenic frequency in parts of the middle range; its ten-bin calibration error was
about 4.7 percentage points.

## Interpretation Boundary

All 1,000 Variation IDs were new to development, but 699 shared at least one gene with
development. The confidence interval for raw accuracy is approximately 75.8%-80.9%.
The cohort is also selected because records safely reached a clear benign or pathogenic
aggregate classification by July 2026. V7 therefore predicts direction conditional on
resolution, not whether a VUS resolves.

Thirty sealed candidates were absent from the July 2026 snapshot; they are counted as
missing, not as outcomes. The protocol and result are committed together after the run.
Artifact timestamps and content hashes preserve the sealing sequence, but there was no
external custodian or public preregistration before answer access.

This is the project's strongest temporal evidence so far, not clinical validation. It
uses public aggregate classifications, allows same-gene overlap, and must not guide
patient care.
