# ClinVar API Connection

## Purpose

The browser Pilot Workspace retrieves current ClinVar summaries without downloading a database. Before a request, a local planning route reports source, maximum estimated transfer, purpose, whether the action is small, and whether protection blocked it. The user must approve the plan before the backend contacts NCBI.

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

The Pilot Workspace search accepts:

- a numeric ClinVar Variation ID, such as `14206`
- a VCV accession, such as `VCV000014206` or `VCV000014206.1`
- a short gene symbol, such as `BRCA1`, which returns at most five current candidates

The VCV number is normalized to its numeric Variation ID before the request. Gene searches use an official ESearch query limited to five records. RCV accessions, SCV accessions, rs numbers, unrestricted free text, URLs, and shell-like input are not accepted.

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
- measured JSON response bytes when available.

The local `POST /api/clinvar/plan` route performs no external request. The approved `POST /api/clinvar/lookup` route accepts only validated query text and a true approval value. It never executes commands. The response includes the transfer source, estimate, actual bytes, purpose, small-request state, and protection result.

The evidence summary reports only metadata present in ESummary, such as the number of listed SCV and RCV accessions, last evaluation date, and molecular consequence. It does not summarize the scientific arguments inside individual submissions.

## Why Use This Instead of a Large Download

For learning and interface development, a one-record API call is faster, smaller, and easier to inspect than a complete ClinVar release. It proves that requests, validation, structured parsing, dashboard display, and failure reporting work with a real source.

Large archived files are still necessary later for reproducible historical comparison. The live API represents current ClinVar data and cannot replace fixed old and new snapshots for the main research question.

The pilot uses this endpoint for one manually selected current record at a time. Historical fields begin blank. NCBI also documents EFetch for one explicit VCV accession version. Pilot mode can request that small XML record, but a reviewer must establish its date and scope.

## Pilot Workspace

Start the dashboard once and use:

```text
http://127.0.0.1:5000/pilot_workspace.html
```

The browser is the normal interface for search, add, review, notes, sources, statuses, and timelines. The routes under `/api/pilot` write only the bounded local workspace file. There is no normal dashboard route for archive extraction.

## Optional Pilot Command

Display the five manual slots without a request:

```bash
python scripts/pilot_mode.py
```

Display one current API plan without starting it:

```bash
python scripts/pilot_mode.py 14206 --reason "Manually selected test record"
```

Add `--confirm-api-requests` only after reviewing the source, estimate, and reason. The optional `--historical-vcv` value must include a version. Full archive scanning is paused.

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

## Simple Browser Lookup

Start the dashboard and open:

```text
http://127.0.0.1:5000/variant_lookup.html
```
