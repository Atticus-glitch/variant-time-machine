# Clue Score V1 Development Validation

Date: 2026-07-28

## Frozen Boundary

`config/clue_score_v1.yaml` was frozen before this run. Its SHA-256 was `2ee751040aa9c86ebe8645c0e02b1cca51d9d9b7d3a4cbdc4675819f10c50d3c`. The development run scored a deterministic 500-record sample from the 439,409 exact older VUS records. All predictions were committed before the runner queried newer outcomes.

No Version 1 point or threshold was changed after inspecting these results.

## Development Results

- Eligible sampled records: 500
- Predictions made: 479
- No prediction: 21
- Correct: 348
- Wrong: 71
- Not scorable: 76
- Accuracy among correct/wrong results: 83.1%
- Balanced accuracy: 77.5%
- Pathogenic-direction precision: 5.2%
- Benign-direction precision: 18.8%
- Uncertain-outcome recall: 82.4%
- Runtime: 2.42 seconds

The high overall accuracy is strongly influenced by the many records that remained uncertain. Directional precision is weak, especially for pathogenic and benign predictions. This is an important baseline finding, not a reason to tune Version 1 on the same answer key.

## Manual Calculation Inspection

Ten correct records were opened and checked: Variation IDs 3390, 57089, 128351, 143606, 156625, 157779, 166254, 179273, 201308, and 203003. Their displayed point sums, thresholds, normalized outcomes, and `Correct` labels agreed with the frozen rules.

Ten wrong records were opened and checked: Variation IDs 141370, 141911, 184899, 206393, 216563, 223343, 230736, 291215, 294605, and 295759. Their arithmetic was correct. Common failures were missense plus multiple-submitter criteria reaching the +3 pathogenic threshold while the newer record remained uncertain, and synonymous evidence predicting benign while the record remained uncertain.

Ten no-prediction or unsafe records were opened and checked: Variation IDs 153235, 154389, 393600, 395295, 398685, 399226, 400380, 400921, 402075, and 441673. They had no recognized directional clue or unsafe non-germline/structural scope. Their zero scores, warnings, and no-prediction or not-scorable labels were consistent.

Ten unscorable or ambiguous records were opened and checked: Variation IDs 3931, 52004, 93838, 153235, 161710, 186594, 191138, 191679, 221107, and 234126. They were kept out of red/green correctness counts because the newer classification conflicted or cross-snapshot scope was unsafe.

## Validation Decision

The software calculations, leakage boundary, strict outcome normalization, and result labels behaved as specified on the development sample. The weak directional precision is preserved honestly. The frozen formula may proceed to the full eligible baseline without tuning.
