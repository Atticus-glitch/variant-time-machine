# Why Original V9 Scored Lower Than V8

## Bottom Line

Original V9 did not score lower because it used cleaner human-reviewed labels or a harder
new test set. It used the same 1,000 opened V8 records, the same unchanged 814/186 target
distribution, and the same 64 predictor-time features. The largest defensible explanation
is that V9 tried to relearn the task from only those 1,000 opened records, while frozen V8
had learned from 9,818 separate development records. V9 also selected stronger logistic
regularization, different weighting, and much lower decision thresholds.

This diagnosis does not prove one isolated cause. Training size, weighting, calibration,
regularization, and threshold choice changed together. It does show which proposed causes
did not happen: no labels were corrected, no records were scientifically excluded, no
features were dropped, and no new clean test cohort was created.

## Evidence Boundary

The historical artifact requested as **V9 original reviewed-dataset model** is preserved
in `outputs/model_registry/model_v9_original.json`. That label is potentially misleading:
completed human reviews were zero, the clean reviewed dataset had zero rows, and the model
was exploratory. All 1,000 outcomes had already been opened during V8 analysis. There was
no independent V9 test.

## Same-Record Results

| Measure | Frozen V8 | Original V9 elastic net | Difference or consequence |
| --- | ---: | ---: | --- |
| Records | 1,000 | 1,000 | Same records |
| Components | 559 | 559 | Same connected components |
| Benign / pathogenic direction | 814 / 186 | 814 / 186 | Same targets |
| Accuracy | 89.50% | 86.00% | V9 was 3.50 points lower |
| Row balanced accuracy | 87.12% | 85.80% | V9 was 1.32 points lower |
| Component-weighted balanced accuracy | 88.22% | 87.35% | V9 was 0.87 points lower |
| Macro F1 | 84.04% | 80.18% | V9 was lower |
| Pathogenic recall | 83.33% | 85.48% | V9 caught four more net pathogenic rows |
| Benign recall | 90.91% | 86.12% | V9 created many more false positives |
| Brier score | 0.0633 | 0.0687 | V9 probabilities were worse by this measure |
| TN / FP / FN / TP | 740 / 74 / 31 / 155 | 701 / 113 / 27 / 159 | V9 traded 39 extra FP for 4 fewer FN |

The models disagreed on 61 rows. V9 corrected 13 V8 errors, including 9 false negatives,
but changed 48 V8-correct calls into errors. Of those new errors, 43 were true negatives
changed to false positives. The paired component-bootstrap interval for V9 minus V8
component-weighted balanced accuracy was -3.35 to +1.74 percentage points. It crossed
zero, so the observed difference is not a clear generalizable separation.

## Dataset Differences

| Question | Finding |
| --- | --- |
| V8 test records | 1,000 |
| Original V9 independent test records | 0 |
| Original V9 opened development records | 1,000, with 800 used to fit each outer fold |
| V8 development records | 9,818 across 1,792 components |
| Did V9 use fewer records for fitting? | Yes, substantially fewer |
| Did V9 remove easy cases? | No |
| Did V9 add harder cases? | No; it reused the V8 cohort |
| Did class balance change? | No; both used 814 benign-direction and 186 pathogenic-direction records |
| Were labels corrected? | No; corrected labels = 0 |
| Were records scientifically excluded? | No; all 1,000 were review-pending, not excluded |
| Was V9 tested on a harder clean split? | No clean or final test existed |

The V9 clean dataset was empty. Therefore a “cleaner but harder labels” explanation is not
supported for original V9. If future human review changes the eligible cohort, all-record,
clean, strict-clean, ambiguous, and excluded results must be reported separately.

## Label Differences

- Completed human reviews: 0.
- Corrected labels: 0.
- Explicit exclusions: 0.
- False positives explicitly excluded: 0.
- False negatives explicitly excluded: 0.
- Review-pending records: 1,000.
- AI suggestions existed for the 105 V8 errors, but every suggestion required human
  confirmation and none changed a label or model input.

Manual review did not make original V9 cleaner or harder because it had not happened.

## Feature Differences

V8 and original V9 both used the exact authenticated 64-feature V8 schema. V9 did not
drop consequence, review status, submitter, evidence-age, count, HGVS, completeness, or
missense-chemistry fields. Eleven columns happened to be constant in this 1,000-record
cohort, but the schema itself remained complete.

The current feature matrix does not contain authenticated historical population
frequency, conservation, protein-domain, or gene-constraint values. Adding those would
require a separately dated source and preregistered derivation. Gene identity is not a
legitimate shortcut: honest component-grouped validation places a gene component entirely
outside its training fold, so gene encoding would be unseen or leaky.

## Model Differences

| Design choice | Frozen V8 | Original V9 |
| --- | --- | --- |
| Selected family | Calibrated elastic-net logistic | Calibrated elastic-net logistic |
| Typical selected configuration | C=1.0, l1 ratio 0 | Mostly C=0.1, l1 ratio 0 |
| Development size | 9,818 | 1,000 total; 800 per outer fit |
| Weighting | Component weights multiplied by balanced class weights | Exact component weights, no class multiplier |
| Decision threshold | 0.315 | 0.200 to 0.220 across elastic outer folds |
| Evaluation | Sealed temporal component-disjoint V8 test | Nested grouped OOF on opened V8 labels |

Original V9's smaller C imposed stronger regularization and may have underfit. Its very low
thresholds increased pathogenic-direction calls, explaining the recall tradeoff. Removing
the V8 class multiplier was methodologically cleaner for equal-component fitting, but it
also changed the learned probability scale. These coupled changes need controlled
ablation rather than a post hoc single-cause claim.

## Evaluation Differences

V8's 1,000 records were selected and evaluated through a sealed retrospective temporal
protocol with zero development ID and component overlap. Original V9 reused those opened
records in nested component-grouped cross-validation. The grouping was honest internally,
but the comparison is asymmetric: V8 had not learned from those labels, while each V9 OOF
model learned from the other opened V8 labels and V9 model choices were made after V8 was
known.

No untouched later component-disjoint cohort exists in the repository. The July 2026
archive was already accessed, and unused rows from that same outcome-selected archive do
not become a new final test merely because they were not selected for the 1,000-row V8
table.

## Likely Causes

1. **Much less development data.** V9 fit each outer model on about 800 rows rather than
   V8's 9,818 development rows.
2. **Threshold and weighting changes.** V9 selected thresholds near 0.20 and made many
   more pathogenic calls, reducing benign recall.
3. **Stronger regularization.** V9 usually selected C=0.1 rather than V8's C=1.0.
4. **Limited candidate grid.** Original V9 searched only three learned families with a
   small grid and calibrated every learned candidate the same way.
5. **Selection noise in a small grouped cohort.** Fold component-weighted balanced
   accuracy for elastic net ranged from 84.77% to 90.46%.

## What Can Be Improved Honestly

- Keep the same grouped folds for fair diagnostic comparisons.
- Separate effects of feature bundles, class weighting, calibration, and thresholding.
- Compare a modest preregistered set of linear, tree, SVM, and small neural candidates.
- Tune configurations and thresholds only inside each outer training partition.
- Report uncalibrated and calibrated variants instead of assuming calibration helps.
- Report component-weighted and row-weighted metrics, calibration, fold stability, and
  paired component-bootstrap uncertainty.
- Preserve every row in all-eligible, pending/ambiguous, clean, strict, and excluded
  accounting even when clean review remains empty.

## What Must Not Be Changed To Raise A Score

- Do not correct or exclude records without a recorded human decision.
- Do not use V8 correctness, AI review suggestions, manual decisions, later metadata, or
  resolved outcomes as predictors.
- Do not tune using V8 predictions or a claimed final V9.1 test.
- Do not use gene identity across component-disjoint folds.
- Do not call internal validation an independent test.
- Do not compare filtered clean scores with V8's all-record score as if cohorts match.

## What The Lower Score Means

The lower point estimate is a real result on these records, but it is not evidence that a
reviewed-dataset approach failed because no reviewed dataset was used. It is evidence that
retraining a more strongly regularized, lower-threshold model on a much smaller opened
cohort did not reproduce frozen V8's performance. It also shows a potentially useful
recall tradeoff, but the extra false positives were too numerous to call it an overall
improvement.
