# ClinVar Data Size Options

Date checked: 2026-07-26

No data file was downloaded for this comparison. Sizes came from official NCBI
directory listings and previously verified response headers. Sizes change as ClinVar
grows.

## Full ClinVar XML

- **Size:** The selected February 2024 VCV XML is 3,334,050,859 compressed bytes and
  the February 2025 file is 4,556,267,423 bytes. Together they are about 7.89 GB. The
  current July 2026 VCV XML is 5,824,540,370 bytes by itself.
- **Information:** This is the richest public format. It includes VCV records,
  submissions, classifications, record status, replacement information, and detailed
  evidence structures.
- **Historical use:** Monthly XML files are fixed and archived, so they support exact
  release comparisons.
- **Appropriate now:** No. The transfer is too large for the current pilot. Archive
  body scanning is paused.

## Tab-Delimited Summary Files

- **Size:** The current `variant_summary.txt.gz` is 441,043,744 bytes, about 441 MB.
  The earlier January 2022 and January 2024 files considered by this project are about
  95.8 MB and 223.6 MB.
- **Information:** Selected variant-level fields such as Variation ID, Allele ID,
  genomic location, aggregate classification, review status, gene, and condition.
  It does not include complete VCV, RCV, or SCV evidence and record history.
- **Historical use:** Archived monthly summary files can support a fixed historical
  comparison within their limited fields.
- **Appropriate now:** Not for the five-record pilot. These files are smaller than
  XML, but downloading millions of rows to inspect five variants is unnecessary.

## VCF Files

- **Size:** The current GRCh38 VCF listing is about 184 MB, with an index of about
  596 KB. Historical VCF files are also archived.
- **Information:** Mapped simple alleles under 10 kb with precise endpoints and
  selected ClinVar annotations. It excludes some large, complex, cytogenetic,
  haplotype, genotype, and imprecisely mapped records. VCF coordinates are
  left-shifted, unlike the HGVS-style locations in other ClinVar files.
- **Historical use:** A complete archived VCF is a dated snapshot, but its coverage
  is incomplete. A remote indexed range query may retrieve a small genomic region if
  the coordinate and assembly are already known and the server supports byte ranges.
- **Appropriate now:** Possibly later for a coordinate check. It is not the best first
  source for record history or for selecting variants by Variation ID.

## API Lookup

- **Size:** One ESummary response is usually measured in kilobytes. Pilot planning
  reserves at most 1 MB. One versioned VCV EFetch response is capped locally at 10 MB.
- **Information:** ESummary provides a current overview for one Variation ID. EFetch
  can provide one current or explicitly versioned VCV XML record. NCBI documents both
  methods as official programmatic access.
- **Historical use:** A specified VCV version is historical information, but its
  version must be linked to a date and reviewed. It must not be described as an
  arbitrary monthly snapshot without evidence that the version was active then.
- **Appropriate now:** Yes. This is the recommended pilot method because it retrieves
  only records that were manually selected.

## Other Small Approaches

- **ClinVar web record review:** Useful for selecting a variant and reading visible
  record history. Save the exact URL, access date, and notes. Manual web review is not
  a substitute for a fixed bulk release, but it is practical for five records.
- **Versioned VCV EFetch:** The strongest small official option found. Request a VCV
  accession with an explicit version, save only that XML record, and verify its date
  and classification scope by hand.
- **Remote indexed VCF query:** Can be low bandwidth for known coordinates. It needs
  assembly-aware tools and does not cover all ClinVar records.
- **Ask NCBI or use a prepared subset:** A documented official subset would be useful
  if one becomes available. An unknown third-party subset should not replace source
  verification.

## Recommendation

For a student project with limited bandwidth, begin with five manually selected
variants. Use ESummary for each current record. If a useful explicit VCV version can
be identified, use versioned EFetch with a 10 MB cap and manually verify its date,
condition scope, and classification. Keep unverified historical fields blank.

Do not download full XML, summary, or VCF files for this pilot. After the workflow is
correct for five to ten variants, reconsider an indexed query, a small approved
summary file, or a larger release only if the scientific question truly requires it
and the transfer is explicitly approved.
