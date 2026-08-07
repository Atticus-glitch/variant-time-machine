# V9.1 mentor summary

## What changed

Original V9 trained only on 1,000 already opened V8 records and shifted toward pathogenic calls, causing 113 false positives. V9.1 retained the same 64 authenticated historical features but augmented each outer training partition with the 9,818-record V8 development matrix. It nested model-family, configuration, calibration, and threshold selection within component-disjoint outer folds.

## What worked

- Fully nested component-weighted balanced accuracy increased from original V9's 0.8735 to 0.8939.
- Pathogenic recall increased from 0.8548 to 0.8978.
- The confusion matrix improved from `701/113/27/159` to `708/106/19/167` for `TN/FP/FN/TP`.
- The model-search and publication path now authenticates its trial manifest, direct sources, frozen folds, eligible protocol, implementations, and output hashes.

## What did not resolve

- The paired interval against original V9 crossed zero: `[-0.0043, 0.0464]`.
- V9.1 did not fairly beat sealed V8; it had lower accuracy, macro F1, benign recall, and calibration quality on the same opened records.
- No human reviews were completed, so clean and strict-clean cohorts remain empty.
- No untouched final cohort exists. The full-development ExtraTrees artifact therefore has no final-test metric.

## Decision

Publish V9.1 as an authenticated, nonofficial internal-development candidate. Do not call it an official V9.1 model, a V8 replacement, clinically validated, or deployable. The next scientifically decisive step is an untouched temporal, component-disjoint cohort or completed human review that yields a genuinely clean evaluation set.
