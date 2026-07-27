# ClinVar API Connections

## Two Current Lookups

The dashboard uses only official NCBI E-utilities, with a local plan and explicit
approval before every network operation. It does not scrape pages or contact a
third-party service.

The optional candidate helper uses ESearch and ESummary:

- ESearch accepts one strictly validated gene symbol and returns at most five current ClinVar identifiers.
- Each candidate is retrieved by an individual ESummary request. A Variation ID or VCV entered in the older lookup workflow is normalized to a numeric Variation ID and also retrieved individually.
- ESummary supplies a small current aggregate overview: Variation ID, current VCV accession/version when present, genes, aggregate germline classification, conditions, review status, limited evidence metadata, official source URL, retrieval time, and measured JSON bytes.
- ESummary is useful for finding candidates, but it is not the official VCV history response and does not establish a historical classification.

The Version History Explorer uses official VCV EFetch XML:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
```

It first requests the unversioned VCV accession to establish the latest official
accession and version. Only then can it plan exact historical requests. `all`
requests versions 1 through latest, `custom` requests an inclusive integer range,
and `endpoints` requests version 1 and latest (or only version 1 when latest is 1).
Each historical version is a separate request such as `VCV000014206.1`.

## Strict Validation

VCV input must exactly match uppercase `VCV#########` with nine digits and an
optional positive version suffix, for example `VCV000014206` or
`VCV000014206.1`. `VCV000000000`, lowercase or unpadded accessions, whitespace,
zero/negative versions, URLs, RCV/SCV accessions, rs identifiers, free text, and
shell-like input are rejected.

The dashboard accepts an optional suffix but normalizes the current lookup to the
base accession: it always runs unversioned EFetch to discover the latest version
before planning history. The reusable history client can plan one supplied exact
version after that same current lookup. For every explicitly versioned request, a
response with a different accession version is recorded as `missing`, not silently
accepted.

## Request Bounds

- The initial unversioned current EFetch is separate from the limit of 25 historical version requests.
- Historical requests run sequentially, with 0.34 seconds of pacing before each request.
- Connect timeout is 10 seconds and read timeout is 30 seconds.
- The session permits two limited retries for connect/read failures and HTTP 429, 500, 502, 503, and 504 responses, with backoff. Only GET requests are retried.
- Each streamed response has a 10 MiB (10,485,760-byte) hard cap, approximately 10 MB.
- The complete current-plus-history result has a 50 MiB (52,428,800-byte) hard cap. The dashboard describes this as one exploration's maximum.
- Cancellation is checked before retrieval and between version requests. It cannot interrupt an HTTP request already in progress; that request finishes safely before cancellation takes effect.
- Only one dashboard history exploration can run at a time.

The server reconstructs the plan from validated input when exploration begins and
rejects a submitted version list that does not match. `all` fails when the latest
version would require more than 25 historical requests; the user must choose a
custom range or endpoints. No full-archive request is available in the dashboard.

## Parsed EFetch Fields

The namespace-tolerant XML parser records the VCV accession/version, Variation ID,
record type, genes, the first parsed variant name, HGVS expressions, creation/update/deletion
dates, conditions, record status, replacement metadata, deleted state, and warnings.
It deliberately keeps three classification categories separate:

- germline classification, review status, last-evaluated date, and submission count;
- somatic clinical impact with its own corresponding metadata;
- oncogenicity classification with its own corresponding metadata.

Missing fields remain missing and produce warnings where relevant. Outcomes are
`available`, `missing`, `deleted/replaced`, `request failure`, or `parsing failure`.
Decoded XML text and exact source/retrieval provenance are retained locally when a
response body was received; the public API response omits raw XML.

## Failure Handling

Invalid input and invalid plans fail before network access. HTTP/network failures,
oversized responses, no-record responses, malformed XML, accession-version
mismatches, and total-limit failures remain explicit; the software does not create
substitute data. Transfer-limit failures stop the operation. A cancelled partial
exploration is saved only if at least one historical response was received.

## Why VCV History

Exact VCV versions provide a low-bandwidth way to inspect how one aggregate ClinVar
variant record changed and can reveal classification, review, submission, condition,
replacement, or metadata changes. They are useful for selecting and manually
validating a small historical pilot.

A VCV version is not a complete monthly ClinVar snapshot: versions change when
record content changes, not on a monthly schedule, and a version alone does not
prove what was visible at an arbitrary calendar cutoff. Eventual archived monthly
summaries or releases may still be needed for release-wide cohort selection and
date-specific reconstruction.

Official documentation:

- https://www.ncbi.nlm.nih.gov/clinvar/docs/programmatic_access/
- https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/

Sources accessed 2026-07-26 and 2026-07-27.
