# Variant Time Machine Poster Outline

## 1. Title

**Variant Time Machine: A Leakage-Conscious Retrospective Test of VUS Classification Direction**

Subtitle: Historical public ClinVar research, not diagnosis or clinical validation.

## 2. Background

ClinVar aggregates submitted classifications of genetic variants. Variants of
uncertain significance (VUS) can later move toward a benign or pathogenic aggregate
classification as public evidence changes. A historical snapshot study can test
whether the older record contained useful directional signals, but it cannot determine
patient-level meaning or predict whether a VUS will resolve.

## 3. Research Question

Among variants classified as uncertain in an earlier official ClinVar snapshot and
known to have a clear later aggregate classification, can older-snapshot information
predict the direction of that later classification without future-data leakage?

## 4. Data

- Official NCBI ClinVar archived `variant_summary` snapshots.
- January 2022 predictors to January 2024 outcomes for initial development.
- January 2024 predictors to July 2026 outcomes for V7 and V8.
- V8 test: 1,000 records, 814 benign-direction and 186 pathogenic-direction outcomes,
  spanning 559 predictor-time gene components.
- The cohort is outcome-selected: only safely matched records with a clear later
  direction are scored.

## 5. Methods

Describe conservative identifier and allele matching, germline scope, older-only
features, forbidden identity and future fields, connected gene components, grouped
development, frozen model and prediction commitments, and one-time vault evaluation.
V8 used calibrated elastic-net logistic regression with a fixed 0.315 threshold.

## 6. Model Versions

Show V1 through V8 as a methodology timeline rather than a score leaderboard. Early
versions used clue scores and internal holdouts; V7 introduced the later temporal
cohort; V8 added the strongest project-defined component-isolation design. Cohorts and
tasks differ, so most cross-version scores are descriptive rather than paired effects.

## 7. V8 Result

On the sealed 1,000-record retrospective test, V8 recorded 89.5% accuracy, 87.12%
balanced accuracy, 84.04% macro F1, 90.91% benign recall, and 83.33% pathogenic recall.
Confusion matrix: TN 740, FP 74, FN 31, TP 155. The recorded leakage and artifact audit
passed.

## 8. V8 vs V7 Comparison

Frozen V7 was scored on the same 1,000 V8 records. V7 recorded 86.67% balanced accuracy
and V8 recorded 87.12%, a +0.45-point difference. The component-bootstrap 95% interval
was -2.45 to +3.31 points. Because it crosses zero, V8 did not demonstrate statistically
clear overall superiority over V7.

## 9. Error Analysis

V8 made 105 errors: 74 false positives and 31 false negatives. Automatic categories
are unverified triage suggestions. Prioritize 19 high-confidence errors, false negatives,
missense errors, noncoding false negatives, severe-consequence false positives,
unrecognized consequences, and V8/V7 disagreements. Include deterministic TN, TP, FP,
and FN case studies rather than selected success stories.

## 10. Limitations

The experiment is retrospective and conditional on clear later outcomes. Aggregate
ClinVar labels can combine conditions, submitters, and imperfect evidence. The archive
had already been accessed for V7, V8 membership is reconstructible, and component
separation does not prove biological independence. Preserve the fitting-weight,
tie-break, and out-of-fold reuse caveats.

## 11. Next Steps

Complete structured manual review of frozen errors and correct controls. Seek mentor
feedback on matching, biological interpretation, calibration, and uncertainty. Any
future model change should receive a new version and a genuinely later untouched
evaluation; the current task is not to create V9.

## 12. Not Medical Advice

Variant Time Machine is a retrospective historical research project using public
aggregate data. It is not medical advice, clinical validation, a diagnostic system, or
a tool for interpreting patient variants.

## Suggested Figures

1. Workflow diagram from historical snapshots through matching, leakage controls,
   frozen prediction commitment, and evaluation.
2. V8 confusion matrix with plain-English direction labels.
3. Model-version timeline from V1 through V8 without a cross-cohort leaderboard.
4. V8 versus frozen V7 same-record balanced-accuracy comparison with paired interval.
5. Error-analysis breakdown by FP/FN, consequence, confidence, and unverified category.
6. Example case timeline showing older VUS, V8 prediction, later aggregate direction,
   source link, and manual-review status.
