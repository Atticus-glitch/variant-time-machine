# Project Decisions

## Use Historical Time Splitting

A random train/test split can place records from the same scientific period, gene, or evidence history on both sides of an evaluation. The intended question is about predicting a later state from an earlier state, so evaluation must preserve time. A held-out later period is a closer simulation of the real research task and makes performance claims more credible.

## Prevent Future-Information Leakage

Future-information leakage occurs when a feature contains evidence that was unavailable at the prediction date. Examples could include a newer review status, a later submission count, or an annotation updated after the historical cutoff. Leakage can create impressive but meaningless accuracy. Every feature therefore needs a source, release, and availability rule.

## Start With Interpretable Baselines

The outcome classes may be imbalanced, with many variants remaining uncertain. An “all remain uncertain” baseline and a simple majority baseline establish how much accuracy is available without learning anything. A hand-designed score and logistic regression can then reveal whether specific clues add value. More complex models should be considered only if they improve a carefully held-out evaluation and remain explainable enough for the research goal.

## Treat Matching as the First Major Technical Risk

A wrong cross-release match creates a wrong outcome label, and no model can repair that error. Variant names, genome assemblies, coordinates, alleles, conditions, and identifiers can change or be represented differently. Matching rules must prioritize stable identifiers, verify genomic details, preserve ambiguous cases, and be tested through manual inspection before large-scale processing.

## Pilot Release Pair: February 2024 to February 2025

The small record-history pilot uses official VCV XML releases dated 2024-02-01 and 2025-02-06. Both use the same current XML family, but their documented schema revisions are 2.0 and 2.2. XML was selected because it exposes record status, replacement history, and separate germline, somatic clinical impact, and oncogenicity classifications. The older January 2022 to January 2024 `variant_summary` choice is deferred rather than treated as pilot evidence.

## Begin With Identifier-Only Matching

The proof of concept accepts exact `AlleleID + VariationID` pairs and separately flags unique Allele ID matches when the Variation ID changed. It keeps multiple candidates, conflicting identifiers, complex records, and unmatched records visible instead of forcing a match. I am delaying coordinate matching and record-history checks because they require careful genome-assembly normalization and evidence from VCV or RCV records.

## Stream Instead of Retaining Full XML

The two source archives total about 7.89 GB compressed. The pilot reads compressed XML directly from NCBI and retains only requested records. A metadata-only dry run is the default safe first step, and a body scan requires an explicit confirmation flag. Transfer and output limits fail closed. This saves local disk but does not remove the possible multi-gigabyte bandwidth cost.

## Require Human Review

The pilot selects 16 current records through official NCBI ESummary and leaves all historical fields blank before extraction. Exact Variation ID matches are automatic candidates only. Record status, replacement metadata, missing values, and separate classification types remain visible. No automatic comparison is scientifically verified until a person checks both archived records and saves a review state.
