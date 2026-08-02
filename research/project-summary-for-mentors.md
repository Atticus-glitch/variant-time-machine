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
baselines, logistic regression, three frozen neural-network holdouts, and a sealed
record-level temporal evaluation.
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

Pathogenic is the positive class. Every test uses distinct connected groups. V6's
1,000 records and their groups were excluded before V6 fitting, as were all prior test
groups. V5 has the highest point score on its own test, while V6 has the strongest
sample-size evidence and a more modest estimate. Different cohorts and training sets
prevent a head-to-head winner claim.

V7 moves the predictor to January 2024 and the answer to July 2026. Candidate
predictions were hashed before the answer download, and test IDs had zero development
overlap. V7 is the strongest current evidence, although 69.9% of test records shared a
gene with development and the test remains conditional on clear resolution.

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

## Proposed Next Step

Review a predeclared sample of V7's 215 errors, especially the 186 missense mistakes,
and assess middle-range calibration. Any changed model must wait for another sealed
future answer snapshot rather than reusing July 2026 as a test.

## Where Mentorship Would Help

- Review whether the cohort and grouping rules answer a useful scientific question.
- Check the matching and outcome definitions for hidden sources of bias.
- Advise on confidence intervals, calibration, and comparison across distinct tests.
- Help design later temporal validation without leaking future information.
- Challenge claims so that reports remain proportional to the evidence.

The most useful mentor response would identify one methodological weakness to fix
before scaling, rather than endorsing the current model score.
