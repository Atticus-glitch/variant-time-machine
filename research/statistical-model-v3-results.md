# Statistical Model V3 Results

Generated: 2026-07-30T00:31:54.765091+00:00

## Design

Logistic regression learned all clue coefficients from 6,933 training records. A
deterministic connected-gene SHA-256 split kept 1,885 records held out until this
evaluation. Model inputs are only binary older-snapshot clue indicators; assigned
points, scores, predictions, newer fields, and outcomes were not model features.

The train and test partitions share zero Variation IDs and zero connected gene groups.
The frozen source database SHA-256 is
`bb66cc4e2e682300251180f3eda89e27828b5b80dd91abd02a2758653913c97b` and the
partition manifest SHA-256 is
`97a05bb25ac83e18973665ac110b5f40ce3035b906f5cffb772b843ef03bcb9f`.

## Held-Out Results

- Accuracy: 58.2%
- Balanced accuracy: 70.6%
- Pathogenic precision: 35.8%
- Benign precision: 96.3%
- Pathogenic recall: 94.2%
- Benign recall: 47.0%
- ROC AUC: 0.788
- Pathogenic average precision: 0.546
- Brier score: 0.171

The test set contained 450 pathogenic and 1,435 benign outcomes. The model correctly
predicted 424 pathogenic and 674 benign outcomes. It predicted 761 benign outcomes as
pathogenic and 26 pathogenic outcomes as benign.

## Learned Coefficients

Positive coefficients point toward pathogenic resolution and negative coefficients
point toward benign resolution, conditional on the other included indicators.

- `synonymous_consequence`: -5.4139 (odds ratio 0.004)
- `noncoding_consequence`: -3.2642 (odds ratio 0.038)
- `loss_of_function_consequence`: +2.2283 (odds ratio 9.284)
- `canonical_splice_consequence`: +1.9128 (odds ratio 6.772)
- `missense_consequence`: -1.6661 (odds ratio 0.189)
- `expert_panel_review`: +1.1056 (odds ratio 3.021)
- `multiple_agreeing_submitters`: -0.2686 (odds ratio 0.764)
- `criteria_without_conflict`: +0.1366 (odds ratio 1.146)
- `conflict_warning`: +0.0000 (odds ratio 1.000)

## Limitation

This is a conditional internal holdout from the already inspected Version 2 cohort.
It does not predict whether a VUS will resolve and is not independent temporal,
clinical, or medical validation. The held-out result was not used to retune features,
partitioning, regularization, class weighting, or the decision threshold.
