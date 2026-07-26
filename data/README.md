# Data Directory

No scientific data are included during project setup.

- `raw/`: immutable downloaded source releases. Never edit raw files in place.
- `interim/`: parsed or partially matched data that are not analysis-ready.
- `processed/`: documented, quality-checked datasets used for analysis.

Large data files are ignored by Git. Each future download must record its official source URL, release date, retrieval date, format, file size, checksum when available, and applicable terms. Generated files should be reproducible from code rather than manually edited. Small synthetic fixtures may later be committed in a clearly labeled test-data location; they must never be presented as real results.

`interim/example_clinvar_timeline.csv` is a committed synthetic software fixture. Every row is labeled `SYNTHETIC TEST DATA - NOT SCIENTIFIC RESULTS`. It does not contain real ClinVar records and must not be used to support a scientific claim.

`example_variants.csv` is a simpler fake dataset used only by the local beginner dashboard. Every row is labeled `Synthetic example data. Not real scientific results.`

`manual_review/` is reserved for small real examples that have been checked against official historical sources. Its CSV begins with no data rows because no historical comparison has been manually verified yet.

`manual_review/pilot_variants.csv` contains 16 official current ESummary records and blank historical columns. It is a candidate list, not a verified timeline. `manual_review/extracted/` may contain only small bounded outputs and manifests from the pilot streaming command. Full ClinVar XML archives are not retained.
