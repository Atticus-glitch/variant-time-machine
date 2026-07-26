# Local Development Dashboard

This simple Flask dashboard helps a new researcher understand what Variant Time Machine does, what has been built, and what should happen next. It is not the final public website, a medical tool, or a report of scientific results.

## Start the Dashboard

From the repository root:

```bash
source .venv/bin/activate
python scripts/start_dashboard.py
```

Open this address in a browser:

```text
http://127.0.0.1:5000
```

You can also run:

```bash
python website/dashboard/app.py
```

Press `Ctrl+C` in the server terminal when you want to stop it.

## What Each Section Means

- What Is This Project? gives the research question in plain language.
- Project Progress shows the nine major steps and whether each is `Not Started`, `Working`, or `Complete`.
- Fake Example Dataset shows the shape of a future comparison table. It reads `data/example_variants.csv`, which contains only invented examples.
- What Each Folder Does explains where plans, code, tests, data, outputs, and website files belong.
- Next Three Tasks gives a short list of reasonable scientific development steps.
- Computer Status reports the active Python environment and whether local data or timeline outputs exist.
- Latest Research Note displays the newest main entry from `research/research-notebook.md`.
- Live ClinVar Connection shows whether this dashboard session has completed a current one-record NCBI lookup.
- Historical Variant Comparison counts only complete rows in `data/manual_review/test_variants.csv`. It starts at zero by design.

## How This Helps Development

The dashboard makes project status visible without opening many files or pretending unfinished work is complete. It separates software progress from scientific progress and keeps future machine learning steps visible but inactive.

The browser loads information from these Flask API endpoints:

- `/api/status`
- `/api/progress`
- `/api/dataset`
- `/api/clinvar/status`
- `/api/clinvar/lookup?variant_id=14206`

The separate browser lookup is available at `http://127.0.0.1:5000/variant_lookup.html`. It requests one current record from the official NCBI ClinVar E-utilities API. It does not use the fake example CSV and does not download a database.

To update progress, edit `PROGRESS_ITEMS` in `website/dashboard/app.py`. Change a status only when the explanation is accurate. Do not mark historical comparison complete until real matches have been checked manually.

## Synthetic Data Rule

The dashboard dataset must remain labeled:

`Synthetic example data. Not real scientific results.`

The current example CSV is not produced from ClinVar and must not be cited as research evidence.
