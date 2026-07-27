# Methods

## Current Scientific Milestone

The current goal is to produce a verified table connecting variants classified as uncertain in an older ClinVar snapshot with their classifications in a newer snapshot. No model training or biological feature engineering is part of this stage.

## Historical Time Separation

The planned study asks what could have been predicted at an earlier date. The older release therefore defines the information cutoff, and the newer release supplies outcomes. This separation is necessary because a random split of current records would not recreate the historical question. It could mix evidence from the same scientific period into both training and testing.

## Preventing Future Information Leakage

Future information leakage occurs when a predictor contains information that was not available at the prediction date. Examples include a later review status, a newer submitter count, or a current annotation added after the older snapshot. Leakage can make a weak method look accurate. For this reason, newer fields are retained only to check outcomes and matches. Any future predictor will need a documented source and availability date no later than the older release.

## Selected Releases and Format

The original XML pilot considered official VCV releases dated 2024-02-01 and 2025-02-06. Their compressed sizes total about 7.89 GB. That strategy is paused because streaming can still consume the full transfer even when no archive is retained.

The active browser workspace starts with zero records and is limited to ten. ESummary retrieves one current Variation ID, or ESearch finds at most five current candidates for a gene. If a reviewer identifies an explicit historical VCV accession version, the optional command-line EFetch tool can retrieve only that version with a 10 MB cap. The version must be linked to a date and reviewed; it is not automatically treated as a monthly snapshot.

## Transfer Protection

Before any download, the software reports source, estimated size, purpose, and whether the plan crosses 500 MB. It waits for an explicit confirmation flag. The archive inspection command is metadata-only and has no body-scan option.

Pilot mode also waits for explicit confirmation even though its requests are small. Current ESummary planning reserves 1 MB. Versioned EFetch is streamed and stops at 10 MB. The CSV is written atomically, and failed temporary output is removed.

The browser Pilot Workspace is now the normal interface. A local planning request does not contact NCBI. After approval, one Variation ID or VCV request has a 1 MB estimate; a gene search has a 6 MB estimate and returns at most five candidates. Actual JSON body bytes are recorded. The 500 MB protection remains active, and no archive action is exposed by the dashboard.

## Manual Pilot Review

The browser stores current ClinVar wording without converting it to harmful or harmless. A reviewer separately enters an older date and classification, newer comparison date and classification, classification type, official NCBI source URL, notes, ambiguity reason, and checklist answers. Allowed classification labels keep uncertain, pathogenic, likely pathogenic, benign, likely benign, conflicting, protective, risk factor, drug response, oncogenic, likely oncogenic, other, and unable-to-determine categories separate.

Records begin `unreviewed` and can move to `reviewing`, `verified`, `ambiguous`, or `excluded`. Ambiguous and excluded records require an explanation. Verified records require both dates, both classifications, an official source, classification type, every checklist item, and an older date before the newer date. The calculated timeline never fills absent values.

The workspace is a small versioned JSON file. Every mutation is validated, copied to one backup, written to a temporary file, and atomically replaced. Command-line tools remain available for reproducibility but are not required for normal pilot research.

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

The browser workspace begins with zero records and is limited to ten. No archived XML body has been processed, no historical classification has been verified, no biological conclusion has been made, and no model has been trained.
