# Data Directory

`pilot_results/` contains the small derived real-pilot CSV, JSON, Markdown, transfer,
and manual-review outputs. These are official-record research outputs, not synthetic
examples, model-training data, or clinical results. Small raw VCV XML responses remain
Git-ignored under `manual_review/vcv_history/`.

No scientific data are included during project setup.

- `raw/`: immutable downloaded source releases. Never edit raw files in place.
- `interim/`: parsed or partially matched data that are not analysis-ready.
- `processed/`: documented, quality-checked datasets used for analysis.

Large data files are ignored by Git. Each future download must record its official source URL, release date, retrieval date, format, file size, checksum when available, and applicable terms. Generated files should be reproducible from code rather than manually edited. Small synthetic fixtures may later be committed in a clearly labeled test-data location; they must never be presented as real results.

`interim/example_clinvar_timeline.csv` is a committed synthetic software fixture. Every row is labeled `SYNTHETIC TEST DATA - NOT SCIENTIFIC RESULTS`. It does not contain real ClinVar records and must not be used to support a scientific claim.

`example_variants.csv` is a simpler fake dataset used only by the local beginner dashboard. Every row is labeled `Synthetic example data. Not real scientific results.`

`manual_review/` is reserved for small real examples that have been checked against official historical sources. Its CSV begins with no data rows because no historical comparison has been manually verified yet.

`manual_review/pilot_variants.csv` contains five empty rows ready for manually selected real variants. Empty cells contain no scientific data. Pilot mode may add one current API record and one optional versioned VCV source at a time. Full ClinVar XML archives are not downloaded or retained.

`manual_review/pilot_workspace.json` is the active browser list. It begins with zero
records and stores up to ten current lookups and manual reviews. The CSV remains an
optional command-line template rather than the dashboard's main data store.
