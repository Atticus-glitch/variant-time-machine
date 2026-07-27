# ClinVar Archive and Identifier Research

> Pilot update, 2026-07-26: this earlier TSV research remains background for a
> possible full-table study. The active pilot uses five empty manual slots and
> one-record API requests. See `historical-data-plan.md`.

Research performed 2026-07-26 using official NCBI sources. No ClinVar release files were downloaded.

## Selected Initial Releases

The initial comparison will use these monthly archived `variant_summary` snapshots:

| Role | Release date | Official file | Compressed size reported by NCBI |
| --- | --- | --- | --- |
| Older predictor snapshot | 2022-01-06 | [`variant_summary_2022-01.txt.gz`](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/variant_summary_2022-01.txt.gz) | 95,791,203 bytes |
| Newer outcome snapshot | 2024-01-04 | [`variant_summary_2024-01.txt.gz`](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/variant_summary_2024-01.txt.gz) | 223,649,945 bytes |

These dates are a project choice, not an NCBI recommendation. Both files are official first-Thursday monthly snapshots, are exactly two years apart, and precede the 2024-01-29 addition of somatic-classification columns to `variant_summary`. The interval may contain enough changes to study while avoiding that particular schema boundary. This assumption must be checked after the files are downloaded and their headers and class counts are inspected.

## Why Start With `variant_summary`

NCBI provides comprehensive XML, tab-delimited summaries, and partial VCF releases. The tab-delimited `variant_summary` file includes aggregate germline classification, review status, submitter count, identifiers, and genomic representations. It is substantially smaller and simpler than XML, making it appropriate for the first variant-level matching experiment. It does not contain complete submissions or reliable variant-condition histories, so later questions may require VCV or RCV XML.

ClinVar publishes weekly updates but archives the comprehensive monthly release from the first Thursday of each month. Historical tab-delimited files use the pattern:

```text
https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/<year>/variant_summary_<year-month>.txt.gz
```

## Identifier Findings

- `AlleleID` identifies an individual allele.
- `VariationID` identifies the classified set of one or more alleles and corresponds to the numeric part of a VCV accession for ordinary classified records.
- One Variation ID can contain multiple Allele IDs, and one Allele ID can participate in multiple Variation IDs, especially for complex or included records.
- VCV is a variant-level aggregate across conditions; RCV is a variant-condition aggregate; SCV is an individual submitted record.
- Accession versions change for defined record updates, but some NCBI annotation changes do not increment the version.
- `variant_summary` has separate assembly rows, commonly GRCh37 and GRCh38, that must not be counted as separate variants.
- Right-shifted `Start`/`Stop` fields and left-shifted VCF fields are different representations and must not be mixed.
- RCV accessions, phenotype text, gene, rs number, and coordinates are supporting evidence, not safe sole identifiers.

## Conservative Proof-of-Concept Rules

1. Collapse duplicate assembly rows for an `AlleleID` and `VariationID` pair.
2. Accept an exact `AlleleID + VariationID` pair as an identifier match.
3. If the Allele ID has exactly one later Variation ID, retain the candidate but label the Variation ID change explicitly.
4. If an Allele ID has multiple later candidates, report ambiguity rather than choosing one.
5. If a Variation ID points to a different Allele ID, report conflicting identifiers.
6. Do not automatically match included or complex identifiers.
7. Do not infer mergers, replacements, or deletions from absence or coordinate similarity. Those cases require VCV or RCV record-history information.
8. Do not assign harmful, harmless, or uncertain outcomes until classification mapping rules are separately reviewed.

The current code implements these identifier rules and a compressed-table parser. It has been tested only with synthetic fixtures and a tiny compressed test file. It has not been run on either selected real release, and coordinate fallback remains unimplemented.

## Known Limitations

- `variant_summary` includes variants with genomic locations and can contain multiple rows per biological allele because of assemblies.
- `ClinicalSignificance` is a variant-level aggregate and may combine evidence associated with different conditions.
- A missing later row could reflect deletion, replacement, changed mapping, or another change in the record's history.
- NCBI may modify archived files to remove private information that was submitted by mistake, so retrieval dates and checksums must be recorded.
- Current field documentation may differ from old headers; parsing must use each file's actual header rather than fixed column positions.
- File sizes are large enough that downloads should be deliberate, checked against the official listed size, hash-recorded, and excluded from Git.

## Official Sources

All sources were accessed 2026-07-26.

- [ClinVar release cycle](https://www.ncbi.nlm.nih.gov/clinvar/docs/release_cycle/)
- [Accessing and using ClinVar data](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/)
- [Guide to ClinVar FTP files](https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/)
- [ClinVar identifiers](https://www.ncbi.nlm.nih.gov/clinvar/docs/identifiers/)
- [ClinVar classification terms](https://www.ncbi.nlm.nih.gov/clinvar/docs/clinsig/)
- [Tab-delimited README and field definitions](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/README)
- [2022 tab-delimited archive listing](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/)
- [2024 tab-delimited archive listing](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/)
- [VCV XML schema 2.6](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/xsd_public/ClinVar_VCV_2.6.xsd)
- [RCV XML schema 2.3](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/xsd_public/RCV/ClinVar_RCV_2.3.xsd)
