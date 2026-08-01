# Variant Time Machine: One-Page Abstract

## Background

ClinVar records genetic variant classifications that can change as evidence develops.
This project asks whether information available in an older ClinVar snapshot contains
signals about the later direction of variants of uncertain significance (VUS). The
work is a historical research experiment, not a diagnostic or medical tool.

## Method

The predictor snapshot is the January 6, 2022 archived ClinVar `variant_summary`; the
answer snapshot is January 4, 2024. Records are matched conservatively by identifiers
and restricted to germline variants that were exactly uncertain in 2022. The current
binary modeling cohort is conditional on a clear benign or pathogenic aggregate
outcome in 2024. Models use only older-snapshot inputs, and connected older-gene groups
are kept out of both training and testing to reduce related-record leakage.

The project progressed from a fixed clue score to logistic regression and then to three
neural-network experiments. V4 used 11 older-only hint indicators. V5 added
numeric age, submitter-count, and missing-field inputs, training-only class balancing,
feature scaling, and two hidden layers. V6 kept that model design but reserved 1,000
new group-isolated records before retraining. V6 training excluded its test records,
their 4,672 connected companions, and all 628 records in prior V4/V5 test groups.

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

## Conclusion

The experiment shows why balanced accuracy, confusion matrices, and sample size matter.
V4's 76% accuracy hid weak pathogenic recall. V5's small test looked much more balanced.
V6 then tested that pattern at ten times the scale and produced a more modest result.
Following the result instead of defending it has made the next question clearer: can a
frozen model generalize to a genuinely later untouched cohort?

All current findings are internal and conditional on the selected 2022-to-2024 cohort.
They are not independent temporal, clinical, or medical validation, do not predict
whether a VUS will resolve, and should not guide patient care.
