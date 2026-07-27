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

`pilot_variants.csv` begins with five empty rows and the declared manual pilot columns. Use `scripts/pilot_mode.py` to plan one current API lookup. The script makes no request until `--confirm-api-requests` is provided. An optional explicit VCV version can supply a small historical record, but its date and scope still need manual verification.

`extracted/` is reserved for small reviewed records if they are needed later. Full archives do not belong there. `pilot_review.json` is created only when a person saves a dashboard review decision.

`pilot_variant_001.json` is the separate single-variant workflow record. It begins with
empty strings and lists. `select_pilot_variant.py` never changes it.
`run_pilot_workflow.py` writes it only after the current API request and the selection
are separately confirmed. An empty `historical_records_found` list means no historical
claim has been verified.

`pilot_workspace.json` is the canonical browser pilot list. It starts with zero
records and is limited to ten. Browser saves create `pilot_workspace.backup.json`,
which is ignored by Git, before atomically replacing the main file. Current fields,
manual past fields, exact classification categories, checklist answers, notes, sources,
statuses, and timestamps stay together in each record.
