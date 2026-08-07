# V9.1 Improvement Plan

**Status: frozen internal-validation plan written before V9.1 training.**

## Purpose

I will diagnose and improve the original V9 pipeline without altering V8, original V9,
labels, or cohort membership. Because no untouched later component-disjoint cohort exists,
this pass can select only a **V9.1 internal-development candidate**. It cannot produce an
official final V9.1 test result.

## Allowed Data

- The 1,000 authenticated rows in `data/processed/v9/v9_messy_dataset.csv`, relabeled
  `v9_1_all_eligible_dataset.csv` without changing outcomes.
- The authenticated 9,818-record V8 development matrix reconstructed from the frozen V8
  development database, historical predictor index, and opened V7 predictions. The V8
  protocol audited zero component overlap between these records and all 1,000 V8/V9 rows.
- Only the 64 authenticated predictor-time `feature__*` columns derived from the January
  2024 snapshot.
- `component_hash` for grouping, weighting, overlap checks, and bootstrap only.
- Variation ID for joins and audit only.
- Frozen V8, V7, and original V9 predictions for same-record comparison only, never as
  model inputs or selection features.
- Human review fields only for lossless dataset accounting and secondary subset reporting.

## Forbidden Data

- Newer classification, newer review status, newer LastEvaluated, newer submitter count,
  current API values, later condition text, resolved direction, or any answer-derived
  field as a predictor.
- `dataset_outcome`, `original_automatic_outcome`, label source, V8/V7 predictions,
  probability, correctness, confusion group, automatic review flags, AI suggestions,
  manual decisions, corrections, and exclusion reasons as predictors.
- Gene, component identity, coordinates, RCV identity, and condition identity as model
  inputs.
- Any feature whose January 2024 provenance cannot be authenticated.

## Target

The target remains the unchanged original automatic later aggregate direction:
`moved_toward_benign` or `moved_toward_pathogenic`. This is conditional retrospective
direction classification among old VUS records known to have a later directional label.
It is not prediction of whether a VUS will resolve and is not a clinical endpoint.

## Dataset States

- **All eligible:** all 1,000 authenticated V8 rows with warnings preserved.
- **Clean reviewed:** only rows explicitly accepted by completed human review. With the
  current ledger this is expected to contain zero rows.
- **Strict clean:** accepted reviewed rows that also have high match confidence, clear
  germline/comparable scope, complete core fields, and no unresolved severe ambiguity.
- **Ambiguous:** all review-pending, scope-ambiguous, label-problem, expert-needed, or
  severe-warning rows not eligible for clean claims.
- **Excluded:** only explicit scientific exclusions with recorded reasons. Pending review
  is not an exclusion.

Every source row must remain represented in all-eligible and exactly one current review
state. No AI suggestion can become a human decision automatically.

## Feature Sets

1. Consequence and variant-type features only.
2. Old ClinVar review/evidence metadata only.
3. Consequence plus metadata.
4. Consequence, metadata, and completeness/count/HGVS flags.
5. All 64 allowed non-leaky features.
6. All allowed features without gene identity; currently identical to set 5 because gene
   identity is already forbidden.
7. Gene identity candidate: declared ineligible and not fit because component-disjoint
   folds make fold-local identities unseen and fold-global encoding would leak.

Zero-variance handling, scaling, and any learned transformation must occur inside training
partitions. Feature sets are fixed in `config/v9_1.json`.

## Candidate Models

The fixed modest search includes:

1. Elastic-net logistic regression, uncalibrated.
2. Platt-calibrated elastic-net logistic regression.
3. Histogram gradient boosting, uncalibrated.
4. Platt-calibrated histogram gradient boosting.
5. Random forest.
6. ExtraTrees.
7. Platt-calibrated linear SVM.
8. A small standardized MLP with early stopping.
9. Frozen Clue Score V1 coverage baseline.
10. Consequence-only baseline.
11. Majority baseline.

The exact curated configurations, seeds, 100-tree budget, early-stopping rule, weighting
variants, calibrator, and threshold grid are fixed in `config/v9_1.json`. The first
pre-result trial was stopped after exceeding one hour without publishing metrics; the
curated budget preserves every family and scientific safeguard while removing redundant
Cartesian combinations. Candidate failures remain visible.

## Validation Strategy

- Reuse the original V9 five outer component-grouped folds for direct same-record
  diagnosis and to avoid choosing a favorable new split.
- Compare two frozen training regimes: the original V9-style regime using only the outer
  training rows, and the primary augmented regime adding all 9,818 prior V8 development
  records to every outer and inner fit. The held-out outer V9 fold is never added to
  training. This directly tests the training-size diagnosis.
- Within each outer training partition, use four stratified component-grouped folds for
  feature-set/configuration selection, optional Platt calibration, and threshold choice.
- Fit preprocessing only on the applicable training partition.
- Require every row to receive exactly one outer OOF prediction and every component to
  remain in one outer fold.
- Report the five outer-fold values and overall OOF metrics.
- Use all-eligible data plus the frozen prior V8 development matrix for the augmented
  regime because reviewed clean data is empty. Clean and strict-clean metrics remain
  unavailable rather than fabricated.

## Final Test Rules

No final test is available. V9.1 development must set:

- `official_v9_1_model: false`;
- `final_test_available: false`;
- `final_test_evaluated: false`;
- `test_records: 0`.

A future final test must be temporally later, untouched, and have zero Variation-ID and
zero connected-component overlap with every prior development and opened test cohort. A
model, threshold, feature schema, membership commitment, and predictions must be sealed
before labels are opened. There may be one evaluation and no tuning afterward.

## Selection Metric And Tie Breaks

1. Reject any leakage, overlap, incomplete-prediction, or fold failure.
2. Rank by component-weighted validation balanced accuracy.
3. Treat candidates within 0.005 as close; among them prefer higher macro F1.
4. Then prefer higher pathogenic-direction recall.
5. Then prefer lower Brier score where probabilities are available.
6. Then prefer narrower/well-centered component-bootstrap behavior and lower fold spread.
7. Then prefer interpretability.
8. If still close, prefer the simpler model and lexicographically first frozen ID.

Raw accuracy is never the selection metric.

## Threshold Selection

- Choose the operating threshold only from inner grouped OOF predictions inside each
  outer training partition.
- Optimize component-weighted balanced accuracy on the fixed 0.10 to 0.90 grid.
- Break ties by closest to 0.5 and then lower threshold.
- Also report, but do not select as the primary operating point, the threshold with the
  best pathogenic recall subject to component-weighted balanced accuracy no more than
  0.02 below the inner optimum.
- Never tune a threshold from outer OOF aggregate results or final-test labels.

## Calibration

Calibrated variants use Platt logistic calibration fit only on grouped inner OOF logits.
Uncalibrated variants remain separate candidates. Report Brier score, log loss, ten fixed
probability bins, and observed versus predicted pathogenic fractions.

## Bootstrap

Use 10,000 paired component bootstrap replicates on fixed outer OOF predictions. Report
95% intervals for accuracy, component-weighted balanced accuracy, macro F1, benign recall,
and pathogenic recall for the selected development candidate and major baselines. State
that these intervals omit full model-selection uncertainty.

## Same-Record Comparisons

Compare on the same 1,000 records against original V9, frozen V8, frozen V7 where joined,
consequence-only, and majority. Report transition counts and paired intervals. V8 was
evaluated while sealed and V9.1 was developed after labels were opened, so even a favorable
V9.1 point estimate is not symmetric evidence of temporal superiority.

## Naming Rule

The selected internal candidate may be called **V9.1 development candidate**. It is an
improvement over original V9 only if its point estimate is higher under the frozen primary
metric; a clear improvement requires the paired 95% interval versus original V9 to remain
above zero. It fairly beats V8 only after an equivalent untouched final evaluation, which
is impossible in the current repository.

## Leakage And Self-Deception Checks

The run must fail or warn when:

- any forbidden or non-allowlisted predictor enters the matrix;
- an outer-validation label reaches fitting, calibration, configuration, or threshold
  selection;
- any component crosses an outer or inner fold;
- source labels differ from the immutable originals;
- exclusion accounting disproportionately removes V8 errors without a warning;
- clean or strict datasets are too small;
- gene identity is requested as a predictor;
- accuracy is reported without balanced accuracy;
- a same-record comparison is missing;
- “better” appears without a fair-comparison qualification;
- clinical-use language appears;
- a final result is requested while the final-test gate is false;
- raw archives, databases, caches, credentials, or environment directories are staged.

## Required Reporting

Publish every feature-set and candidate result, including failures and losing models;
threshold selections; calibration bins; fold values; bootstrap intervals; all/clean/strict
and ambiguous counts; same-record comparisons; source and output hashes; environment;
limitations; and the strongest truthful claim. Weak or negative results must remain
unchanged.
