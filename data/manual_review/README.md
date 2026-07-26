# Manual Review Data

This folder is reserved for small, real ClinVar examples used to test the historical comparison workflow.

These examples are not the final research dataset. They must not be used to claim a reclassification rate, model performance, or biological pattern.

Each variant must be manually verified before inclusion. A reviewer must check:

- the ClinVar Variation ID and Allele ID when available,
- the gene,
- the exact older release date and classification,
- the exact newer release date and classification,
- official archive or ClinVar source references,
- any conflicting evidence, changed identifiers, or uncertain matching.

`test_variants.csv` intentionally contains only a header. Do not add a row from memory, a search snippet, or an assumed history. Use `python scripts/review_variant.py <identifier>` to inspect the current record, then verify both historical snapshots separately before editing the CSV.

Every populated row is treated as manually verified by the dashboard. Therefore, incomplete or provisional work should remain in the research notebook rather than this table.

`pilot_variants.csv` is different. It contains 16 real current ESummary records selected on 2026-07-26, but its historical fields are blank. Inclusion in that file does not mean a historical match was verified.

`extracted/` is reserved for small JSON records, source manifests, and automatic comparisons created by the confirmed streaming command. Full archives do not belong there. `pilot_review.json` is created only when a person saves a dashboard review decision.
