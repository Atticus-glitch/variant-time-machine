# V9 Exploratory Training Report

## Status

I trained exploratory candidates on 1,000 previously opened V8 records grouped into 559
connected components. I did not name an official V9 winner and did not evaluate a final
test set. The human-review gate is still incomplete: all 1,000 records are pending and
the clean reviewed dataset has zero rows.

## Protocol

I fixed the candidate grid for this run in `config/v9_exploratory.json`. I used five
outer grouped folds for evaluation and four inner grouped folds for configuration,
calibration, and threshold selection. Related records stayed in one outer fold, and each
component received equal total weight. All 64 predictors came from the authenticated
`feature__*` allowlist. No candidate failed.

## Results

| Candidate | Component-weighted balanced accuracy | Macro F1 | Pathogenic recall | Brier score |
| --- | ---: | ---: | ---: | ---: |
| Frozen V8 reference | 88.22% | 84.04% | 83.33% | 0.0633 |
| Elastic-net logistic | 87.35% | 80.18% | 85.48% | 0.0687 |
| Histogram gradient boosting | 86.17% | 81.13% | 84.95% | 0.0707 |
| ExtraTrees | 85.70% | 78.13% | 86.56% | 0.0638 |
| Consequence only | 84.29% | 75.09% | 87.63% | 0.1910 |
| Majority | 50.00% | 44.87% | 0.00% | 0.1860 |

Elastic net led the new candidate families. Frozen V8 remained the strongest same-record
reference at the point estimate. In 10,000 component bootstrap replicates, the interval
for elastic net minus V8 component-weighted balanced accuracy was -3.35 to +1.74
percentage points. Because this crosses zero, I do not claim a clear difference or an
improvement.

Clue Score V1 covered 450 records and abstained on 550. It was correct on 446 covered
records, but its directional thresholds selected that subset. Its covered-record score
is not comparable to candidates that made 1,000 predictions.

## Interpretation

The new models generally found more pathogenic outcomes but produced many more false
positives. Elastic net changed V8's 31 FN and 74 FP to 27 FN and 113 FP. That tradeoff
lowered accuracy, macro F1, and calibration quality even though pathogenic recall rose.

This comparison is not symmetric. Frozen V8 was evaluated while sealed, but the new
candidates were developed through folds sampled from labels that had already been opened
during V8 analysis. The bootstrap also conditions on fixed out-of-fold predictions and
does not reproduce every model-selection decision. These results can guide future work,
but they cannot validate V9.

## Reproducibility

The run manifest records the data, configuration, Clue Score configuration, fold, source
implementation, environment, and output hashes. The generated fold assignments,
candidate metrics, out-of-fold predictions, calibration bins, nested selections,
bootstrap intervals, and failure ledger are in `outputs/v9_exploratory/`.

## Next Gate

I need completed human review and a rebuilt clean dataset before any official model
selection. A final evaluation also requires a later untouched component-disjoint cohort.
Until then, `official_v9_winner` stays `null` and `final_test_evaluated` stays false.
