# Project Summary for Mentors

## Project

Variant Time Machine studies a narrow historical question: among ClinVar variants that
were uncertain on January 6, 2022 and had a clear benign or pathogenic aggregate
classification on January 4, 2024, can older information predict the direction of
that resolution? It does not predict whether a variant will resolve and is not a
medical tool.

## Work Completed

The project includes a reproducible Python pipeline, conservative matching rules,
synthetic software tests, source and decision records, a local dashboard, simple
baselines, logistic regression, three frozen neural-network holdouts, a sealed
record-level temporal evaluation, and a preregistered component-disjoint retrospective
test.
The repository is configured with a GitHub remote; this summary does not claim that
the repository or website is publicly accessible.

Development was deliberately staged. Early work tested small official NCBI requests
and documented why a multi-gigabyte XML route was paused. The later tab-delimited
workflow used the fixed January 6, 2022 and January 4, 2024 snapshots and kept newer
fields out of model inputs.

## Current Evidence

| Model | n | Accuracy | Balanced accuracy | Benign recall | Pathogenic recall | Confusion matrix |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| V4 | 100 | 76.0% | 62.5% | 100.0% | 25.0% | TN 68, FP 0, FN 24, TP 8 |
| V5 | 100 | 82.0% | 82.2% | 81.5% | 82.9% | TN 53, FP 12, FN 6, TP 29 |
| V6 | 1,000 | 75.6% | 74.4% | 77.6% | 71.1% | TN 535, FP 154, FN 90, TP 221 |
| V7 | 1,000 | 78.5% | 79.1% | 78.1% | 80.0% | TN 629, FP 176, FN 39, TP 156 |
| V8 | 1,000 | 89.5% | 87.1212% | 90.91% | 83.33% | TN 740, FP 74, FN 31, TP 155 |

Pathogenic is the positive class. V6's 1,000 records and their groups were excluded
before V6 fitting, as were all prior internal-test groups. Different cohorts, training
sets, and temporal boundaries prevent a cross-version winner claim.

V7 moves the predictor to January 2024 and the answer to July 2026. Candidate
predictions were hashed before the answer download, and test IDs had zero development
overlap. V7 has the strongest archive-time boundary, although 69.9% of test records
shared a gene with development and the test remains conditional on clear resolution.

V8's 1,000 records span 559 predictor-time gene components and have zero development
ID/component and V7-test-ID overlap. V8's macro F1 was 84.0371%, ROC AUC 0.94594,
average precision 0.83895, and Brier score 0.06332. On the same records V7 reached
86.6688% balanced accuracy; V8's +0.4524-point difference had a component-bootstrap
interval of -2.45 to +3.31 points, so no overall superiority was demonstrated. The
230-record missense point comparison favored V8, 63.82% to 55.88%, but its paired
interval also included zero.

V8 has the strongest component-isolation design, not an unqualified strongest-evidence
claim. It is retrospective and reconstructible from the already-accessed archive.

## Main Limitations

- The cohort is selected using clear 2024 outcomes, so results apply only conditionally
  to this resolved cohort.
- These are internal holdouts, not independent temporal, clinical, or medical
  validation.
- Aggregate ClinVar records are not error-free ground truth and can combine evidence
  across conditions and submitters.
- Connected-gene grouping reduces one leakage risk but does not prove broad
  generalization.
- V4/V5 are small; V6 is larger but still comes from the same outcome-selected cohort.
- The current V2 database byte hash differs from the V4/V5 recorded source hash. V6
  freezes the current hash rather than rewriting prior provenance.
- V7's raw accuracy did not exceed the majority-benign baseline. Its advantage is
  balanced discrimination and 80% pathogenic recall.
- V8 is membership-hidden but retrospective, and membership is reconstructible from
  the published salt and already-accessed July 2026 archive.
- V8's combined component/class weighting was not strictly equal per component, its
  tie-break did not rank regularization within the selected family, and out-of-fold
  labels were reused for selection, calibration, and threshold choice.

## Proposed Next Step

Review V8 errors and calibration, especially missense records, without converting a
nonsignificant subgroup point difference into a claim. Any changed model must wait for
another sealed future answer snapshot rather than reusing July 2026 as a test.

## Where Mentorship Would Help

- Review whether the cohort and grouping rules answer a useful scientific question.
- Check the matching and outcome definitions for hidden sources of bias.
- Advise on confidence intervals, calibration, and comparison across distinct tests.
- Help design later temporal validation without leaking future information.
- Challenge claims so that reports remain proportional to the evidence.

The most useful mentor response would identify one methodological weakness to fix
before scaling, rather than endorsing the current model score.
