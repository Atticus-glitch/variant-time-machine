# Variant Time Machine

**Early research and development: results are not yet available.**

Variant Time Machine is a computational genetics research project that asks whether information available about a ClinVar variant at an earlier date can help predict its later classification. I plan to follow variants first labeled as variants of uncertain significance (VUS), build a carefully dated dataset, and compare explainable prediction methods. The goal is to help prioritize research questions, not to make clinical decisions.

> This project is for research and education only. It is not a medical device, does not provide diagnoses, and must not be used to make healthcare decisions.

## Research Question

**Using only information that was available at an earlier point in time, can an explainable computational model predict whether a ClinVar variant of uncertain significance will later be reclassified as harmful, harmless, or remain uncertain?**

## Current Status

The project intentionally begins with a small pilot dataset to validate methods before considering larger historical releases. The local dashboard is now the main pilot interface. It can plan and approve small current lookups, add up to ten variants, save manual historical review, enforce verification checks, and display an honest timeline. No historical result is assumed in advance, no biological claims have been made, and no models exist.

## Planned Workflow

1. Select an archived ClinVar release and a newer comparison release.
2. Identify variants classified as uncertain in the older release.
3. Match those variants across time using stable identifiers and verified genomic information.
4. Assign later outcomes while preserving ambiguous and unusable cases for review.
5. Construct features using only information available at the prediction date.
6. Compare simple baselines, a biological score, logistic regression, and possibly a tree-based model.
7. Evaluate on held-out variants or time periods with classification and calibration metrics.
8. Communicate methods, limitations, and individual model explanations through a public demonstration.

## Repository Structure

- `research/`: research plan, notebook, decisions, sources, and competition notes
- `data/`: local raw, interim, and processed data areas; downloaded data are not committed
- `src/variant_time_machine/`: installable Python package and future pipeline modules
- `scripts/`: setup validation, explicit downloading, and timeline construction commands
- `notebooks/`: guidance for exploratory notebooks
- `tests/`: automated setup and package tests
- `outputs/`: generated figures, tables, and models
- `docs/`: data dictionary, methods, and limitations
- `website/`: local development dashboard and future public website area

## Setup

Python 3.12 is the required reproducible environment. The current VM does not yet
have Python 3.12 installed, so migration is not complete and the existing `.venv`
has been kept unchanged.

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python scripts/validate_setup.py
pytest
ruff check .
ruff format --check .
```

Run commands from the repository root. Initial setup and validation do not download ClinVar or any other large dataset.

On this Ubuntu 26.04 VM, `python3.12` was not installed or listed by the configured
APT repositories. One user-level option is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv python install 3.12
~/.local/bin/uv venv --python 3.12 .venv312
source .venv312/bin/activate
~/.local/bin/uv pip install --python .venv312/bin/python -e ".[dev]"
```

Review third-party installer commands before running them. Do not remove `.venv`
until `.venv312` passes setup validation and all tests.

## Timeline Command

Build a timeline from two standardized CSV files:

```bash
python scripts/build_timeline_dataset.py older.csv newer.csv \
  --output outputs/tables/clinvar_timeline.csv
```

For raw archived `variant_summary` files, provide the release dates explicitly:

```bash
python scripts/build_timeline_dataset.py \
  data/raw/variant_summary_2022-01.txt.gz \
  data/raw/variant_summary_2024-01.txt.gz \
  --older-release-date 2022-01-06 \
  --newer-release-date 2024-01-04 \
  --output outputs/tables/clinvar_timeline.csv
```

The command refuses to replace an existing output unless `--overwrite` is supplied. Every configured download requires explicit confirmation after showing its source, estimated size, and purpose. Downloads above 500 MB are protected by a hard large-download rule. No download occurs during imports, tests, or setup validation.

## Local Dashboard

Start the dashboard once from the repository root:

```bash
python scripts/start_dashboard.py
```

The server opens `http://127.0.0.1:5000/pilot_workspace.html` in the default browser. Use `python scripts/start_dashboard.py --no-browser` only when automatic browser opening is not wanted.

Normal pilot research happens in the **Pilot Workspace**. From the browser you can review a transfer estimate, approve a small current ClinVar lookup, add a record with a selection reason, edit past and newer classifications, save notes and sources, change review status, complete the verification checklist, and view a timeline. The dashboard never exposes the paused full-archive scan.

Current lookups and historical verification are different tasks. A current result can be saved immediately, but a past classification remains blank until a person records an official source, exact dates, category type, and review notes. `Verified` means all required fields and checklist items were completed; it does not mean ClinVar itself is infallible.

The dashboard also contains clearly labeled synthetic display data. Synthetic examples are software demonstrations and must not be presented as research results.

Start a manual historical review with:

```bash
python scripts/review_variant.py 14206
```

The command displays current ClinVar information and an unchecked archive-verification checklist. It does not add a row or claim that the variant changed.

## Optional Developer Commands

Command-line tools remain available for reproducibility, testing, and debugging. They are not required for normal pilot work.

See the five legacy CSV slots without making a network request:

```bash
python scripts/pilot_mode.py
```

Plan one current lookup. This prints the source, estimated size, and purpose, then stops:

```bash
python scripts/pilot_mode.py 14206 --reason "Manually selected test record"
```

After reviewing the plan, make the small request explicitly:

```bash
python scripts/pilot_mode.py 14206 \
  --reason "Manually selected test record" \
  --confirm-api-requests
```

An optional `--historical-vcv VCV000014206.1` requests one explicit VCV version with a 10 MB limit. A versioned record still requires manual date, condition, and scope verification. It is not automatically equivalent to a monthly release.

The earlier 7.89 GB two-archive scan is paused and cannot be started by the archive inspection script. `python scripts/extract_pilot_history.py --dry-run` reads only headers and tiny MD5 files. See [`research/data-size-options.md`](research/data-size-options.md) for the alternatives.

## Optional Single-Variant Commands

Preview a candidate without accepting it:

```bash
python scripts/select_pilot_variant.py --variation-id 14206
```

Add `--confirm-api-requests` only after reviewing the displayed source, size, and
purpose. The selection tool can also use `--vcv VCV000014206` or `--gene BRCA1`. Gene
search returns at most five current candidates. Previewing never saves a pilot record.

Run the interactive workflow when one candidate has a clear selection reason:

```bash
python scripts/run_pilot_workflow.py
```

The command-line workflow confirms the small API request and asks again before selection. It saves `data/manual_review/pilot_variant_001.json` as a reproducible one-record artifact. The browser Pilot Workspace uses `data/manual_review/pilot_workspace.json` as its canonical multi-record store. Historical records remain empty until a person checks an official historical source.

## Current Milestone

Complete one source-backed historical review through the Pilot Workspace, then repeat the same checked method on a small set. The pilot dataset is not suitable for model training. No machine-learning work will begin until historical matching is reliable.

## Reproducibility

The goal is for every data transformation, matching decision, feature definition, and model evaluation to be documented and reproducible from versioned code and recorded source releases. Raw public datasets will remain outside Git because of their size; their URLs, release dates, checksums where available, and retrieval dates will be recorded.

## Ethics and Medical Disclaimer

Only public or appropriately accessible non-identifiable data are planned. The project does not recruit human participants, collect medical records, or modify organisms. Database classifications may conflict, change, or contain biases, so findings will be limited to the datasets and dates actually tested.

## License

Source code and original project documentation are available under the [MIT License](LICENSE). External datasets retain their own terms and licenses.
