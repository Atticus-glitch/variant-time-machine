# Variant Time Machine: One-Page Abstract

## Background

ClinVar records genetic variant classifications that can change as evidence develops.
This project asks whether information available in an older ClinVar snapshot contains
signals about the later direction of variants of uncertain significance (VUS). The
work is a historical research experiment, not a diagnostic or medical tool.

## Method

The development cohort uses January 2022 predictor and January 2024 answer snapshots.
V7 adds a temporal test with January 2024 predictors and July 2026 answers. Records are
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

## Conclusion

The experiment shows why balanced accuracy, confusion matrices, and sample size matter.
V4's 76% accuracy hid weak pathogenic recall. V5's small test looked much more balanced.
V6 then tested that pattern at ten times the scale and produced a more modest result.
Following the result instead of defending it led to V7's later temporal cohort. Its
remaining challenge is concentrated: 186 of 215 errors were missense variants.

V7 is temporal at the record level, but 69.9% of tests shared a development gene. All
findings remain conditional on clear later resolution. They are not clinical or medical
validation, do not predict whether a VUS will resolve, and should not guide patient care.
