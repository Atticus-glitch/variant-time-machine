# Variant Time Machine

**Early research and development: rule-based baselines are preserved and a learned-weight experiment is being added.**

Variant Time Machine is a computational genetics research project that asks whether information available about a ClinVar variant at an earlier date can help predict its later classification. I plan to follow variants first labeled as variants of uncertain significance (VUS), build a carefully dated dataset, and compare explainable prediction methods. The goal is to help prioritize research questions, not to make clinical decisions.

> This project is for research and education only. It is not a medical device, does not provide diagnoses, and must not be used to make healthcare decisions.

## Research Question

**Using only information that was available at an earlier point in time, can an explainable computational model predict whether a ClinVar variant of uncertain significance will later be reclassified as harmful, harmless, or remain uncertain?**

## Current Status

The project now has indexed January 2022 and January 2024 ClinVar summary snapshots. Frozen **Clue Score V1** and **Resolved Direction V2** remain available as hand-scored baselines. **Statistical Model V3** learned logistic-regression coefficients and completed its grouped holdout. **AI Holdout V4** is a separate small neural network that receives all eleven older-only hint indicators. Exactly 100 variant records are reserved for a website-triggered test, and related-gene companions are quarantined from training. All versions remain conditional exploratory research, not clinical claims.

## Research Workflow

1. Open **Prediction Results** and read the frozen changed-outcome Version 2 formula.
2. Review wrong high-confidence predictions before easy correct examples.
3. Open a result and inspect every older clue, point, warning, threshold, normalized answer, and date label.
4. Confirm Variation and Allele IDs, germline scope, conditions, and official ClinVar context.
5. Record reviewed, correctly matched, ambiguous, or excluded decisions separately from automatic results.
6. Use Version History Explorer only when exact available VCV versions can narrow the timeline.
7. Preserve Versions 1 and 2; train Version 3 only on its training partition and reserve a future cohort for truly independent validation.

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

Python 3.12 is the required reproducible environment. This system is Ubuntu 26.04
LTS, `python3.12` is not installed, and the existing `.venv` uses Python 3.14.4.
Migration was **not successful**, so do not claim that Python 3.12 is active.

Review the third-party `uv` installer before running it. The safe user-level setup
commands are:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv python install 3.12
~/.local/bin/uv venv --python 3.12 .venv312
~/.local/bin/uv pip install --python .venv312/bin/python -e '.[dev]'
.venv312/bin/python scripts/validate_setup.py
.venv312/bin/python -m pytest
.venv312/bin/ruff check .
.venv312/bin/ruff format --check .
```

Run commands from the repository root. No privileged commands were run. Initial
setup and validation do not download ClinVar or any other large dataset. Do not
remove `.venv` until `.venv312` passes every command above.

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

After installing into `.venv312`, start the dashboard from the repository root:

```bash
.venv312/bin/python scripts/start_dashboard.py
```

The server opens **Pilot Results** at `http://127.0.0.1:5000/pilot_results.html`. Use `.venv312/bin/python scripts/start_dashboard.py --no-browser` when automatic browser opening is not wanted. Until the Python 3.12 migration succeeds, `.venv/bin/python scripts/start_dashboard.py` is only a temporary current fallback; it uses Python 3.14.4 and must not be described as Python 3.12.

Normal pilot research happens in the **Version History Explorer**. Its optional gene search uses current ESearch plus individual ESummary lookups for at most five candidates. The history itself uses EFetch: it first requests the unversioned VCV to learn the latest official version, then offers all versions, a custom inclusive range, or endpoints (version 1 and latest). It accepts only canonical uppercase `VCV#########` or `VCV#########.version` input; in the dashboard, a supplied suffix is validated but the current lookup still resolves the unversioned accession before history planning. Exact versioned EFetch responses are checked against the requested `.version`.

Each approved exploration uses only official NCBI endpoints, at most 25 historical version requests, sequential 0.34-second pacing, a 10-second connect and 30-second read timeout, and two limited retries for connection/read failures or HTTP 429, 500, 502, 503, and 504 responses. Every response has a 10 MiB hard cap (approximately 10 MB), and the complete exploration has a 50 MiB hard cap. Cancellation is checked between requests; it cannot interrupt the active HTTP request. There is no full-archive control.

Saved automatic XML, parsed records, comparisons, provenance, and a separate manual review live under the ignored `data/manual_review/vcv_history/<VCV>/` tree. Germline, somatic clinical impact, and oncogenicity remain separate. Manual corrections never overwrite automatic parsed fields, and `manually_verified` requires all ten checks.

The first live demonstration used `VCV000014026` (Variation ID 14026; TACR3). Official EFetch returned versions 1, 2, and 3. All three aggregate germline classifications were `Pathogenic`, so the software detected no germline classification change. Review status and submission count did change. The current lookup plus the three exact-version requests transferred 95,970 response bytes. This case still requires manual verification and is not evidence that the variant was formerly a VUS.

In the separate older Pilot Workspace, current lookup and manual historical verification remain different tasks: a past classification stays blank until a person records an official source, exact dates, category type, and review notes. Its `verified` status and the Version History Explorer's `manually_verified` status mean only that the applicable checklist was completed; neither means ClinVar is infallible.

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

Train AI Holdout V4 without opening its frozen 100-record test, then use the website once to reveal its accuracy on those unseen records.

The neural network adjusts internal weights by minimizing supervised classification loss on training examples. The 100-record test remains internal to the already inspected Version 2 cohort, so it is not pristine independent validation and still cannot predict whether resolution will happen.

## Reproducibility

The goal is for every data transformation, matching decision, feature definition, and model evaluation to be documented and reproducible from versioned code and recorded source releases. Raw public datasets will remain outside Git because of their size; their URLs, release dates, checksums where available, and retrieval dates will be recorded.

## Ethics and Medical Disclaimer

Only public or appropriately accessible non-identifiable data are planned. The project does not recruit human participants, collect medical records, or modify organisms. Database classifications may conflict, change, or contain biases, so findings will be limited to the datasets and dates actually tested.

## License

Source code and original project documentation are available under the [MIT License](LICENSE). External datasets retain their own terms and licenses.
