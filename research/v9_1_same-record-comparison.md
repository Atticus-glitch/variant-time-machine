# V9.1 same-record comparison

## Results

All rows below use the same 1,000 records and unchanged labels.

| Procedure | Component-weighted BA | Balanced accuracy | Accuracy | Macro F1 | Pathogenic recall | Benign recall | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| V9.1 fully nested selection | 0.8939 | 0.8838 | 0.875 | 0.8233 | 0.8978 | 0.8698 | 0.0736 |
| Original V9 | 0.8735 | 0.8580 | 0.860 | 0.8018 | 0.8548 | 0.8612 | 0.0687 |
| Frozen V8 | 0.8822 | 0.8712 | 0.895 | 0.8404 | 0.8333 | 0.9091 | 0.0633 |
| Frozen V7 | 0.8706 | 0.8667 | 0.864 | 0.8080 | 0.8710 | 0.8624 | 0.0637 |

Against original V9, V9.1 improved the component-weighted balanced-accuracy point estimate by 0.0203. The paired 95% component bootstrap interval was `[-0.0043, 0.0464]`, so the result does not establish a clear improvement. There were 69 prediction disagreements: V9.1 corrected 42 original-V9 errors and harmed 27 original-V9 correct predictions.

Against frozen V8, V9.1 improved the component-weighted balanced-accuracy point estimate by 0.0116 and pathogenic recall by 0.0645. It reduced accuracy by 0.0200, macro F1 by 0.0171, benign recall by 0.0393, and calibration quality as measured by Brier score. The paired primary-metric interval was `[-0.0123, 0.0378]`.

## Interpretation

V9.1 does not fairly beat V8. V8 was evaluated while these labels were sealed; V9.1 was developed after they were opened. The intervals also condition on fixed out-of-fold predictions and omit full feature, candidate, calibration, and threshold-selection uncertainty.

Sources: `outputs/evaluations/v9_1_same_record_comparisons.csv` and `outputs/evaluations/v9_1_bootstrap_intervals.json`.
