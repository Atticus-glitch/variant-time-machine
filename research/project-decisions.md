# Project Decisions

## Use Historical Time Splitting

A random train/test split can place records from the same scientific period, gene, or evidence history on both sides of an evaluation. The intended question is about predicting a later state from an earlier state, so evaluation must preserve time. A held-out later period is a closer simulation of the real research task and makes performance claims more credible.

## Prevent Future-Information Leakage

Future-information leakage occurs when a feature contains evidence that was unavailable at the prediction date. Examples could include a newer review status, a later submission count, or an annotation updated after the historical cutoff. Leakage can create impressive but meaningless accuracy. Every feature therefore needs a source, release, and availability rule.

## Start With Interpretable Baselines

The outcome classes may be imbalanced, with many variants remaining uncertain. An “all remain uncertain” baseline and a simple majority baseline establish how much accuracy is available without learning anything. A hand-designed score and logistic regression can then reveal whether specific clues add value. More complex models should be considered only if they improve a carefully held-out evaluation and remain explainable enough for the research goal.

## Treat Matching as the First Major Technical Risk

A wrong cross-release match creates a wrong outcome label, and no model can repair that error. Variant names, genome assemblies, coordinates, alleles, conditions, and identifiers can change or be represented differently. Matching rules must prioritize stable identifiers, verify genomic details, preserve ambiguous cases, and be tested through manual inspection before large-scale processing.

## Initial Release Pair: January 2022 to January 2024

I chose the archived monthly `variant_summary` releases dated 2022-01-06 and 2024-01-04 for the first comparison. Both are official first-Thursday snapshots, and they are two years apart. They also come before ClinVar added somatic-classification columns later in January 2024, which avoids one known schema difference. This choice is not final. I still need to check the actual headers, class counts, missing values, and number of usable matches.

## Begin With Identifier-Only Matching

The proof of concept accepts exact `AlleleID + VariationID` pairs and separately flags unique Allele ID matches when the Variation ID changed. It keeps multiple candidates, conflicting identifiers, complex records, and unmatched records visible instead of forcing a match. I am delaying coordinate matching and record-history checks because they require careful genome-assembly normalization and evidence from VCV or RCV records.
