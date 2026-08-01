# AI Holdout V4 Results

Tested: 2026-08-01T20:43:37.195915+00:00

- Hidden records: 100
- Correct: 76
- Wrong: 24
- Accuracy: 76.0%
- Balanced accuracy: 62.5%
- Actual benign: 68
- Actual pathogenic: 32
- Benign recall: 100.0% (68 of 68)
- Pathogenic recall: 25.0% (8 of 32)

The headline accuracy is inflated by the larger benign class. V4 predicted all benign
records correctly but missed 24 of 32 pathogenic outcomes. The result is preserved and
will not be used to retrain V4. V5 uses a fresh holdout disjoint from every V4 test
group.

This remains an internal test from the outcome-selected 2022-to-2024 cohort, not
independent temporal or clinical validation.
