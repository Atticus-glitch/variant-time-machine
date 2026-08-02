# AI Temporal V8 Results

## Result

V8 evaluated exactly 1,000 January 2024 VUS records with clear benign- or
pathogenic-direction aggregate outcomes in July 2026. The sealed test contained 814
benign and 186 pathogenic outcomes across 559 predictor-time gene components.

| Metric | V8 result |
| --- | ---: |
| Accuracy | 89.5% |
| Balanced accuracy | 87.1212% |
| Macro F1 | 84.0371% |
| Benign recall | 90.91% |
| Pathogenic recall | 83.33% |
| ROC AUC | 0.94594 |
| Average precision | 0.83895 |
| Brier score | 0.06332 |
| Confusion matrix | TN 740, FP 74, FN 31, TP 155 |

Pathogenic is the positive class. The majority-benign baseline would score 81.4% raw
accuracy, 50% balanced accuracy, and 0% pathogenic recall on this cohort. V8's result
therefore reflects discrimination across both classes rather than class prevalence
alone.

## Isolation Checks

The final test had zero Variation ID overlap and zero predictor-time gene-component
overlap with the complete development ledger. It also had zero Variation ID overlap
with the opened V7 test. The 1,000 records belong to 559 components, so they are not
1,000 independent gene samples; uncertainty was bootstrapped by sealed component.

V8 used the preregistered logistic regression (`C=1`, `l1_ratio=0`) and fixed threshold
of 0.315. The model and all 378,552 eligible candidate predictions were committed
before the label vault was opened. The one allowed evaluation preserved the sealed
predictions.

## Paired V7 Comparison

Frozen V7 predictions were scored on the same 1,000 V8 records. V7 reached 86.6688%
balanced accuracy and V8 reached 87.1212%, a paired difference of +0.4524 percentage
points. The 10,000-replicate component-bootstrap 95% confidence interval for the
difference was -2.45 to +3.31 percentage points. Because the interval includes zero,
the test does not establish overall V8 superiority to V7.

The preregistered missense subset contained 230 records. V8 reached 63.82% balanced
accuracy and same-record V7 reached 55.88%. The paired component-bootstrap confidence
interval includes zero, so this larger point difference is promising subgroup evidence,
not a demonstrated missense improvement.

## Interpretation Boundary

V8 strengthens the evidence by removing all development/test predictor-time gene-
component overlap and by comparing V8 with frozen V7 predictions on the same records.
It does not establish biological independence between genes, predict whether a VUS
will resolve, provide condition-specific truth, or support clinical use. Evaluation is
conditional on records selected because they had a safe clear July 2026 outcome.

V8 is a membership-hidden retrospective test, not a never-opened prospective or future
test. The July 2026 archive had already been accessed for V7. "Membership-hidden"
describes procedural separation inside the project, not cryptographic secrecy: the
published salt and accessible archive make membership reconstructible by deliberately
rerunning label selection.

The preregistered implementation caveats remain part of the result:

- combined inverse-component and balanced-class sample weights mean effective fitting
  weights did not give every component strictly equal total weight;
- the simplicity tie-break preferred logistic regression as a family but did not rank
  regularization strengths within that family;
- grouped out-of-fold labels were reused for final candidate selection, calibration,
  and threshold selection, while the separately reported nested 0.5-threshold estimate
  does not evaluate the full deployed procedure.

These caveats qualify development and selection claims; they do not alter the sealed
test predictions or justify a post-result rerun.
