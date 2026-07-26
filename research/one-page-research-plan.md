# Project Title

**Variant Time Machine: Predicting the Future Reclassification of Uncertain Genetic Variants**

## Background and Problem

DNA variants are differences in DNA sequences. Some variants are clearly harmful because strong evidence links them to disease, while others are clearly harmless. Many variants fall between these categories. They are labeled **variants of uncertain significance (VUS)** because the available evidence is incomplete or conflicting.

ClinVar is a public database that stores variant classifications submitted by clinical laboratories, researchers, and expert groups. Over time, new population, laboratory, clinical, or computational evidence may cause an uncertain variant to be reclassified as pathogenic, likely pathogenic, benign, or likely benign. Predicting which uncertain variants are most likely to change could help researchers prioritize variants for additional investigation. This project is a research prioritization project, not a diagnostic medical tool.

## Research Question

**Using only information that was available at an earlier point in time, can an explainable computational model predict whether a ClinVar variant of uncertain significance will later be reclassified as harmful, harmless, or remain uncertain?**

## Hypothesis

Uncertain variants may be more likely to become classified as harmful when they are rare in population data, significantly alter a protein, occur in important or evolutionarily conserved protein regions, affect genes that do not tolerate damaging variation well, or gain stronger evidence from multiple submitters.

Variants may be more likely to become classified as harmless when they are relatively common among apparently healthy populations, do not meaningfully alter a protein, occur outside important protein regions, or gain agreement among trusted submitters supporting a benign interpretation. These statements are hypotheses to test, not facts that the analysis will assume.

## Proposed Data

The project will begin with:

- an older archived ClinVar release,
- a newer ClinVar release,
- variants labeled uncertain in the older release,
- and their classifications in the newer release.

Potential later sources include gnomAD for population frequency, UniProt for protein domains and function, and conservation or gene-constraint information from reputable public sources. The first version will use ClinVar information alone before external biological features are added.

## Method

1. Download or obtain an archived ClinVar dataset and a newer ClinVar dataset.
2. Identify variants labeled uncertain in the older release.
3. Match the same variants between releases using stable identifiers and carefully checked genomic information.
4. Label each outcome as moved toward harmful, moved toward harmless, remained uncertain, or unusable/ambiguous.
5. Remove or separately analyze records with unreliable matching, conflicting definitions, or information leakage.
6. Create features that would actually have been available at the earlier date.
7. Compare a simple majority or “all remain uncertain” baseline, a hand-designed biological scoring system, logistic regression, and possibly a tree-based model.
8. Test models on variants or time periods that were not used during training.
9. Compare accuracy, balanced accuracy, precision, recall, F1 score, confusion matrices, and calibration where appropriate.
10. Build a website that explains individual predictions and the evidence behind them.

## Original Contribution

The originality is not a claim that nobody has studied variant reclassification. The intended contribution is the combination of strict historical testing, prevention of future-information leakage, explainable predictions, comparison against simple baselines, analysis of which clues provide useful information, and an accessible public demonstration.

## Expected Output

- reproducible Python data pipeline,
- historical variant-reclassification dataset,
- explainable prediction models,
- graphs and statistical comparisons,
- public website/demo,
- GitHub repository,
- science-fair poster,
- abstract and research paper.

## Safety, Ethics, and Limitations

Only public or appropriately accessible non-identifiable data will be used. No human participants will be recruited, no medical records will be collected, and no biological organisms will be modified. The tool must not diagnose patients. Predictions may reflect weaknesses or disagreements in existing databases, ClinVar classifications can conflict or change, and all conclusions must remain limited to the tested datasets.

## Immediate Milestone

**First milestone: produce a verified table connecting variants labeled uncertain in one archived ClinVar release with their classifications in a later release. No machine-learning claims will be made until this matching process has been checked carefully.**
