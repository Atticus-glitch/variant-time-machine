# V9 Model Selection Plan

## Status

**Frozen planning document: 2026-08-02. No final V9 model exists.**

This plan must be frozen before any final-test labels are accessed. It authorizes no
final-test evaluation today. Dataset preparation exists, but review adjudication and
candidate fitting are incomplete.

## Research Question

Can an older-snapshot model improve balanced discrimination of later benign-direction
versus pathogenic-direction aggregate outcomes under stricter review, temporal
separation, and connected-gene-component isolation than the current development
process? The task remains conditional on records that later have a clear aggregate
direction; it does not predict whether an unresolved record will resolve.

## Review Gate

No official V9 candidate fitting may begin until all V8 false negatives, all
high-confidence V8 false positives, at least 25 true negatives, and at least 25 true
positives have completed schema-valid manual reviews. Every V8/V7 disagreement must be
reviewed or remain explicitly queued with status, and exclusion-reason counts must be
reported. Uncertain or expert-needed decisions do not count as clean approval.

Passing the numerical gate does not permit silent edits. Originals remain immutable;
accepted corrections and exclusions are applied only while producing a new versioned
development dataset linked to review IDs. The current completed-review count is 0, so
the gate has not passed.

## Dataset Freeze

Before model work, publish a manifest containing source paths and hashes, snapshot
dates, inclusion and exclusion rules, accepted review IDs, correction policy, duplicate
checks, class counts, component counts, and a dataset hash. Any data-affecting change
creates a new dataset version and invalidates downstream candidate results.

## Grouped Development Splits

- Group records by connected components formed from normalized predictor-time gene
  tokens. A record with multiple tokens joins their components transitively.
- Keep every component in exactly one fold. Do not split a component between training,
  calibration, threshold selection, validation, or final test.
- Use nested grouped cross-validation for candidate and hyperparameter selection.
- Report record-weighted and component-weighted metrics; use component-weighted
  balanced accuracy as the primary ranking value.
- Freeze fold membership and its hash before candidate fitting.
- Treat gene-less records by a frozen rule before splitting; do not place them ad hoc
  after outcomes are inspected.

## Leakage Guardrails

- Features must be demonstrably available at the predictor snapshot.
- Forbid Variation ID, gene identity, absolute coordinate, condition or RCV identity,
  answer-snapshot fields, later review data, prior correctness, manual-review decisions,
  and manual corrections as model inputs.
- Manual review may decide dataset eligibility or correct a development label, but its
  text, decision, and correction type are not predictive features.
- Fit preprocessing, missing-value handling, encoding, weighting, calibration, and
  threshold selection inside the applicable grouped training partitions.
- Never use a final-test label for feature design, candidate ranking, calibration,
  threshold choice, error analysis, or stopping decisions.
- Run automated overlap checks for Variation IDs and connected gene components across
  every partition and record the results in the freeze manifest.

## Candidate Families

Evaluate a small frozen set rather than an open-ended search:

1. Elastic-net logistic regression.
2. Calibrated histogram gradient boosting.
3. Random forest or ExtraTrees.
4. Clue-score baseline where available.
5. Consequence-only baseline.
6. Majority-direction baseline.
7. Frozen V8 evaluated on the same records where possible.

Hyperparameter grids, random seeds, weighting, calibration choices, and threshold grids
must be fixed in the dataset/model preregistration before fitting. Adding a family after
seeing grouped validation results starts a new plan version.

## Candidate Ranking Rules

1. Reject any candidate that fails the leakage audit.
2. Rank remaining candidates by grouped-validation balanced accuracy.
3. Break close results by validation macro F1, then pathogenic-direction recall.
4. Next prefer calibration quality and stability under component bootstrap.
5. Next prefer interpretability; if performance is similar, prefer the simpler model.
6. Within one family, prefer fewer active features or stronger regularization, then the
   lexicographically first frozen hyperparameter identifier.
7. A candidate is ineligible if any fold fails, any leakage or overlap check fails, its
   predictions are incomplete, or its calibration/threshold procedure used its
   evaluation fold labels outside the preregistered nested procedure.
8. Report all candidates, including failed and losing candidates. Do not select from a
   secondary subgroup result.

## Calibration And Threshold

Calibration and threshold selection use only grouped out-of-fold predictions generated
inside development. The exact calibrator and threshold grid must be frozen before
candidate fitting. Tied thresholds choose the value closest to 0.5 and then the lower
value. Report the uncalibrated 0.5 result as a sensitivity analysis, not as a replacement
selected after inspection.

## Final-Test Guardrails

- Select one complete pipeline before final-test access.
- Hash the dataset manifest, code revision, environment, fitted pipeline, threshold,
  final-test membership commitment, and every final-test prediction before labels are
  opened.
- The final test must be temporally later and untouched, with zero Variation ID and zero
  predictor-time connected-gene-component overlap with all development data and prior
  opened tests.
- Permit one evaluation. Preserve all predictions and outputs regardless of result.
- Do not tune, retrain, relabel, or substitute a model after opening the final test.
- A model-affecting or label-affecting defect invalidates V9; a corrected attempt gets a
  new version and a new untouched final test.
- Do not call any candidate the final V9 before these conditions are satisfied.

## Reporting

The preregistered primary metric is component-weighted balanced accuracy. Also report
record-weighted balanced accuracy, accuracy and majority baseline, per-class recall,
macro F1, ROC AUC, average precision, Brier score, fixed-bin calibration, confusion
matrix, prevalence, component counts, and 10,000 component-bootstrap intervals. Label
subgroup analyses as secondary and report their denominators.

## Stop Conditions

Stop before fitting if the review gate, provenance checks, dataset accounting, or
grouped split checks fail. Stop before final evaluation if any artifact is unfrozen or
any final membership or label was accessed. A weak or negative valid final result is
reported unchanged.

## Current Decision

There is no selected V9 candidate, no trained final V9 pipeline, no V9 prediction
commitment, and no valid V9 final-test result. V8 remains the latest completed model
evaluation while this plan is pending.
