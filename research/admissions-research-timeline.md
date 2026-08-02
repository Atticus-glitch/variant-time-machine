# Admissions Research Timeline

This timeline uses the dates recorded in the research notebook. It separates completed
work from proposed next steps and does not claim publication or medical validation.

## Data Dates

- **2022-01-06:** Fixed older ClinVar `variant_summary` predictor snapshot.
- **2024-01-04:** Fixed newer ClinVar `variant_summary` answer snapshot.
- **2024-01-29:** Documented schema expansion occurred after both selected snapshots.

## Work Timeline

- **2026-07-26:** Created the repository structure, initial research question,
  documentation, and synthetic tests. Researched ClinVar archives and provisionally
  selected the January 6, 2022 and January 4, 2024 releases.
- **2026-07-26:** Built the historical pipeline foundation, first live ClinVar
  connection, and conservative historical comparison workflow.
- **2026-07-26:** Investigated bounded XML retrieval, then paused the roughly 7.89 GB
  archive pair. Adopted a small-pilot strategy, 500 MB large-download protection, and
  bounded official API requests.
- **2026-07-26:** Created the first pilot-variant workflow and browser pilot workspace,
  while keeping unverified historical fields empty.
- **2026-07-27:** Implemented bounded VCV version-history retrieval with strict request
  and response limits. Recorded the first real three-record descriptive pilot; it was
  not evidence of future prediction.
- **2026-07-28:** Froze and ran Clue Score V1. The full baseline reached 81.0% raw
  accuracy but 47.5% balanced accuracy, showing that the dominant unresolved class
  made raw accuracy misleading.
- **2026-07-29:** Defined Resolved Direction V2 for variants known to have a clear 2024
  outcome. It reached 58.5% accuracy and 65.1% balanced accuracy and remained
  exploratory.
- **2026-07-29:** Froze Statistical Model V3, a logistic regression using nine
  older-only binary indicators and connected-gene group splitting.
- **2026-07-30:** Opened the V3 internal holdout: 1,885 records, 58.2% accuracy, and
  70.6% balanced accuracy. This was not independent validation. The original V3 source
  database hash is no longer present locally and should not be reconstructed or guessed.
- **2026-07-31:** Froze V4, selected 100 hidden records by connected group, trained on
  8,325 records, and saved the model before opening the test.
- **2026-08-01:** Tested V4 once: n=100, 76% accuracy, 62.5% balanced accuracy, TN 68,
  FP 0, FN 24, TP 8.
- **2026-08-01:** Froze and trained V5 after the aggregate V4 result was known. V5 used
  14 older-only inputs, training-only balancing, scaling, and hidden layers of 32 and
  16 units. Its 100 test records used groups distinct from V4's.
- **2026-08-01:** Tested V5 once: n=100, 82% accuracy, 82.1978% balanced accuracy,
  TN 53, FP 12, FN 6, TP 29. V5 appeared more balanced, but the two distinct small
  tests did not establish a stable winner.
- **2026-08-01:** Froze V6 around 1,000 new connected-group representatives before
  fitting. V6 excluded all prior test groups, trained on 2,518 records, and recorded
  zero train/test ID or group overlap.
- **2026-08-01:** Tested V6 once: n=1,000, 75.6% accuracy, 74.4% balanced accuracy,
  TN 535, FP 154, FN 90, TP 221. The larger result was more modest than V5's small-test
  point estimate and made the limits of the earlier comparison clearer.
- **2026-08-02:** Sealed 761,235 January 2024 candidate predictions before downloading
  the July 2026 answer archive. V7 then scored 78.5% accuracy and 79.1% balanced
  accuracy on 1,000 new Variation IDs, with 80% pathogenic recall.

## Proposed Work

- **Next stage:** Review V7's missense errors and probability calibration without
  feeding July 2026 test answers back into V7.
- **Longer-term need:** Evaluate on a genuinely later untouched snapshot for
  independent temporal evidence.

## Planning Milestones

These dates are planning targets, not scientific claims:

- **August 3, 2026:** Freeze current V4/V5 results.
- **August 7, 2026:** Complete leakage audit.
- **August 10, 2026:** Complete and preserve the 1,000-record V6 internal test.
- **August 14, 2026:** Complete error analysis.
- **August 26, 2026:** Finish one-page abstract.
- **August 31, 2026:** Email 10 mentors.
- **September 20, 2026:** Clean public GitHub/dashboard.
- **September 25, 2026:** Poster draft complete.
- **September 30, 2026:** Manually review 50 predictions.
- **October 12, 2026:** MIT essay drafts complete.
- **October 17, 2026:** Research supplement draft complete.
- **October 22, 2026:** Freeze project v1.0.
- **October 31, 2026:** Submit MIT Early Action early.
- **November 5, 2026:** Regeneron STS deadline, if submitting.

All V3, V4, and V5 results described here are internal to a conditional 2022-to-2024
cohort. They are not independent, clinical, or medical validation. The repository is
configured with a GitHub remote, but this timeline makes no claim about public access.
