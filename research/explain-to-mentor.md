# Explaining Variant Time Machine to a Mentor

## Short Explanation

I independently built Variant Time Machine to study a narrow historical question in public ClinVar data: among variants classified as uncertain at an earlier date and known to have a clear later aggregate classification, can older information predict whether that classification moves toward benign or pathogenic? "Independently built" describes my role in creating the project; it does not mean the results have independent, external, or clinical validation.

## Data Snapshots

I used official NCBI ClinVar historical releases rather than current web pages. The main development data compare the January 6, 2022 predictor snapshot with the January 4, 2024 answer snapshot. V7 and V8 move the predictor date to January 2024 and the answer date to July 2026. The task is conditional: it includes records that were VUS at predictor time and had a safely matched, clear later benign- or pathogenic-direction aggregate outcome. It does not predict whether a VUS will resolve.

## Main Methodological Focus

My main focus has been future-information leakage. I restricted predictors to fields available in the older snapshot, excluded identifiers and newer outcomes from features, preserved source hashes and frozen protocols, and separated records by connected predictor-time gene components. For V8, the test had zero Variation ID and zero gene-component overlap with the development ledger, and zero Variation ID overlap with the V7 test. The model and 378,552 eligible candidate predictions were committed before the label vault was opened, and the sealed test was evaluated once.

## Why There Are Multiple Versions

The numbered versions record changes in methods rather than repeated attempts to polish one result. Early versions tested clue scores and small holdouts. V4's 76% accuracy concealed weak pathogenic recall. V5 looked stronger on a different 100-record test. V6 used a 1,000-record group-isolated holdout and produced a more modest result. V7 moved to a later temporal cohort. V8 added the strongest project-defined component-isolation protocol. Results across different cohorts are not a leaderboard, and V8's same-record comparison with frozen V7 does not establish superiority.

## V8 Result

V8 used a preregistered logistic regression and a fixed threshold. On a sealed 1,000-record retrospective test spanning 559 predictor-time gene components, it recorded 89.5% accuracy and 87.1212% balanced accuracy, with 90.91% benign recall and 83.33% pathogenic recall (`TN 740, FP 74, FN 31, TP 155`). Macro F1 was 84.0371%, ROC AUC 0.94594, average precision 0.83895, and Brier score 0.06332.

V8 is the project's best-performing current retrospective model on its own sealed test.
That description is not a cross-cohort ranking and does not establish clinical value.

Frozen V7 recorded 86.6688% balanced accuracy on the same records. V8's difference was +0.4524 percentage points, with a 95% component-bootstrap interval from -2.45 to +3.31 points. Because the interval crosses zero, I do not claim that V8 improved on or outperformed V7.

## Important Limitations

- The later outcome is an aggregate ClinVar classification, not condition-specific or error-free truth.
- The cohort was selected because it had a clear later outcome, so the result does not apply to all VUS.
- V8 is retrospective. The July 2026 archive had already been accessed for V7, and V8 membership is reconstructible even though it was hidden during development.
- Gene-component separation addresses one leakage path but does not prove biological independence or broad generalization.
- The records span 559 components, so 1,000 records are not 1,000 independent gene samples.
- Fitting weights were not strictly equal in total per component, the simplicity tie-break did not rank regularization within the selected family, and grouped out-of-fold labels were reused in selection, calibration, and threshold choice.
- The project offers no diagnosis, medical advice, clinical utility, or basis for patient care.

## Feedback I Need

- Does the outcome-selected cohort answer a scientifically useful question?
- Are the matching, aggregate-label, and connected-component definitions defensible?
- What hidden leakage or selection-bias paths remain?
- Is component bootstrap the right uncertainty unit, and how should calibration uncertainty be reported?
- Which high-confidence FP/FN records should be checked first, and what evidence should a structured manual review capture?
- How should I design a genuinely later untouched evaluation without using July 2026 again for model development and testing?

The most useful feedback would identify a methodological weakness or a falsifying check to complete before scaling, not endorse the headline score.

The project and dashboard are research communication tools only, not medical advice.
