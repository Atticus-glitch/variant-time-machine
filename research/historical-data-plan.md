# Historical ClinVar Data Plan

Date: 2026-07-26

## Immediate Goal

Test the historical workflow on 16 real current ClinVar records. Extract only those
records from two archived releases, compare exact Variation IDs, and manually review
every result. This is a small pilot, not a representative dataset and not input for
machine learning.

## Selected XML Releases

| Role | Release date | Official file | Compressed size | Official MD5 | Schema |
| --- | --- | --- | ---: | --- | --- |
| Older | 2024-02-01 | `xml/archive/2024/ClinVarVCVRelease_2024-02.xml.gz` | 3,334,050,859 bytes | `669267f97e208014ca04d629b6681cf6` | ClinVar VCV 2.0 |
| Newer | 2025-02-06 | `xml/ClinVarVCVRelease_2025-02.xml.gz` | 4,556,267,423 bytes | `9ab805f0abb0b72099bc90eb9474fa22` | ClinVar VCV 2.2 |

Both are official VCV XML releases from the same current format family. They use
different documented schema revisions, so the parser selects named XML elements and
tests missing fields. The earlier plan to begin with January 2022 and January 2024
`variant_summary` files remains useful for later full-table work, but it is not the
source pair for this record-history pilot.

## Storage and Bandwidth Rule

The source files total about 7.89 GB compressed. A scan may stop early when every
requested Variation ID is found, but early stopping is not guaranteed. Therefore:

1. `--dry-run` requests only headers and the small official MD5 text files.
2. Archive bodies are requested only with `--confirm-large-transfer`.
3. Compressed bytes are counted and can be stopped by `--max-transfer-gb`.
4. Retained JSON is limited by `--max-output-mb`, with a 50 MiB default per file.
5. Full gzip files and decompressed XML are never written to disk by this command.
6. Failed writes remove their temporary files.

## Pilot Records

`data/manual_review/pilot_variants.csv` contains 16 current records retrieved through
official NCBI ESummary on 2026-07-26. These current facts help identify records for the
pilot. They do not prove any historical value. All historical columns remain blank
until the archived XML is actually scanned.

## XML Fields

The stream reads one `VariationArchive` element at a time. It retains Variation ID,
VCV accession and version, record type, record status, allele IDs, genes, conditions,
and replacement metadata. Germline classification, somatic clinical impact, and
oncogenicity are stored in separate fields and are never combined.

## Matching and Review

An automatic match requires the same numeric Variation ID in both extracted files.
Missing records, unfamiliar statuses, and replacement metadata remain visible. The
software can label a germline classification as unchanged, changed, or unable to
verify, but every result stays `requires_manual_review`.

The dashboard review choices are `Not reviewed`, `Confirmed match`, `Needs follow-up`,
and `Rejected automatic match`. A reviewer must inspect both source records and their
scope before selecting a final review state. Automatic output is never described as a
scientifically verified result.
