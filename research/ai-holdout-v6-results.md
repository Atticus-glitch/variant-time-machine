# AI Holdout V6 Results

## Why V6 Exists

V5's 100-record test was encouraging, but it was too small to tell whether the balanced
result was a durable pattern or a fortunate sample. Expanding V5 itself would have been
invalid because most remaining cohort records were already in V5 training. V6 therefore
started over with a new partition and a precommitted 1,000-record test.

## Separation Before Training

- V6 test representatives: 1,000, selected from 1,000 connected older-gene groups
- V6 training records: 2,518
- Connected companions quarantined: 4,672
- Records in prior V4/V5 test groups excluded from V6: 628
- Train/test Variation ID overlap: 0
- Train/test connected-group overlap: 0
- V6 train or test overlap with prior test groups: 0

Selection used hashes of group keys and Variation IDs, not labels or predictions. The
model was saved before the test metrics were calculated. Source, configuration,
partition-manifest, and model hashes are recorded with the ignored binary artifacts.

## Frozen Result

| Metric | Result |
| --- | ---: |
| Test records | 1,000 |
| Accuracy | 75.6% |
| Accuracy 95% Wilson interval | 72.8%-78.2% |
| Balanced accuracy | 74.4% |
| Macro F1 | 72.9% |
| ROC AUC | 0.844 |
| Average precision | 0.725 |
| Brier score | 0.154 |

Pathogenic is the positive class. The test contained 689 benign-direction and 311
pathogenic-direction outcomes. The confusion matrix was `TN 535, FP 154, FN 90, TP
221`, giving 77.6% benign recall and 71.1% pathogenic recall.

## What I Learned From It

The larger result is less dramatic than V5's 100-record result, and that is exactly why
the experiment was worth running. V6 still exceeds majority and seeded-random baselines,
but it gives a more cautious estimate and exposes 244 cases for error review. The next
step is not to hide those errors behind another architecture. It is to understand them,
check calibration, and then test on a genuinely later untouched cohort.

## Boundary

V6 remains internal to the previously inspected, outcome-selected 2022-to-2024 V2
cohort. The current local source database has the same 8,818 cohort IDs but a different
byte hash from the source recorded by V4/V5; V6 freezes the current hash and does not
rewrite prior provenance. This is not independent temporal, clinical, or medical
validation and must not guide patient care.
