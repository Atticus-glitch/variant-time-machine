# Methods

## Study Design

The planned study is a retrospective historical prediction experiment. Variants classified as uncertain in an older ClinVar snapshot will form the starting cohort. Their records in a later snapshot will define outcomes, subject to explicit handling of conflicting, merged, withdrawn, condition-specific, and unmatched records.

## Matching Before Modeling

The identifier-only proof of concept collapses duplicate assembly rows and first seeks an exact `AlleleID + VariationID` pair. A unique Allele ID candidate with a changed Variation ID is retained under a separate status. Multiple candidates, identifier conflicts, complex included records, and unmatched records are preserved rather than resolved automatically. Coordinates, RCVs, conditions, genes, names, and rs numbers are not used as sole keys. Coordinate fallback and VCV/RCV lifecycle resolution will require separate validation before implementation.

The proof of concept is tested only with explicitly synthetic fixtures. Before scaling, a small sample from the selected 2022-01-06 and 2024-01-04 snapshots must be manually reviewed. Match rule, candidate count, original identifiers, classifications, and exclusion reason will be retained for audit.

## Leakage Control

Every predictor must have been available by the older release cutoff. Fields from the newer release are outcome information and cannot become features. External annotations will be added only when a historical release or defensible availability date can be established.

## Planned Comparisons

The evaluation will begin with majority and “all remain uncertain” baselines, followed by a transparent biological score and logistic regression. A tree-based model may be tested later. Held-out variants or later time periods will be used for evaluation. Planned metrics include accuracy, balanced accuracy, per-class precision, recall, F1 score, confusion matrices, and calibration where appropriate. Class balance and uncertainty must accompany any metric.

No real ClinVar release has been downloaded or processed, no biological outcomes have been assigned, and no models have been run yet.
