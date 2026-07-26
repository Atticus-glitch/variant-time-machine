# Methods

## Study Design

This project is a historical prediction study. I will begin with variants classified as uncertain in an older ClinVar snapshot and check their records in a later snapshot. Conflicting, merged, withdrawn, condition-specific, and unmatched records will be labeled clearly instead of being forced into an outcome group.

## Matching Before Modeling

The identifier-only proof of concept combines duplicate assembly rows and first looks for an exact `AlleleID + VariationID` pair. A unique Allele ID candidate with a changed Variation ID receives a separate status. The matcher does not make an automatic choice when it finds multiple candidates, conflicting identifiers, complex records, or no match. Coordinates, RCVs, conditions, genes, names, and rs numbers are not used by themselves as matching keys. Coordinate matching and record-history checks will need separate testing before they are added.

The proof of concept is tested only with explicitly synthetic fixtures. Before scaling, a small sample from the selected 2022-01-06 and 2024-01-04 snapshots must be manually reviewed. Match rule, candidate count, original identifiers, classifications, and exclusion reason will be retained for audit.

## Leakage Control

Every predictor must have been available by the older release cutoff. Fields from the newer release are outcome information and cannot become features. I will add external annotations only when I can identify a historical release or another reliable date showing that the information was available.

## Planned Comparisons

The evaluation will begin with majority and “all remain uncertain” baselines, followed by a transparent biological score and logistic regression. A tree-based model may be tested later. Held-out variants or later time periods will be used for evaluation. Planned metrics include accuracy, balanced accuracy, per-class precision, recall, F1 score, confusion matrices, and calibration where appropriate. Class balance and uncertainty must accompany any metric.

No real ClinVar release has been downloaded or processed, no biological outcomes have been assigned, and no models have been run yet.
