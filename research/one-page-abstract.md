# Variant Time Machine: One-Page Abstract

## Background

ClinVar records genetic variant classifications that can change as evidence develops.
This project asks whether information available in an older ClinVar snapshot contains
signals about the later direction of variants of uncertain significance (VUS). The
work is a historical research experiment, not a diagnostic or medical tool.

## Method

The development cohort uses January 2022 predictor and January 2024 answer snapshots.
V7 and V8 use January 2024 predictors and July 2026 answers. Records are
matched conservatively by Variation and Allele IDs and restricted to germline variants.
The binary task remains conditional on a clear later benign or pathogenic outcome.

The project progressed from a fixed clue score to logistic regression, three
neural-network experiments, and a temporal gradient-boosting test. V4 used 11 older-only hint indicators. V5 added
numeric age, submitter-count, and missing-field inputs, training-only class balancing,
feature scaling, and two hidden layers. V6 kept that model design but reserved 1,000
new group-isolated records before retraining. V6 training excluded its test records,
their 4,672 connected companions, and all 628 records in prior V4/V5 test groups.
V7 used all 8,818 development records, selected and calibrated its model with grouped
out-of-fold predictions, and sealed January 2024 predictions before the July 2026
answer archive was downloaded.
V8 excluded every predictor-time gene component touching development and every V7 test
ID, then evaluated the preregistered sealed model once on 1,000 records in 559
components.

## Results

V4 achieved 76% accuracy and 62.5% balanced accuracy on 100 records. Its confusion
matrix was TN 68, FP 0, FN 24, TP 8, with pathogenic treated as positive. V5 achieved
82% accuracy and 82.1978% balanced accuracy on a different 100 records. Its confusion
matrix was TN 53, FP 12, FN 6, TP 29.

V6 achieved 75.6% accuracy, 74.4% balanced accuracy, and 72.9% macro F1 on 1,000
different records (`TN 535, FP 154, FN 90, TP 221`). Its train/test Variation ID and
connected-group overlaps were both zero. V5 retains the highest point estimate on its
own small test; V6 supplies the larger and more cautious estimate. Because records and
training memberships differ, these results do not identify a stable winner.

V7 achieved 78.5% accuracy, 79.1% balanced accuracy, and ROC AUC 0.885 on 1,000
record-level temporal tests (`TN 629, FP 176, FN 39, TP 156`). Test Variation ID overlap
with development was zero. V7 detected 80% of pathogenic-direction outcomes; a
majority-benign baseline had 80.5% raw accuracy but 0% pathogenic recall.

V8 contained 814 benign and 186 pathogenic outcomes and achieved 89.5% accuracy,
87.1212% balanced accuracy, 84.0371% macro F1, ROC AUC 0.94594, average precision
0.83895, and Brier score 0.06332 (`TN 740, FP 74, FN 31, TP 155`). Development ID and
component overlap and V7-test-ID overlap were zero. On these same records frozen V7
reached 86.6688% balanced accuracy. The V8 difference was +0.4524 points, with a
component-bootstrap interval of -2.45 to +3.31 points, so overall superiority was not
demonstrated. Missense balanced accuracy was 63.82% for V8 versus 55.88% for V7 on 230
records, but its paired interval also included zero.

## Conclusion

The experiment shows why balanced accuracy, confusion matrices, and sample size matter.
V4's 76% accuracy hid weak pathogenic recall. V5's small test looked much more balanced.
V6 then tested that pattern at ten times the scale and produced a more modest result.
Following the result instead of defending it led first to V7's later cohort and then to
V8's development-component-disjoint test. V8 improved the point estimate on the same
records, but uncertainty rules out an overall superiority claim.

V8 remains a retrospective, reconstructible-membership test because July 2026 was
already accessed for V7. Its fitting weights were not strictly equal per component, its
simplicity tie-break did not rank within-family regularization, and out-of-fold labels
were reused for selection, calibration, and threshold choice. All findings remain
conditional on clear later resolution. They are not clinical or medical validation, do
not predict whether a VUS will resolve, and should not guide patient care.
