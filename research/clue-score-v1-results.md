# Clue Score V1 Results

Generated: 2026-07-28T22:16:18.389293+00:00

## Question

Can a small fixed score using only fields in the January 6, 2022 ClinVar
snapshot predict the direction of the January 4, 2024 aggregate classification?

## Data Sources And Dates

- Predictor snapshot: January 6, 2022 archived `variant_summary`.
- Answer snapshot: January 4, 2024 archived `variant_summary`.
- Exact older eligibility: `Uncertain significance`.
- This is a two-snapshot comparison. It does not establish the exact date of change.

## Frozen Formula And Thresholds

The permanent formula is `config/clue_score_v1.yaml` with SHA-256
`2ee751040aa9c86ebe8645c0e02b1cca51d9d9b7d3a4cbdc4675819f10c50d3c`. Its provisional weights were frozen before full
outcome evaluation. Scores of +3 or higher predict pathogenic direction, -2 or
lower predict benign direction, -1 through +2 predict remaining uncertain, and
records without a directional clue receive no prediction.

## Actual Results

- Eligible older VUS records: 439,409
- Predictions made: 421,578
- Correct: 298,090
- Wrong: 70,053
- No prediction: 17,831
- Not scorable: 65,175
- Accuracy among correct/wrong results: 81.0%
- Balanced accuracy: 47.5%
- Pathogenic-direction precision: 1.3%
- Benign-direction precision: 16.1%
- Uncertain-outcome recall: 80.8%
- No-prediction rate: 4.1%

## Runtime And Storage

- Core full-run runtime: 336.54 seconds
- Final indexed result database: 1,891,164,160 bytes
- Generated output bundle: 3,448,775,132 bytes
- Filesystem space free after final validation: 50,759,442,432 bytes

## Confusion Matrix

See `confusion_matrix.csv`. Rows are normalized actual outcomes and columns are
prediction directions. Unscorable newer categories are excluded rather than forced
into a direction.

## Common Clues And Failures

The clue appearing in the largest number of correct predictions was `criteria_without_conflict`.
This descriptive count does not prove that the clue caused correctness. Wrong
predictions can reflect weak HGVS consequence inference, aggregate condition
differences, and provisional review-status points. Exact counts are in
`metric_summary.json`.

## Limitations

- This is an exploratory rule-based baseline, not a medical prediction tool.
- The summary file lacks modern consequence annotations, population frequency,
  conservation, functional evidence, and submission-level evidence.
- Exact Variation ID and Allele ID equality is required; unsafe scope is not scorable.
- Aggregate classifications may combine conditions and submitters differently over time.
- Snapshot dates and `LastEvaluated` are separate and neither necessarily identifies
  the exact change date.
- Weights were not optimized and performance is not clinical validity.

## Next Experiment

Manually review stratified correct, wrong, no-prediction, and unscorable records. A
future Version 2 may test independently dated annotations or revised rules, but must
keep Version 1 unchanged and use separate validation.
