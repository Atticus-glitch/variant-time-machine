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

The considered VCV XML releases are dated 2024-02-01 and 2025-02-06. They are valid fixed historical sources, but together they can transfer about 7.89 GB. This pair is paused and is not the active pilot input. The active pilot uses bounded individual VCV API requests.

## Begin With Identifier-Only Matching

The proof of concept accepts exact `AlleleID + VariationID` pairs and separately flags unique Allele ID matches when the Variation ID changed. It keeps multiple candidates, conflicting identifiers, complex records, and unmatched records visible instead of forcing a match. I am delaying coordinate matching and record-history checks because they require careful genome-assembly normalization and evidence from VCV or RCV records.

## Do Not Stream Full XML for the Pilot

Streaming avoids storing a full archive, but it does not avoid transferring the archive when records are missing or late. The command-line body scan was removed. Metadata-only inspection remains available, and the reusable reader defaults to a 500 MB transfer ceiling.

## Require Human Review

The older CSV pilot begins with five empty rows. Each variant must be manually selected for a written reason. Current ESummary and exact-version VCV EFetch results remain separate, and no historical classification is verified until a person checks the record date, condition scope, and source.

## Adopt a Bounded VCV Version-History Pilot

The active method is a bounded pilot of genuine VCV histories through the local
Version History Explorer. It uses only official NCBI services: current ESearch and
individual ESummary requests may identify candidates, while unversioned VCV EFetch
establishes the latest accession version and exact `.version` EFetch requests provide
the history. Input and returned versions are strictly validated.

This decision does not authorize machine learning or a full archive download. The
pilot is not equivalent to comparing monthly snapshots: VCV versions identify changes
to one aggregate record, not a complete database state at regular calendar dates.
Eventual archived monthly summaries or releases may still be required if the pilot
cannot support date-specific selection and validation.

The implementation bounds a history to 25 historical requests after the current
lookup, 10 MiB per response (approximately 10 MB), and 50 MiB per exploration. It
uses individual sequential requests, 0.34-second pacing, 10-second connect and
30-second read timeouts, two limited retries, and cancellation checks between
requests. Automatic parsing/comparison artifacts remain separate from manual
corrections, and manual verification requires ten explicit checks.

**Next milestone:** Build and manually verify a pilot set of approximately 10–25 genuine VCV histories, then evaluate whether this version-history method is sufficient for selecting and validating the first historical examples.
