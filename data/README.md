# Data Directory

No scientific data are included during project setup.

- `raw/`: immutable downloaded source releases. Never edit raw files in place.
- `interim/`: parsed or partially matched data that are not analysis-ready.
- `processed/`: documented, quality-checked datasets used for analysis.

Large data files are ignored by Git. Each future download must record its official source URL, release date, retrieval date, format, file size, checksum when available, and applicable terms. Generated files should be reproducible from code rather than manually edited. Small synthetic fixtures may later be committed in a clearly labeled test-data location; they must never be presented as real results.
