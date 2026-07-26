# Methods

## Current Scientific Milestone

The current goal is to produce a verified table connecting variants classified as uncertain in an older ClinVar snapshot with their classifications in a newer snapshot. No model training or biological feature engineering is part of this stage.

## Historical Time Separation

The planned study asks what could have been predicted at an earlier date. The older release therefore defines the information cutoff, and the newer release supplies outcomes. This separation is necessary because a random split of current records would not recreate the historical question. It could mix evidence from the same scientific period into both training and testing.

## Preventing Future Information Leakage

Future information leakage occurs when a predictor contains information that was not available at the prediction date. Examples include a later review status, a newer submitter count, or a current annotation added after the older snapshot. Leakage can make a weak method look accurate. For this reason, newer fields are retained only to check outcomes and matches. Any future predictor will need a documented source and availability date no later than the older release.

## Selected Releases and Format

The 16-record pilot uses official VCV XML releases dated 2024-02-01 and 2025-02-06. Their compressed sizes are 3,334,050,859 and 4,556,267,423 bytes. Their official MD5 values and exact URLs are fixed in configuration. Both belong to the current VCV format family, with schema revisions 2.0 and 2.2.

The current ESummary API is used only to select and display current candidate records. It cannot supply historical classifications. Historical values must come from the fixed archived XML releases.

## Bounded Remote Extraction

The pilot performs a metadata-only dry run before any body request. Confirmed extraction wraps the HTTP response in a compressed-byte counter, `gzip.GzipFile`, and incremental XML parsing. It keeps only requested `VariationArchive` records and stops when all are found. A missing record may require a full scan, so the command warns that as much as 7.89 GB could be transferred. It does not retain a gzip archive or decompressed XML file.

Record count, compressed transfer, and retained output limits stop work with an error. Network requests use timeouts and limited retries. Small outputs are written atomically, and failed temporary outputs are removed.

## Parsing

The parser reads CSV, TSV, or compressed TSV input and selects ClinVar fields by header name rather than column position. It creates a standardized table while preserving Variation ID, Allele ID, assembly, genomic representation, classification text, review status, submitter count, RCV accessions, and phenotype text. Missing values remain missing. Classification text is not simplified during parsing.

## Why Matching Is the First Scientific Challenge

A wrong cross-release match creates a wrong outcome label. Later modeling cannot repair that error. The same allele can appear on more than one genome assembly, identifiers can participate in complex records, and records may be merged, replaced, deleted, or remapped. Conditions and aggregate classifications can also change independently of the underlying DNA allele.

The current matcher:

1. Limits the older group to exact supported VUS terms.
2. Combines duplicate rows with the same Allele ID and Variation ID.
3. Prefers an exact Allele ID and Variation ID pair.
4. Allows a unique Allele ID candidate with a changed Variation ID but labels that rule separately.
5. Refuses to choose among multiple candidates or conflicting identifiers.
6. Detects a numeric Variation ID linked to multiple Allele IDs and keeps it as one unsupported complex record.
7. Requires the older release date to be earlier than the newer release date.
8. Does not use coordinates, genes, rs numbers, phenotypes, or RCV accessions as sole keys.

## Outcome Mapping

Only exact later classification terms map to directional outcomes. `Pathogenic`, `Likely pathogenic`, `Benign`, `Likely benign`, and supported VUS terms each receive their stated labels. Explicit conflict text becomes `VUS_to_Conflicting`. A still-uncertain record becomes `VUS_to_Still_Uncertain`. Missing, unfamiliar, ambiguous, or unreliable information becomes `Unable_to_Verify`.

This conservative rule avoids pretending that a mixed aggregate has one clear direction. It may place some usable records into an ambiguous group, which is acceptable until manual review supports a more detailed rule.

For the XML pilot, germline, somatic clinical impact, and oncogenicity are separate columns. Only exact Variation IDs are compared automatically. Germline values can be labeled unchanged, changed, or unable to verify. Missing records, non-current statuses, and replacement metadata are flagged. Every automatic result remains `requires_manual_review`.

## Validation Before Scale

The included CSV is synthetic test data and is not a ClinVar extract. It tests parsing, matching, missing data, output labels, and command-line formatting. Before full-release processing, a small real sample from every match category must be checked against the archived records and, when necessary, VCV or RCV history.

Sixteen real current ClinVar summaries have been recorded as pilot candidates. No archived XML body has been processed, no historical classifications have been filled, no biological conclusions have been made, and no models have been trained.
