# Project Decisions

## Use Historical Time Splitting

A random train/test split can place records from the same scientific period, gene, or evidence history on both sides of an evaluation. The intended question is about predicting a later state from an earlier state, so evaluation must preserve time. A held-out later period is a closer simulation of the real research task and makes performance claims more credible.

## Prevent Future-Information Leakage

Future-information leakage occurs when a feature contains evidence that was unavailable at the prediction date. Examples could include a newer review status, a later submission count, or an annotation updated after the historical cutoff. Leakage can create impressive but meaningless accuracy. Every feature therefore needs a source, release, and availability rule.

## Start With Interpretable Baselines

The outcome classes may be imbalanced, with many variants remaining uncertain. An “all remain uncertain” baseline and a simple majority baseline establish how much accuracy is available without learning anything. A hand-designed score and logistic regression can then reveal whether specific clues add value. More complex models should be considered only if they improve a carefully held-out evaluation and remain explainable enough for the research goal.

## Treat Matching as the First Major Technical Risk

A wrong cross-release match creates a wrong outcome label, and no model can repair that error. Variant names, genome assemblies, coordinates, alleles, conditions, and identifiers can change or be represented differently. Matching rules must prioritize stable identifiers, verify genomic details, preserve ambiguous cases, and be tested through manual inspection before large-scale processing.

## Pause the February 2024 to February 2025 Archive Pair

The considered VCV XML releases are dated 2024-02-01 and 2025-02-06. They are valid fixed historical sources, but together they can transfer about 7.89 GB. This pair is paused and is not the active pilot input. The active pilot uses one-record API requests.

## Begin With Identifier-Only Matching

The proof of concept accepts exact `AlleleID + VariationID` pairs and separately flags unique Allele ID matches when the Variation ID changed. It keeps multiple candidates, conflicting identifiers, complex records, and unmatched records visible instead of forcing a match. I am delaying coordinate matching and record-history checks because they require careful genome-assembly normalization and evidence from VCV or RCV records.

## Do Not Stream Full XML for the Pilot

Streaming avoids storing a full archive, but it does not avoid transferring the archive when records are missing or late. The command-line body scan was removed. Metadata-only inspection remains available, and the reusable reader defaults to a 500 MB transfer ceiling.

## Require Human Review

The pilot begins with five empty rows. Each variant must be manually selected for a written reason. Current ESummary and explicit-version VCV EFetch results remain separate, and no historical classification is verified until a person checks the record date, condition scope, and source.
