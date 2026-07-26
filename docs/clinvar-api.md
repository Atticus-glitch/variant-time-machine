# ClinVar API Connection

## Purpose

The live lookup demonstrates that Variant Time Machine can communicate with a real genetics resource without downloading a large database. It retrieves one current ClinVar variant summary for research and development visibility.

This feature does not perform historical comparison, diagnosis, or machine learning.

## Official Connection

The project uses the NCBI Entrez E-utilities `esummary` endpoint:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi
```

The request specifies:

- database: `clinvar`
- one numeric ClinVar Variation ID
- JSON response format
- tool name: `variant_time_machine`

NCBI documents ClinVar support for `esearch`, `esummary`, `elink`, and `efetch`. This project uses `esummary` because it provides a small structured overview suitable for one-record testing. It does not scrape an HTML page.

Official documentation:

- https://www.ncbi.nlm.nih.gov/clinvar/docs/programmatic_access/
- https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/

Sources accessed 2026-07-26.

## Accepted Identifiers

The lookup accepts:

- a numeric ClinVar Variation ID, such as `14206`
- a VCV accession, such as `VCV000014206` or `VCV000014206.1`

The VCV number is normalized to its numeric Variation ID before the request. RCV accessions, SCV accessions, rs numbers, gene names, and free-text descriptions are not accepted by this first interface.

## Returned Fields

`src/variant_time_machine/clinvar_api.py` returns a `ClinVarVariant` record containing:

- variant identifier returned by NCBI,
- numeric Variation ID,
- gene symbol or symbols,
- current aggregate germline classification,
- associated germline conditions when listed,
- current aggregate germline review status,
- a short evidence metadata summary when available,
- official ClinVar source URL,
- UTC retrieval time.

The evidence summary reports only metadata present in ESummary, such as the number of listed SCV and RCV accessions, last evaluation date, and molecular consequence. It does not summarize the scientific arguments inside individual submissions.

## Why Use This Instead of a Large Download

For learning and interface development, a one-record API call is faster, smaller, and easier to inspect than a complete ClinVar release. It proves that requests, validation, structured parsing, dashboard display, and failure reporting work with a real source.

Large archived files are still necessary later for reproducible historical comparison. The live API represents current ClinVar data and cannot replace fixed old and new snapshots for the main research question.

The pilot list uses this endpoint for 16 current candidate records. Historical fields are deliberately blank. A separate confirmed streaming command reads the official February 2024 and February 2025 VCV XML archives. API and archive values are never substituted for one another.

## Archived XML Command

Inspect source headers and official MD5 text without requesting archive bodies:

```bash
python scripts/extract_pilot_history.py --dry-run
```

Only after reviewing the possible 7.89 GB transfer, run:

```bash
python scripts/extract_pilot_history.py --confirm-large-transfer
```

An optional `--max-transfer-gb` limit applies to each release. Hitting the limit is a safe failure, not a partial scientific result.

## Failure Handling

The client reports separate errors for:

- an invalid identifier,
- no ClinVar record,
- network or HTTP failure,
- malformed or incomplete JSON.

If the internet or NCBI service is unavailable, the script and dashboard say the connection failed. They do not create substitute data.

## Limitations

- The response reflects current ClinVar, not an archived release.
- ClinVar classifications are submitted by outside organizations and may conflict or change.
- ESummary is an overview and does not include all evidence in full VCV, RCV, or SCV records.
- Some fields may be missing.
- The first client supports one identifier per request and does not implement bulk lookup.
- Repeated automated use must follow NCBI rate and usage guidance.
- This information is not medical advice and must not be used for healthcare decisions.

## Run the Command-Line Test

```bash
python scripts/test_clinvar_connection.py
```

Use another supported identifier:

```bash
python scripts/test_clinvar_connection.py VCV000014206
```

## Use the Browser Lookup

Start the dashboard and open:

```text
http://127.0.0.1:5000/variant_lookup.html
```
