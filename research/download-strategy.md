# Historical ClinVar Download Strategy

Date: 2026-07-28

## Decision

Use the official archived, gzip-compressed `variant_summary` tab-separated files for the first broad cross-release dataset. The fixed pair is:

| Role | Release date | Official file | Compressed bytes |
| --- | --- | --- | ---: |
| Older | 2022-01-06 | `variant_summary_2022-01.txt.gz` | 95,791,203 |
| Newer | 2024-01-04 | `variant_summary_2024-01.txt.gz` | 223,649,945 |
| Total | | | 319,441,148 |

The URLs and expected sizes are centralized in `src/variant_time_machine/config.py`. HTTP metadata and the official archive listings were checked before implementation; no archive body was downloaded during planning.

## Format Comparison

| Format | Coverage and fields | Storage and processing | Decision for first dataset |
| --- | --- | --- | --- |
| `variant_summary` TSV | Broad variant coverage; Variation ID, Allele ID, aggregate classification, review status, gene, condition names, and coordinates | The selected pair is about 319 MB compressed; header-based chunked parsing is practical | Selected |
| VCF | Useful normalized short variants and coordinates | Smaller, but excludes records that cannot be represented as VCF variants and does not provide an equivalent complete variant-level snapshot | Not sufficient alone |
| VCV XML | Rich aggregate records, accessions, assertions, and history detail | Multi-gigabyte monthly archives with more complex streaming parsing | Reserve for targeted ambiguity review |
| RCV/SCV XML | Condition-level and submission-level evidence | Larger semantic and parsing scope than the initial question requires | Not selected |
| E-utilities API | Useful for bounded checks of individual records | Not a fixed broad monthly snapshot and inefficient for the full release comparison | Continue using for manual checks only |

The TSV choice is deliberately limited. It cannot safely resolve every merge, replacement, deletion, condition-specific assertion, or submission history. Such cases remain ambiguous until targeted official-record review.

## Transfer Safety

The Historical Dataset Builder calculates a new local plan without contacting NCBI. Its automatic safe-download limit is the smallest of:

- 5,000,000,000 bytes;
- 10% of currently free filesystem space;
- the amount that preserves at least 20,000,000,000 bytes free.

The builder reports the exact URLs, compressed sizes, largest sequential `.part` file, current free space, estimated free space after transfer, destination, and existing-file status. A transfer requires a one-use approval of the exact server-issued plan. Downloads run sequentially and use the existing atomic file and provenance-sidecar behavior.

Existing targets are reused only when they are regular, non-symbolic files with the configured exact size. Wrong-size or unsafe targets block the operation; the builder does not overwrite or remove them automatically.

## Integrity And Provenance

The historical tab-delimited archive directories do not publish per-file MD5 sidecars for this pair. The downloader therefore verifies each file against its configured official byte size and records a locally calculated SHA-256 checksum, source URL, release date, retrieval timestamp, and filename in a JSON sidecar.

The release date is the scientific snapshot date. The retrieval timestamp records when this project obtained the file and must not be used as the snapshot date.

## Processing Boundary

The next processing stage must read each gzip file in chunks and write a standardized subset without fully decompressing the archive to disk or loading the entire release into memory. Automatic matching and manual validation remain separate from downloading. At least 25 cross-release matches must be reviewed before the matching pipeline is accepted for baseline scoring.

## Official Sources

Accessed 2026-07-28:

- https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/
- https://www.ncbi.nlm.nih.gov/clinvar/docs/release_cycle/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/README
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/archive_2.0/
- https://ftp.ncbi.nlm.nih.gov/pub/clinvar/xml/
