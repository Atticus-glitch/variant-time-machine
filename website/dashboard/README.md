# Local Development Dashboard

This local Flask dashboard is the normal bounded VCV history workflow. Its startup target is **Pilot Results**, a preliminary descriptive result rather than a final study or medical tool.

## Start the Dashboard

From the repository root:

```bash
.venv312/bin/python scripts/start_dashboard.py
```

After the documented Python 3.12 installation succeeds, that command is recommended.
The current `.venv` is Python 3.14.4, not Python 3.12; use
`.venv/bin/python scripts/start_dashboard.py` only as a temporary fallback.

Pilot Results normally opens automatically at:

```text
http://127.0.0.1:5000/pilot_results.html
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

The initial latest-version lookup is separate from the maximum 25 historical requests. Requests use 0.34-second sequential pacing, 10-second connect and 30-second read timeouts, and two limited retries for connection/read errors and selected transient statuses. Each response has a 10 MiB hard cap (approximately 10 MB); one exploration has a 50 MiB hard cap. Only official NCBI ESearch, ESummary, and EFetch endpoints are used in this workflow. The separate Historical Dataset Builder controls the fixed archived summary pair.

## What Each Section Means

- What Is This Project? gives the research question in plain language.
- Project Progress shows the seven current stages and whether each is `Not Started`, `Working`, or `Complete`.
- Fake Example Dataset shows the shape of a future comparison table. It reads `data/example_variants.csv`, which contains only invented examples.
- What Each Folder Does explains where plans, code, tests, data, outputs, and website files belong.
- Next Three Tasks gives a short list of reasonable scientific development steps.
- Computer Status reports the active Python environment and whether local data or timeline outputs exist.
- Latest Research Note displays the newest main entry from `research/research-notebook.md`.
- Live ClinVar Connection shows whether this dashboard session has completed a current one-record NCBI lookup.
- Historical Variant Comparison counts only browser workspace records that passed every verification rule. It starts at zero by design.
- Data Transfer Safety shows the largest planned request, current transfer, total raw download size, data storage use, and that large-download protection is on.
- Version History Explorer is the main control center for current VCV confirmation, exact version plans, progress, cancellation, saved histories, automatic timelines, and ten-item manual verification.
- Pilot Results shows the real aggregate summary, batch transfer plan, timelines, review controls, and five downloadable outputs.
- Historical Dataset Builder shows the exact fixed release pair, live disk calculation, automatic safety limit, and one-use download confirmation.
- Variant Spreadsheet pages through the full local two-release index and opens a two-card timeline with all collapsed fields for one Variation ID.
- Start Here is the recommended landing page. It reports the live older-VUS update queue and presents the review workflow and site map on one page.
- Prediction Results displays the frozen Clue Score V1 formula, real metrics, review-priority list, complete point calculations, sparse manual review controls, rerun progress, and generated downloads.
- Pilot Workspace remains available for the older current-record/manual-date workflow.

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

The separate browser lookup and Pilot Workspace remain available, but normal pilot work should use the Version History Explorer. Current ESummary candidate results are not historical results, and VCV versions are not monthly snapshots.

Pilot Workspace records are stored in `data/manual_review/pilot_workspace.json`. Each change uses validation, a backup, and an atomic file replacement. The workspace stores no secrets and runs no shell commands. The Historical Dataset Builder is separate and permits only the configured 319,441,148-byte compressed TSV pair; the multi-gigabyte XML strategy remains paused.

Version-history artifacts are stored under the Git-ignored `data/manual_review/vcv_history/<VCV>/` layout documented in `data/manual_review/README.md`. Automatic parsed data and XML are never overwritten by manual corrections; review annotations and status remain in `review.json`.

To update progress, edit `PROGRESS_ITEMS` in `website/dashboard/app.py`. Change a status only when the explanation is accurate. Do not mark historical comparison complete until real matches have been checked manually.

## Synthetic Data Rule

The dashboard dataset must remain labeled:

`Synthetic example data. Not real scientific results.`

The current example CSV is not produced from ClinVar and must not be cited as research evidence.
