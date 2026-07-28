# Methods

## Current Scientific Milestone

The first descriptive pilot now contains three genuine VCV histories and seven official versions. One automatic `Other_Germline_Change` and two unchanged histories were detected; all three remain unverified. The next goal is approximately 25–50 suitable, manually reviewed histories. This stage includes no machine learning, model training, or biological feature engineering.

## Historical Time Separation

The planned study asks what could have been predicted at an earlier date. The older release therefore defines the information cutoff, and the newer release supplies outcomes. This separation is necessary because a random split of current records would not recreate the historical question. It could mix evidence from the same scientific period into both training and testing.

## Preventing Future Information Leakage

Future information leakage occurs when a predictor contains information that was not available at the prediction date. Examples include a later review status, a newer submitter count, or a current annotation added after the older snapshot. Leakage can make a weak method look accurate. For this reason, newer fields are retained only to check outcomes and matches. Any future predictor will need a documented source and availability date no later than the older release.

## Active VCV Version-History Pilot

The original XML pilot considered official VCV releases dated 2024-02-01 and 2025-02-06. Their compressed sizes total about 7.89 GB. That full-archive strategy remains paused because streaming can still consume the complete transfer.

The dashboard's Version History Explorer is the normal workflow. Its optional ESearch/ESummary helper finds at most five current candidates through individual current requests. History uses EFetch instead: an unversioned VCV request establishes the latest official version, followed by exact `.version` requests in `all`, custom inclusive-range, or endpoint mode. Strict canonical VCV validation and exact returned-version checks prevent a different record or version from being accepted silently.

## Transfer Protection

Planning is local and does not contact NCBI. Every operation shows its official source, purpose, request count, maximum transfer, and storage estimate before explicit approval. The initial latest-version request does not count toward the maximum 25 historical requests. Historical EFetch requests are individual, sequential, and paced by 0.34 seconds; they use a 10-second connect timeout, a 30-second read timeout, and two limited retries for connect/read failures and selected transient HTTP statuses.

Each response has a 10 MiB hard cap (approximately 10 MB), and the complete exploration has a 50 MiB hard cap. Cancellation is observed between requests, not during the active request. Only official NCBI endpoints are used, only one dashboard exploration runs at once, and no archive action is exposed.

Partial or complete results with received historical data are saved under the ignored `data/manual_review/vcv_history/<VCV>/` tree. Individual JSON and XML replacements are bounded and atomic, symlinks are refused, and readers use the same lock as writers so they do not observe an in-progress refresh. An interrupted process can still leave a mixed generation across files, so manifests and source records must be checked during review.

## Automatic Parsing and Comparison

Each EFetch record preserves accession/version, Variation ID, record type, genes, name, HGVS expressions, record dates, conditions, record status, replacement/deletion metadata, and warnings. Germline, somatic clinical impact, and oncogenicity are parsed into separate classification blocks; each block has independent classification, review status, last-evaluated date, and submission count where supplied.

Only `available` versions are compared, sorted by version. The comparison skips unavailable holes and warns when the two available versions are not numerically consecutive. Automatic germline change labels are:

- `No_Classification_Change`
- `VUS_to_Pathogenic`, `VUS_to_Likely_Pathogenic`, `VUS_to_Benign`, `VUS_to_Likely_Benign`
- `Pathogenic_to_VUS`, `Benign_to_VUS`
- `Became_Conflicting`, `Conflict_Resolved`, `Other_Germline_Change`
- `Non_Germline_Change`, `Missing_Classification`

`Non_Germline_Change` means the normalized germline classification was unchanged but a somatic or oncogenicity block differed. The timeline also reports review-status values, whether known germline submission counts changed, warnings, and `high` or `limited` confidence. `Unable_to_Compare` and `unable` confidence are declared schema values but are not currently emitted by this comparison path. These are automatic labels, not manually verified scientific outcomes.

## Manual Pilot Review

Version histories begin `unreviewed` and can become `needs_review`, `ambiguous`, `manually_verified`, or `excluded`. Ambiguous and excluded histories require notes. `manually_verified` requires all ten checks: VCV identity, Variation ID, gene, classification type, old/new versions, relevant dates, official source requests, manually checked classification change, documented missing/conflicting information, and acknowledgement that versions are not monthly snapshots.

Reviewer decisions, notes, sources, verification flags, and manual corrections are stored only in `review.json`. Manual corrections are annotations and never mutate `metadata.json`, `versions.json`, `comparisons.json`, `manifest.json`, or raw XML. This separation keeps automatic extraction reproducible and human interpretation auditable.

The manifest and review store the same SHA-256 digest of the automatic evidence. If a
refresh changes that evidence, a previously verified case returns to `needs_review`
with all checks false. Human notes, sources, and corrections remain preserved.

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

One real three-version history, `VCV000014026`, has been retrieved and automatically compared. All three aggregate germline classifications were `Pathogenic`; review status and submission counts changed, but no germline classification change was detected. The case remains `needs_review` with zero completed verification checks. The next validation step is to build and manually verify approximately 10–25 genuine histories, preserving unsuccessful, ambiguous, deleted/replaced, missing, and parsing-failure cases. Only then will the project evaluate whether VCV history is sufficient or whether archived monthly summaries/releases are required.
