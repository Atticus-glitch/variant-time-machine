# AI Temporal V8 Preregistration

## Purpose

V8 asks whether a model trained on previously opened records can predict the direction
of later reclassification for 1,000 January 2024 VUS records whose Variation IDs and
complete predictor-time gene components are absent from development.

This protocol was frozen and its label-vault commitment was pushed before V8 feature
code, model selection, training, or prediction. The July 2026 archive had already been
used for V7, so V8 is a membership-hidden retrospective test, not a never-opened future
archive.

## Development Ledger

- 8,818 opened 2022-to-2024 V2 records
- 1,000 opened V7 temporal records
- Duplicate Variation IDs are forbidden.
- Gene symbols are used only for connected-component isolation and grouped validation,
  never as model inputs.

## Sealed Test

1. Begin with January 2024 exact germline VUS records absent from January 2022.
2. Exclude every V7 final-test ID.
3. Normalize predictor-time gene symbols with the frozen NFKC/uppercase rule.
4. Connect all candidate records that share any gene token.
5. Exclude every component touching any V2 or V7 development gene.
6. Exclude records without a usable gene token.
7. Require exact Variation ID, unchanged complete Allele ID set, exclusively germline
   July 2026 scope, and one clear benign- or pathogenic-direction aggregate outcome.
8. Hash-rank eligible records with the frozen salt and seal exactly 1,000 without class
   balancing or prediction access.

The resulting pool contained 1,491 safe records in 728 components. The test contains
1,000 records, so records are not independent one-per-gene samples. Uncertainty will be
bootstrapped by sealed gene component.

Public commitment:
`outputs/evaluations/frozen/v8_vault_commitment.json`

## Features

Only fields available in the applicable predictor snapshot may be used. The frozen
feature bundles are:

- consequence and variant type;
- review strength, criteria, conflict, submitter count, and evaluation age;
- RCV count, source-row count, assembly count, coordinate span, and missingness;
- missense amino-acid chemistry from static predictor-independent tables.

Variation ID, gene identity, absolute coordinate, condition/RCV identity, newer fields,
prior model predictions, and prior correctness are forbidden. The same transformer must
be applied to 2022 and 2024 records.

## Model Selection

- Five outer and four inner connected-gene-group folds
- Equal total weight per development component
- Candidate families limited to frozen elastic-net logistic and shallow histogram
  gradient-boosting grids
- Primary selection metric: balanced accuracy
- Within 0.005 balanced accuracy, prefer the simpler model
- Platt calibration on grouped out-of-fold logits only
- Threshold selected on component-weighted out-of-fold predictions by the frozen rule

## Final Evaluation

Primary metric: balanced accuracy.

Required secondary reporting:

- accuracy and majority baseline;
- benign and pathogenic recall;
- macro F1;
- ROC AUC and average precision;
- Brier score and fixed-bin calibration;
- confusion matrix and class prevalence;
- overall and missense-only results;
- 10,000 component-bootstrap confidence intervals;
- paired comparison with frozen V7 predictions on the same V8 records.

The model and all candidate predictions must be hashed before the vault is opened. One
evaluation is allowed. A poor result is still the result. A model-affecting bug ends V8
and any corrected run must receive a new version while preserving V8.

## Claim Boundary

V8 can support gene-component-disjoint evidence within this project's labeled
development ledger. It cannot establish biological independence between different
genes, predict whether a VUS resolves, provide condition-specific truth, or support
clinical use.
