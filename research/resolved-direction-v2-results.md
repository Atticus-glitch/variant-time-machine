# Resolved Direction V2 Results

Generated: 2026-07-29T19:43:48.980242+00:00

## Conditional Question

Among safely matched variants that were exactly uncertain in the January 6, 2022
snapshot and had become clearly pathogenic or benign by the January 4, 2024 snapshot,
which direction does the older-only frozen score predict?

This experiment does not predict whether a VUS will become certain. Cohort membership
uses the later answer snapshot, while the score itself remains based only on 2022.

## Frozen Binary Rule

- Score +1 or higher: pathogenic direction
- Score -1 or lower: benign direction
- Score 0: no prediction
- `remain_uncertain` is not an allowed prediction

## Actual Results

- Resolved directional cohort: 8,818
- Actual pathogenic direction: 2,531
- Actual benign direction: 6,287
- Predictions made: 7,859
- Correct: 4,595
- Wrong: 3,264
- No prediction: 959
- Accuracy: 58.5%
- Balanced accuracy: 65.1%
- Pathogenic precision: 42.7%
- Benign precision: 99.1%
- Pathogenic recall: 95.5%
- Benign recall: 34.6%

## Limitation

Version 2 was designed after reviewing Version 1 aggregate results and uses the same
2024 answer snapshot. It is exploratory, not independent validation, not a prediction
of whether resolution occurs, and not a medical tool.
