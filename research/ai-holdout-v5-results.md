# AI Holdout V5 Results

Tested: 2026-08-01T21:05:05.514653+00:00

## Result

- Hidden records: 100
- Correct: 82
- Wrong: 18
- Accuracy: 82%
- Balanced accuracy: 82.1978%
- Actual benign: 65
- Actual pathogenic: 35
- Benign recall: 81.5385% (53 of 65)
- Pathogenic recall: 82.8571% (29 of 35)

With pathogenic as the positive class, the confusion matrix is:

| | Predicted benign | Predicted pathogenic |
| --- | ---: | ---: |
| Actual benign | TN 53 | FP 12 |
| Actual pathogenic | FN 6 | TP 29 |

## Comparison With V4

V4 tested 100 different records and achieved 76% accuracy and 62.5% balanced accuracy,
with TN 68, FP 0, FN 24, and TP 8. V4 and V5 share zero test connected groups. V5 is
apparently stronger across class balance and made fewer false-negative errors in its
own test, but the results are not a paired comparison.

Each model was tested on a distinct set of only 100 records, and V5 was designed after
the aggregate V4 result was known. The evidence therefore does not establish a stable
winner. Both complete results should be preserved without retraining either model on
its hidden answers.

## Boundary

This is an internal test from the conditional cohort of variants that were uncertain
in the January 6, 2022 ClinVar snapshot and had a clear benign or pathogenic aggregate
outcome in the January 4, 2024 snapshot. It does not predict whether a VUS will resolve.
It is not independent temporal, clinical, or medical validation and must not guide
patient care.

The next evaluation became V6 rather than an expansion of V5. V6 reserved 1,000 new
connected-group representatives before fitting, excluded all V4/V5 test groups, and
reported 75.6% accuracy and 74.4% balanced accuracy without retuning on its answers.
