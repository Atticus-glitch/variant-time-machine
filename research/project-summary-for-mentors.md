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
baselines, logistic regression, and three frozen neural-network holdout experiments.
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

Pathogenic is the positive class. Every test uses distinct connected groups. V6's
1,000 records and their groups were excluded before V6 fitting, as were all prior test
groups. V5 has the highest point score on its own test, while V6 has the strongest
sample-size evidence and a more modest estimate. Different cohorts and training sets
prevent a head-to-head winner claim.

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

## Proposed Next Step

Review a predeclared sample of V6's 244 errors, assess calibration, and decide whether
any model change is justified. The next major test should use a genuinely later
untouched ClinVar snapshot or external cohort, with Variation IDs and connected groups
checked against all training data before evaluation.

## Where Mentorship Would Help

- Review whether the cohort and grouping rules answer a useful scientific question.
- Check the matching and outcome definitions for hidden sources of bias.
- Advise on confidence intervals, calibration, and comparison across distinct tests.
- Help design later temporal validation without leaking future information.
- Challenge claims so that reports remain proportional to the evidence.

The most useful mentor response would identify one methodological weakness to fix
before scaling, rather than endorsing the current model score.
