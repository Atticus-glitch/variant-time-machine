# Methods

## Study Design

The planned study is a retrospective historical prediction experiment. Variants classified as uncertain in an older ClinVar snapshot will form the starting cohort. Their records in a later snapshot will define outcomes, subject to explicit handling of conflicting, merged, withdrawn, condition-specific, and unmatched records.

## Matching Before Modeling

Stable identifiers will be preferred, then checked against available genomic assembly, coordinate, reference allele, alternate allele, and condition information. A small sample will be manually reviewed before scaling. Match confidence and exclusion reasons will be retained so sensitivity analyses can test whether conclusions depend on uncertain matches.

## Leakage Control

Every predictor must have been available by the older release cutoff. Fields from the newer release are outcome information and cannot become features. External annotations will be added only when a historical release or defensible availability date can be established.

## Planned Comparisons

The evaluation will begin with majority and “all remain uncertain” baselines, followed by a transparent biological score and logistic regression. A tree-based model may be tested later. Held-out variants or later time periods will be used for evaluation. Planned metrics include accuracy, balanced accuracy, per-class precision, recall, F1 score, confusion matrices, and calibration where appropriate. Class balance and uncertainty must accompany any metric.

No data have been processed and no models have been run yet.
