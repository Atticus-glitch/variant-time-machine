# Strongest Truthful V8 Claim

## One-Sentence Claim

On the sealed 1,000-record gene-component-disjoint retrospective temporal test, V8 recorded 89.5% accuracy and 87.12% balanced accuracy.

## Claim Close to User Wording

Using only information recorded in the January 2024 ClinVar snapshot, the independently built V8 model predicted whether 1,000 variants then classified as uncertain later moved toward a benign or pathogenic aggregate classification in the July 2026 snapshot. On this sealed, retrospective test, whose Variation IDs and predictor-time gene components did not overlap the development ledger, V8 recorded 89.5% accuracy, 87.12% balanced accuracy, 90.91% benign recall, and 83.33% pathogenic recall (`TN 740, FP 74, FN 31, TP 155`).

## What This Does Not Mean

- It does not predict whether a VUS will resolve; the test included only records with a clear later benign- or pathogenic-direction outcome.
- It does not determine whether a variant is medically harmful or harmless.
- It is not diagnosis, clinical validation, medical advice, or evidence for clinical use.
- It does not establish condition-specific truth; ClinVar aggregate classifications can combine submissions, conditions, and evidence.
- Gene-component disjointness addresses one project-defined leakage risk. It does not prove biological independence or generalization to unrelated future data.
- It does not show that V8 is superior to V7. On the same records, the paired V8-minus-V7 balanced-accuracy interval crossed zero.
- "Independently built" describes who built the project. It does not mean independently validated.

## Wording to Avoid

- "V8 predicts which uncertain variants are pathogenic."
- "V8 diagnoses genetic disease" or "can guide patient care."
- "V8 is 89.5% clinically accurate."
- "V8 predicts VUS resolution."
- "V8 generalizes to unseen genes" or "is gene-independent."
- "V8 outperforms V7" or "is better than existing methods."
- "Prospective validation," "external validation," or "independent validation."
- "Ground truth" for the later aggregate ClinVar classification.

## Caveats That Must Travel With the Claim

- The 1,000 records were selected from January 2024 VUS records that had a safely matched, clear aggregate direction by July 2026; the result is conditional on that outcome-selected cohort.
- The test spans 559 predictor-time gene components, so it is not 1,000 independent gene samples.
- The July 2026 archive had already been accessed for V7. V8 membership was procedurally hidden during development but is reconstructible from the published salt and archive.
- Frozen V7 recorded 86.6688% balanced accuracy on the same records. V8's point difference was +0.4524 percentage points, with a 95% component-bootstrap interval from -2.45 to +3.31 points; no improvement is claimed.
- Combined inverse-component and class-balanced fitting weights were not strictly equal in total per component.
- The simplicity tie-break selected a model family but did not rank regularization strengths within that family.
- Grouped out-of-fold labels were reused for candidate selection, calibration, and threshold selection.
- Manual review of errors and a genuinely later untouched cohort are still needed.
