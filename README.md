# Variant Time Machine

**Early research and development: frozen rule-based and learned-model results are preserved while validation and error analysis continue.**

Variant Time Machine is a computational genetics research project that asks whether information available about a ClinVar variant at an earlier date can help predict its later classification. I started with a simple clue score, then kept rebuilding the experiment whenever a result exposed a better question. The goal is to learn how to design a careful historical study and prioritize research questions, not to make clinical decisions.

> This project is for research and education only. It is not a medical device, does not provide diagnoses, and must not be used to make healthcare decisions.

## Research Question

**Among variants that were uncertain in the January 2022 snapshot and known to have a clear benign or pathogenic aggregate outcome by January 2024, can older-only information predict the direction of that change?**

The broader long-term question also includes variants that remain uncertain, but the current V2-V6 experiment does not answer that question.

## Current Status

The project now has indexed January 2022 and January 2024 ClinVar summary snapshots. Frozen **Clue Score V1** and **Resolved Direction V2** remain available as hand-scored baselines. The neural experiments were deliberately preserved rather than overwritten:

| Model | Test design | n | Accuracy | Balanced accuracy | Benign recall | Pathogenic recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| V4 | Internal connected-group holdout | 100 | 76.0% | 62.5% | 100.0% | 25.0% |
| V5 | Different internal connected-group holdout | 100 | 82.0% | 82.2% | 81.5% | 82.9% |
| V6 | New groups excluded before V6 fitting | 1,000 | 75.6% | 74.4% | 77.6% | 71.1% |

V6 was trained from scratch on 2,518 records after reserving 1,000 test representatives, quarantining 4,672 connected companions, and excluding 628 records in prior V4/V5 test groups. Its train/test Variation ID overlap and connected-group overlap are both zero. V5 still has the highest point score on its own small test, while V6 supplies much stronger sample-size evidence and a more modest estimate. Since the cohorts and training memberships differ, there is **no stable winner** and the scores should not be subtracted as a head-to-head improvement. See the [full comparison](research/model-v4-v5-comparison.md).

## Research Workflow

1. Open **Model Versions** and review the frozen V1-V6 records, leakage audits, baselines, and provenance warnings.
2. Use **Prediction Explorer** to review wrong high-confidence V4-V6 predictions before easy correct examples.
3. Inspect every older-snapshot feature, warning, prediction, probability, and newer answer label.
4. Confirm Variation and Allele IDs, germline scope, conditions, and official ClinVar context.
5. Record reviewed, correctly matched, ambiguous, or excluded decisions separately from automatic results.
6. Use Version History Explorer only when exact available VCV versions can narrow the timeline.
7. Preserve all frozen versions and reserve new group-isolated cohorts for future validation; do not tune against the existing tests.

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

## Model Registry Reports

Rebuild the lightweight V1-V6 registry, standardized evaluations, leakage audits,
logs, comparison tables, error-analysis CSVs, and project timeline from existing
frozen artifacts without training or opening a new test set:

```bash
.venv312/bin/python scripts/build_model_registry.py
```

The temporary Python 3.14 fallback is `.venv/bin/python scripts/build_model_registry.py`.
The command does not copy large model binaries or source databases into Git.

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

Review V6's 244 errors, check probability calibration, and design a genuinely later untouched cohort before changing the model again.

The neural network adjusts internal weights by minimizing supervised classification loss on training examples. V6's 1,000 test records were excluded from V6 training by both Variation ID and connected group, but the test still comes from the already inspected Version 2 cohort. It is not independent temporal validation and still cannot predict whether resolution will happen.

## Reproducibility

The goal is for every data transformation, matching decision, feature definition, and model evaluation to be documented and reproducible from versioned code and recorded source releases. Raw public datasets will remain outside Git because of their size; their URLs, release dates, checksums where available, and retrieval dates will be recorded.

## Ethics and Medical Disclaimer

Only public or appropriately accessible non-identifiable data are planned. The project does not recruit human participants, collect medical records, or modify organisms. Database classifications may conflict, change, or contain biases, so findings will be limited to the datasets and dates actually tested.

## License

Source code and original project documentation are available under the [MIT License](LICENSE). External datasets retain their own terms and licenses.
