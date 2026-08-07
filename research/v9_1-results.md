# V9.1 internal-development results

## Status

V9.1 is a selected internal-development procedure, not an official model and not a final evaluation. No clean reviewed records, strict-clean records, or untouched component-disjoint final cohort were available. All 1,000 labels had already been opened during V8 analysis.

## Protocol

- Evaluation used five outer component-disjoint folds over 1,000 records and 559 components.
- Each outer training partition was augmented with the authenticated 9,818-record V8 development matrix covering 1,792 components.
- Prior/opened Variation-ID overlap and gene-component overlap were both zero.
- Family, configuration, threshold, and applicable calibration choices were selected inside each outer training partition.
- Seven eligible families shared protocol fingerprint `925a72d8c7b0e23529e0b28a4a7b3e0ec837a4eff2f4f3b2ac3b16453bdd4559`.
- The small MLP diagnostic was invalid because record-level early stopping did not preserve components. It was excluded from every ranking and selection.

## Fully nested estimate

| Metric | Estimate | Component-bootstrap 95% interval |
|---|---:|---:|
| Component-weighted balanced accuracy | 0.8939 | [0.8656, 0.9192] |
| Balanced accuracy | 0.8838 | not reported |
| Accuracy | 0.8750 | [0.8491, 0.8998] |
| Macro F1 | 0.8233 | [0.7855, 0.8582] |
| Pathogenic recall | 0.8978 | [0.8503, 0.9405] |
| Benign recall | 0.8698 | [0.8396, 0.8989] |
| Brier score | 0.0736 | not reported |

The confusion matrix was `TN 708, FP 106, FN 19, TP 167`. ExtraTrees was selected for 800 outer-fold records and random forest for 200, so this estimate represents the nested selection procedure rather than a single fixed family.

## Full-development artifact

After internal evaluation, the complete development data selected ExtraTrees with `depth_None_min_5_class_balanced` and threshold `0.50`. The report-only safety threshold was `0.37`. This fitted artifact has no independent test metric and must not inherit the fully nested estimate as if it were a held-out model score.

The model artifact is `outputs/v9_1_development/model.joblib`, with SHA-256 `0d7a19a6289041daf79e56e7e407aa735d691742f01537ef64efbcb937533c13`. It is trusted executable serialization and should only be loaded after verifying that hash.

## Comparisons

The primary point estimate exceeded original V9 by 0.0203, but the paired 95% interval `[-0.0043, 0.0464]` crossed zero. It exceeded frozen V8 by 0.0116, but that interval `[-0.0123, 0.0378]` also crossed zero and the opened-label comparison is not a fair V8 win.

The strongest supported conclusion is that the fully nested V9.1 internal procedure recovered the component-weighted balanced-accuracy point estimate lost by original V9 while improving pathogenic recall, but uncertainty and evaluation history prevent a superiority claim.

Sources: `outputs/v9_1_development/run_manifest.json`, `outputs/evaluations/v9_1_candidate_models.csv`, `outputs/evaluations/v9_1_threshold_selection.json`, and `outputs/model_registry/model_v9_1.json`.
