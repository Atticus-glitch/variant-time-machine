# Variant Time Machine

**Early research and development — results are not yet available.**

Variant Time Machine is a computational genetics research project investigating whether information available about a ClinVar variant at an earlier date can predict its later reclassification. The project will follow variants initially labeled as variants of uncertain significance (VUS), build a carefully time-stamped dataset, and compare explainable predictive approaches. Its purpose is to support research prioritization, not clinical decision-making.

> This project is for research and education only. It is not a medical device, does not provide diagnoses, and must not be used to make healthcare decisions.

## Research Question

**Using only information that was available at an earlier point in time, can an explainable computational model predict whether a ClinVar variant of uncertain significance will later be reclassified as harmful, harmless, or remain uncertain?**

## Current Status

The repository contains the initial project structure, research plan, documentation, validation tooling, and placeholders for the future data pipeline. No ClinVar releases have been selected or processed, and no models have been trained or evaluated.

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
- `scripts/`: command-line entry points and setup validation
- `notebooks/`: guidance for exploratory notebooks
- `tests/`: automated setup and package tests
- `outputs/`: generated figures, tables, and models
- `docs/`: data dictionary, methods, and limitations
- `website/`: future public explanation and demonstration

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python scripts/validate_setup.py
pytest
ruff check .
ruff format --check .
```

Run commands from the repository root. Initial setup and validation do not download ClinVar or any other large dataset.

## Current Milestone

Produce a verified table connecting variants labeled uncertain in one archived ClinVar release with their classifications in a later release. No machine-learning claims will be made until the matching process has been checked carefully.

## Reproducibility

The goal is for every data transformation, matching decision, feature definition, and model evaluation to be documented and reproducible from versioned code and recorded source releases. Raw public datasets will remain outside Git because of their size; their URLs, release dates, checksums where available, and retrieval dates will be recorded.

## Ethics and Medical Disclaimer

Only public or appropriately accessible non-identifiable data are planned. The project does not recruit human participants, collect medical records, or modify organisms. Database classifications may conflict, change, or contain biases, so findings will be limited to the datasets and dates actually tested.

## License

Source code and original project documentation are available under the [MIT License](LICENSE). External datasets retain their own terms and licenses.
