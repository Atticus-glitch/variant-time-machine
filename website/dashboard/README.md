# Local Development Dashboard

This local Flask site starts at **Overview**, the canonical guide to the research question, evidence, and review flow. It keeps preliminary results, exact VCV history retrieval, manual review, and development status distinct; it is not a medical tool.

## Start the Dashboard

From the repository root:

```bash
.venv312/bin/python scripts/start_dashboard.py
```

After the documented Python 3.12 installation succeeds, that command is recommended.
The current `.venv` is Python 3.14.4, not Python 3.12; use
`.venv/bin/python scripts/start_dashboard.py` only as a temporary fallback.

Overview normally opens automatically at:

```text
http://127.0.0.1:5000/overview.html
```

To start without opening a browser:

```bash
.venv312/bin/python scripts/start_dashboard.py --no-browser
```

Press `Ctrl+C` in the server terminal when you want to stop it.

## Version History Workflow

1. Optionally plan and approve a gene search. ESearch returns at most five identifiers, followed by individual current ESummary requests; these are candidate hints, not history.
2. Enter canonical uppercase `VCV#########` or `VCV#########.version`, plan one official current VCV EFetch, and approve it. The route normalizes to the base accession and uses unversioned EFetch to establish the latest official version.
3. Choose `all`, `custom`, or `endpoints`. Custom is an inclusive integer range; endpoints means version 1 and the latest version. The server rebuilds and validates the plan before starting it.
4. Approve the exact list. Up to 25 historical versions are requested individually and sequentially from official NCBI EFetch. An exact `.version` response is rejected as missing if NCBI returns a different version.
5. Inspect the parsed timeline, warnings, source requests, and comparisons, then complete the separate manual review. A cancellation request takes effect between requests, after any active request finishes.

The initial latest-version lookup is separate from the maximum 25 historical requests. Requests use 0.34-second sequential pacing, 10-second connect and 30-second read timeouts, and two limited retries for connection/read errors and selected transient statuses. Each response has a 10 MiB hard cap (approximately 10 MB); one exploration has a 50 MiB hard cap. Only official NCBI ESearch, ESummary, and EFetch endpoints are used in this workflow. The separate Data Setup utility controls the fixed archived summary pair.

## Site Structure

- **Overview** is the canonical start. It states the purpose once, shows key evidence, and gives the three-step flow: find a variant, inspect evidence, and investigate history.
- **Variants** searches the full local two-release index in a compact six-column table; complete snapshot fields remain in the selected detail panel.
- **Results** has a V1-V8 selector backed by the frozen model registry. V2 retains its detailed searchable calculation workspace; later models link to their available record explorers without pretending that different cohorts form one leaderboard.
- **Models** is the authoritative location for V1-V8 metrics, leakage audits, comparison limits, and V8 claim boundaries.
- **V8 Result Summary** (`/v8_results.html`) is the screenshot-ready public aggregate with exact metrics, the same-record V7 caveat, 20 stable case studies, and whitelisted downloads.
- **Error Review** filters and pages V4-V8 predictions. Its prominent V8 link opens **V8 Manual Review** (`/v8_review.html`), a one-case workflow with timeline evidence, V8 feature contributions, computer-suggestion flags, structured V9 inclusion controls, immediate atomic saves, and progress counts.
- **V9 Dataset Review**, **V9 Model Training**, **V9 Results**, and **V9 Case Explorer** clearly show the current preparation-only state. Training, results, and case predictions remain locked because no final V9 exists.
- **Timeline** displays dated research and application milestones; only task status is editable.

The **Tools** group is consistent on every page:

- Version History is the promoted exact-history workflow for bounded current and historical VCV requests, saved timelines, and manual verification.
- Pilot Results shows the real aggregate summary, batch transfer plan, timelines, review controls, and five downloadable outputs.
- Legacy Manual Workspace preserves the older current-record/manual-date workflow but is not the recommended exact-history path.
- Data Setup shows the exact fixed release pair, live disk calculation, safety limit, and one-use download confirmation.
- Current Lookup requests one current ClinVar summary and does not establish history.
- Project Status shows the current result, current scientific boundary, and next step first. Development progress, synthetic examples, repository folders, transfer safety, system status, and notes remain available under a disclosure.

## How This Helps Development

The dashboard makes project status visible without opening many files or pretending unfinished work is complete. It separates software progress from scientific progress and keeps future machine learning steps visible but inactive.

The browser loads information from these Flask API endpoints:

- `/api/status`
- `/api/progress`
- `/api/dataset`
- `/api/clinvar/status`
- `/api/pilot`
- `/api/clinvar/plan`
- `POST /api/clinvar/lookup`
- `GET`, `POST`, and `PATCH` routes under `/api/pilot`
- `/api/transfer-safety`
- `POST /api/vcv-history/current-plan` and `/api/vcv-history/current`
- `POST /api/vcv-history/plan` and `/api/vcv-history/explore`
- `GET /api/vcv-history/operations/<operation_id>` and its cancellation route
- `GET /api/vcv-histories` and `GET /api/vcv-histories/<VCV>`
- `PATCH /api/vcv-histories/<VCV>/review`
- `POST /api/historical-dataset/plan` and `/api/historical-dataset/run`
- `GET /api/historical-dataset/operations/<operation_id>`
- `GET /api/historical-variants` and `/api/historical-variants/<VariationID>`
- `GET /api/predictions/summary`, `/api/predictions`, and `/api/predictions/<VariationID>`
- `POST /api/predictions/run`, operation progress, manual review, formula, and download routes
- `GET /api/v8/summary`, `/api/v8/case-studies`, `/api/v8/review-queue`, and `/api/v8/review-notes`
- `PATCH /api/v8/review/<VariationID>` and `GET /api/v8/download/<filename>`
- `GET /api/v9/dataset-summary` and `GET /api/v9/download/<filename>`
- `GET /api/v9/exploratory-summary` and `GET /api/v9/exploratory/download/<filename>`

The separate Current Lookup and Legacy Manual Workspace remain available, but normal exact-history work should use Version History. Current ESummary candidate results are not historical results, and VCV versions are not monthly snapshots.

Legacy Manual Workspace records are stored in `data/manual_review/pilot_workspace.json`. Each change uses validation, a backup, and an atomic file replacement. The workspace stores no secrets and runs no shell commands. Data Setup is separate and permits only the configured 319,441,148-byte compressed TSV pair; the multi-gigabyte XML strategy remains paused.

Version-history artifacts are stored under the Git-ignored `data/manual_review/vcv_history/<VCV>/` layout documented in `data/manual_review/README.md`. Automatic parsed data and XML are never overwritten by manual corrections; review annotations and status remain in `review.json`.

V8 review decisions are a separate structured audit. The API validates queue membership, reviewer identity, exact decision and error-category enums, inclusion booleans, corrected outcomes, note length, and required notes before atomically replacing only `v8_review_notes.json`; it never writes the temporal prediction CSV or frozen evaluation files. Run `scripts/build_v9_dataset.py` after review changes to refresh the derived V9 tables and manifest.

To update progress, edit `PROGRESS_ITEMS` in `website/dashboard/app.py`. Change a status only when the explanation is accurate. Do not mark historical comparison complete until real matches have been checked manually.

## Synthetic Data Rule

The dashboard dataset must remain labeled:

`Synthetic example data. Not real scientific results.`

The current example CSV is not produced from ClinVar and must not be cited as research evidence.
