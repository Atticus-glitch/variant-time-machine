# 2026-07-26 Research Notebook

## Project Setup

### Work Recorded

- Created the initial repository structure, Python package, documentation, validation script, and automated setup tests.
- Defined the initial research question: can only historically available information predict whether a ClinVar VUS later moves toward harmful, moves toward harmless, or remains uncertain?
- Deliberately did not download data, select releases, implement matching, or train models during setup.

### Initial Assumptions

- Archived ClinVar releases provide enough information to identify a meaningful set of variants classified as uncertain at an older date.
- At least one stable identifier or a carefully normalized genomic representation can support cross-release matching.
- Classification categories and review status will require explicit, version-aware definitions.
- The date on which each candidate feature became available can be determined well enough to avoid using future information.

### Next Actions

1. Choose two scientifically useful ClinVar release dates.
2. Compare available archive formats and fields, especially identifiers and classification dates.
3. Design and manually inspect a small proof-of-concept cross-release match.

### Unresolved Questions

- Which release interval provides enough reclassifications without making historical fields incomparable?
- Should classifications be analyzed at the variant, condition, or variant-condition level?
- Which ClinVar identifier remains most stable across the selected formats and dates?
- How should conflicting submissions, multiple conditions, withdrawn records, and merged records be labeled?
- What evidence proves that a feature was available by the older cutoff date?

## ClinVar Archive and Matcher Research

### Work Recorded

- Reviewed official NCBI documentation for ClinVar release cadence, archive formats, tab-delimited fields, and identifier relationships.
- Provisionally selected monthly `variant_summary` releases dated 2022-01-06 and 2024-01-04. No release files were downloaded.
- Implemented an identifier-only proof-of-concept matcher and tests using explicitly synthetic TSV fixtures.
- Required ambiguity, conflict, unsupported-complex-record, and unmatched outcomes to remain visible rather than forcing matches.

### Evidence and Assumptions

- Both selected files exist in official NCBI archive listings and are exactly two years apart.
- Both snapshots precede a documented 2024-01-29 `variant_summary` schema expansion for somatic classifications.
- `AlleleID + VariationID` is treated as the strongest key available in `variant_summary`, while neither identifier is assumed to be permanently simple or one-to-one.
- The selected interval is provisional until actual headers, class counts, missingness, and manually reviewed matches are examined.

### Next Actions

1. Download the two selected files deliberately and record retrieval metadata and checksums.
2. Inspect headers and count exact historical VUS tokens without assigning model outcomes.
3. Run the matcher on a small real sample and manually audit exact, changed, ambiguous, conflicting, and unmatched cases.

### Unresolved Questions

- Should VUS subtiers (`VUS-high`, `VUS-mid`, and `VUS-low`) be included in the initial cohort?
- How often does `AlleleID` persist when `VariationID` changes, and what fraction requires XML lifecycle resolution?
- What manually reviewed error rate is acceptable before full-release matching?
- Should the final study remain variant-level or move to condition-specific RCV records?
