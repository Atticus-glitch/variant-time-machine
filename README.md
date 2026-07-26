# Variant Time Machine

**Early research and development: results are not yet available.**

Variant Time Machine is a computational genetics research project that asks whether information available about a ClinVar variant at an earlier date can help predict its later classification. I plan to follow variants first labeled as variants of uncertain significance (VUS), build a carefully dated dataset, and compare explainable prediction methods. The goal is to help prioritize research questions, not to make clinical decisions.

> This project is for research and education only. It is not a medical device, does not provide diagnoses, and must not be used to make healthcare decisions.

## Research Question

**Using only information that was available at an earlier point in time, can an explainable computational model predict whether a ClinVar variant of uncertain significance will later be reclassified as harmful, harmless, or remain uncertain?**

## Current Status

The repository now contains a bounded historical XML pilot. Sixteen real current ClinVar records were selected through official NCBI ESummary, but their historical fields remain blank because no archived XML body has been processed. The project can inspect source metadata, stream only requested records after explicit confirmation, compare exact Variation IDs, and save human review decisions. No biological claims or models exist.

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

The command refuses to replace an existing output unless `--overwrite` is supplied. The configured downloader also requires `--confirm-large-download`; no download occurs during imports, tests, or setup validation.

## Local Dashboard

Start the development dashboard from the repository root:

```bash
python scripts/start_dashboard.py
```

Then open `http://127.0.0.1:5000` in a browser. The dashboard uses synthetic test data and must not be presented as scientific results.

The dashboard also provides a one-record connection to the official current ClinVar API at `http://127.0.0.1:5000/variant_lookup.html` and the manual Historical Pilot at `http://127.0.0.1:5000/historical_pilot.html`. See [`docs/clinvar-api.md`](docs/clinvar-api.md) for supported identifiers and limitations.

Start a manual historical review with:

```bash
python scripts/review_variant.py 14206
```

The command displays current ClinVar information and an unchecked archive-verification checklist. It does not add a row or claim that the variant changed.

## Historical XML Pilot

First inspect the official release headers and MD5 text files. This does not request an archive body:

```bash
python scripts/extract_pilot_history.py --dry-run
```

The selected compressed files are 3.33 GB and 4.56 GB. A scan may stop early, but it can transfer about 7.89 GB if records are missing or late. Start extraction only after reviewing that cost:

```bash
python scripts/extract_pilot_history.py --confirm-large-transfer
```

To impose a smaller hard transfer limit on each release:

```bash
python scripts/extract_pilot_history.py \
  --confirm-large-transfer \
  --max-transfer-gb 1
```

Hitting a limit is reported as a failed extraction. It is not a partial result. Full archives are not saved.

## Current Milestone

Produce a verified table connecting variants labeled uncertain in one archived ClinVar release with their classifications in a later release. No machine-learning claims will be made until the matching process has been checked carefully.

## Reproducibility

The goal is for every data transformation, matching decision, feature definition, and model evaluation to be documented and reproducible from versioned code and recorded source releases. Raw public datasets will remain outside Git because of their size; their URLs, release dates, checksums where available, and retrieval dates will be recorded.

## Ethics and Medical Disclaimer

Only public or appropriately accessible non-identifiable data are planned. The project does not recruit human participants, collect medical records, or modify organisms. Database classifications may conflict, change, or contain biases, so findings will be limited to the datasets and dates actually tested.

## License

Source code and original project documentation are available under the [MIT License](LICENSE). External datasets retain their own terms and licenses.
