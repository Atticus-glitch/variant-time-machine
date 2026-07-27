# Local Development Dashboard

This simple Flask dashboard helps a new researcher understand what Variant Time Machine does, what has been built, and what should happen next. It is not the final public website, a medical tool, or a report of scientific results.

## Start the Dashboard

From the repository root:

```bash
source .venv/bin/activate
python scripts/start_dashboard.py
```

The Pilot Workspace normally opens automatically. Its address is:

```text
http://127.0.0.1:5000/pilot_workspace.html
```

To start without opening a browser:

```bash
python scripts/start_dashboard.py --no-browser
```

Press `Ctrl+C` in the server terminal when you want to stop it.

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
- Pilot Workspace is the main control center. It plans a small lookup before network access, adds current records, prevents duplicates, saves review drafts, enforces verification checks, and displays exact classification categories on a timeline.

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

The separate browser lookup remains available for simple current checks, but normal pilot work should use the Pilot Workspace. Current API results are not historical results. Command-line scripts remain optional developer tools for reproducibility and testing.

Pilot Workspace records are stored in `data/manual_review/pilot_workspace.json`. Each change uses validation, a backup, and an atomic file replacement. The workspace stores no secrets and runs no shell commands. It has no route or button for the paused multi-gigabyte archive scan.

To update progress, edit `PROGRESS_ITEMS` in `website/dashboard/app.py`. Change a status only when the explanation is accurate. Do not mark historical comparison complete until real matches have been checked manually.

## Synthetic Data Rule

The dashboard dataset must remain labeled:

`Synthetic example data. Not real scientific results.`

The current example CSV is not produced from ClinVar and must not be cited as research evidence.
