# V9.1 feature ablation

## Scope

This is internal grouped cross-validation on the 1,000 previously opened V8 records. Each outer training partition was augmented with the authenticated 9,818-record V8 development matrix. It is not an independent final evaluation.

| Feature set | Features | Component-weighted BA | Balanced accuracy | Accuracy | Macro F1 | Pathogenic recall | Benign recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Consequence only | 17 | 0.8517 | 0.8425 | 0.828 | 0.7688 | 0.8656 | 0.8194 |
| Metadata only | 14 | 0.5487 | 0.5532 | 0.438 | 0.4225 | 0.7366 | 0.3698 |
| Consequence + metadata | 31 | 0.8856 | 0.8737 | 0.818 | 0.7692 | 0.9624 | 0.7850 |
| + completeness | 48 | 0.8833 | 0.8710 | 0.817 | 0.7676 | 0.9570 | 0.7850 |
| All allowed non-leaky | 64 | 0.8864 | 0.8760 | 0.842 | 0.7904 | 0.9301 | 0.8219 |

Metadata alone was weak. Adding metadata to consequence features improved component-weighted balanced accuracy by 0.0339, but shifted the operating point toward pathogenic recall. Completeness features did not improve the primary metric. The full 64-feature set recovered benign recall and macro F1 while remaining 0.0008 above the 31-feature set on the primary metric.

Gene identity was forbidden and not fit. Component-disjoint folds make fold-local gene identities unseen, while fold-global encoding would leak the held-out component identity. The nominal `all_allowed_without_gene` result is therefore identical to the selected feature set.

Source: `outputs/evaluations/v9_1_feature_ablation.csv`.
