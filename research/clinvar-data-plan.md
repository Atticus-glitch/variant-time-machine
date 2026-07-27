# ClinVar Historical Data Plan

> Pilot update, 2026-07-26: the active test uses five empty manual slots and
> one-record ESummary or versioned VCV EFetch requests. The bulk-file plan below
> is retained only as background. None of these files has been downloaded.

Date: 2026-07-26

## Goal

The current goal is to produce a checked table that connects variants classified as uncertain in an older ClinVar release with their classifications in a later release. This stage is about reliable records and matching, not machine learning or biological conclusions.

## Selected Archive Files

The first planned comparison uses two official monthly ClinVar files:

| Role | Release date | File |
| --- | --- | --- |
| Older release | 2022-01-06 | `variant_summary_2022-01.txt.gz` |
| Newer release | 2024-01-04 | `variant_summary_2024-01.txt.gz` |

Official URLs:

- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/variant_summary_2022-01.txt.gz
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/variant_summary_2024-01.txt.gz

Both are first-Thursday monthly archive releases and are two years apart. They also come before a documented change later in January 2024 that added somatic classification columns to `variant_summary`. The dates are a starting choice and may be changed if header inspection or matching checks show a serious problem.

## Available Formats

ClinVar provides several formats:

- XML contains the most complete public records, including detailed VCV, RCV, and SCV information. It is large and more complicated to parse.
- VCF contains short variants with genomic coordinates for GRCh37 or GRCh38. It does not include every ClinVar record and is not the best source for complete classification history.
- Tab-separated files provide summary tables. `variant_summary` includes aggregate classification, review status, submitter count, identifiers, genes, and genomic locations.
- Web pages and APIs are useful for checking individual records, but they are not a substitute for a fixed historical snapshot.

The first pipeline will use the archived tab-separated `variant_summary` files. They are easier to inspect and smaller than XML while still containing the main fields needed for a variant-level comparison. XML may later be needed to investigate merged, replaced, deleted, or condition-specific records.

## Variant Identification

The initial matcher will use both `VariationID` and `AlleleID`:

1. An exact `VariationID + AlleleID` pair is the strongest automatic match in `variant_summary`.
2. Duplicate rows for different genome assemblies will be combined into one matched entity.
3. If the Variation ID changes but the Allele ID has exactly one later candidate, the record will be kept with a separate changed-ID status.
4. A match will not be selected when one identifier points to multiple candidates or the identifiers disagree.

Variation ID represents a classified variant or set of alleles. Allele ID represents an individual allele. Their relationship is not always one-to-one, so neither number should be used without checking the other when both are available.

Coordinates, rs numbers, genes, names, phenotypes, and RCV accessions may support a manual review, but the first automatic matcher will not use any of them as a sole key.

## Release and Retrieval Records

Each downloaded file will have a sidecar metadata file recording:

- official source URL,
- ClinVar release date,
- UTC retrieval date and time,
- local filename,
- file size,
- SHA-256 checksum calculated after download.

The release date describes the data snapshot. The retrieval date describes when this project obtained the bytes. These dates must not be confused. Raw downloads will stay in `data/raw/` and will not be committed to Git.

## Matching Problems Over Time

Possible problems include:

- one biological variant appearing once for GRCh37 and once for GRCh38,
- Variation IDs being merged, replaced, or used for complex records,
- one Allele ID appearing in more than one classified variant set,
- coordinates or preferred names changing,
- records disappearing because of deletion, replacement, or mapping changes,
- aggregate classifications combining submissions about different conditions,
- mixed or conflicting classification terms,
- missing identifiers or classifications,
- changes in file columns and definitions between releases.

The parser will select columns by header name rather than fixed position. Original identifiers and uncertainty fields will be kept in the standardized table so questionable matches can be reviewed.

## Ambiguous Cases

The pipeline will preserve uncertainty instead of forcing an answer:

- `VUS_to_Conflicting` will be used when the later classification explicitly reports conflict.
- `Unable_to_Verify` will be used when the later record cannot be identified reliably, its classification is missing, or its wording cannot be mapped safely.
- Match details will include a match status and candidate count.
- Records with multiple possible matches or disagreeing identifiers will not enter a clean training table unless a later manual or XML-based review resolves them.

Before full processing, a small real sample from each match category must be reviewed by hand. The synthetic example data in this repository only test software behavior and are not evidence about ClinVar.

## Official Sources

Accessed 2026-07-26:

- https://www.ncbi.nlm.nih.gov/clinvar/docs/release_cycle/
- https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/
- https://www.ncbi.nlm.nih.gov/clinvar/docs/identifiers/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/README
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/
