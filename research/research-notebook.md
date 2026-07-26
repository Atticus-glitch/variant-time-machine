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
- The selected interval is a starting choice until I examine the actual headers, class counts, missing values, and manually reviewed matches.

### Next Actions

1. Download the two selected files deliberately and record retrieval metadata and checksums.
2. Inspect headers and count exact historical VUS tokens without assigning model outcomes.
3. Run the matcher on a small real sample and manually audit exact, changed, ambiguous, conflicting, and unmatched cases.

### Unresolved Questions

- Should VUS subtiers (`VUS-high`, `VUS-mid`, and `VUS-low`) be included in the initial cohort?
- How often does `AlleleID` stay the same when `VariationID` changes, and what fraction requires XML record-history checks?
- What manually reviewed error rate is acceptable before full-release matching?
- Should the final study remain variant-level or move to condition-specific RCV records?

## 2026-07-26 Historical Pipeline Foundation

### Current Milestone

Produce a verified table connecting variants labeled uncertain in one archived ClinVar release with their classifications in a later release.

### What Was Attempted

- Wrote a focused ClinVar data plan for the selected 2022-01-06 and 2024-01-04 `variant_summary` files.
- Added an explicit downloader that records URL, release date, retrieval time, filename, size, and SHA-256 checksum. No large file was downloaded.
- Added a parser that converts ClinVar summary fields to a standardized table without deleting ambiguity fields.
- Added a conservative historical VUS matcher and a two-input command-line tool.
- Added clearly labeled synthetic data and tests for exact outcomes, conflicts, missing identifiers, missing later records, parsing, and CSV output.

### What Was Learned

- Release date and retrieval date are different facts and both must be recorded.
- Variation ID and Allele ID are useful together, but their relationship is not always one-to-one.
- An exact classification mapping is safer than guessing the direction of mixed ClinVar terms.
- Software tests can verify expected behavior, but they cannot verify whether the matching rules are accurate on real ClinVar history.

### Next Step

Download the two selected files only after checking storage and provenance settings. Then inspect their actual headers and run the pipeline on a small real sample. Manually review every match category before processing the full older VUS group.

## 2026-07-26 First Live ClinVar Connection

### Date

2026-07-26

### Milestone

Created first connection to real genetic data.

### What Was Attempted

- Connected to the official NCBI ClinVar E-utilities `esummary` JSON endpoint.
- Added a single-variant client that accepts a Variation ID or VCV accession.
- Added clear error categories for invalid input, missing records, network failure, and malformed responses.
- Added a command-line connection test and a local dashboard lookup page.
- Kept the request limited to one current record and downloaded no large database.

### What Was Learned

- A small official API request is enough to test real data connectivity and interface behavior.
- Current API data cannot answer the historical research question because it is not a fixed archived snapshot.
- ClinVar ESummary provides useful aggregate fields but not the complete evidence behind every submission.

### Next Step

Use several manually selected Variation IDs to check missing fields and classification formats. Keep these connectivity checks separate from the later archived-release matching dataset.

## 2026-07-26 First Historical Comparison Workflow

### Date

2026-07-26

### Milestone

Created first historical comparison workflow.

### What Worked

- Created a dedicated manual-review folder and a header-only CSV template.
- Defined seven conservative VUS outcome categories.
- Kept ambiguous, complex, missing, and unfamiliar cases as `Unable_to_Verify`.
- Added a review command that shows current ClinVar information and the fields that still need archived verification.
- Added dashboard counts that remain zero until complete source-backed rows exist.

### What Is Still Unknown

- Which first real variants will have clear records in both selected snapshots.
- How often identifiers changed because of merging, replacement, or complex variant sets.
- Whether condition-level differences will require RCV XML instead of variant-level summary data.
- How many manually reviewed examples are needed before full archive processing is justified.

### Why Historical Matching Is Difficult

A current record does not prove what ClinVar showed in 2022 or 2024. Identifiers, assemblies, condition groupings, review status, submissions, and aggregate classifications can all change. A wrong match would create a wrong outcome, so uncertainty must be kept instead of resolved by guessing.

### Next Step

Select one candidate Variation ID, inspect its current record with `scripts/review_variant.py`, and verify the same record independently in both selected archived releases. Add the row only after every checklist item and source reference is complete.

## 2026-07-26 Bounded Historical XML Pilot

### Date

2026-07-26

### What Was Attempted

- Checked the VM interpreter, disk, archive listings, file sizes, official MD5 files, XML family, and schema revisions.
- Selected VCV XML releases dated 2024-02-01 and 2025-02-06.
- Added a confirmation-gated incremental gzip and XML reader with record, transfer, and output limits.
- Retrieved current ESummary facts for 16 active low-numbered Variation IDs and left all historical fields blank.
- Added manifests, exact-ID comparison, missing-record states, record-history flags, and persistent manual review.
- Added a Historical Pilot dashboard page and mocked tests. No archive body was requested during development tests.

### Environment Finding

The active `.venv` uses Python 3.14.4. Python 3.12 and `uv` were not installed, and the configured Ubuntu 26.04 APT repositories did not list Python 3.12 packages. The existing environment was kept. The repository now documents a separate `.venv312` route, but migration is not confirmed.

### What Was Learned

- Streaming prevents large local archive storage but can still use several gigabytes of bandwidth.
- VCV schema 2.0 and 2.2 are in the same current family, but fields still need tolerant parsing and manual checks.
- Germline classification, somatic clinical impact, and oncogenicity must remain separate.
- An exact Variation ID is a useful pilot match, but record status, replacements, conditions, and aggregation can still change its meaning.
- Software tests can show safe failure behavior. They cannot certify a historical scientific match.

### What Is Still Unknown

- Whether all 16 requested records occur in both selected archives.
- How many compressed bytes an actual early-stopped scan will transfer.
- Whether the extracted XML field paths cover every real pilot record shape.
- Which automatic comparisons will pass human review.

### Next Step

Run the metadata-only dry run. Review its URLs, sizes, and MD5 results. Run a real archive scan only after explicitly accepting the possible 7.89 GB transfer, then manually inspect every extracted comparison before making any historical claim.
