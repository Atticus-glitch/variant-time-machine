"""Simple local development dashboard for Variant Time Machine."""

import csv
import json
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.clinvar_api import (  # noqa: E402
    ClinVarAPIError,
    ClinVarConnectionError,
    ClinVarRecordNotFound,
    InvalidVariantIdentifier,
    lookup_clinvar_variant,
)
from variant_time_machine.config import (  # noqa: E402
    PILOT_EXTRACTED_DIR,
    PILOT_REVIEW_PATH,
    PILOT_VARIANTS_PATH,
    PILOT_XML_RELEASES,
    RAW_DATA_DIR,
    TABLES_DIR,
)
from variant_time_machine.pilot import (  # noqa: E402
    REVIEW_STATUSES,
    load_reviews,
    read_pilot_rows,
    save_review,
)

SYNTHETIC_NOTICE = "Synthetic example data. Not real scientific results."
EXAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "example_variants.csv"
NOTEBOOK_PATH = PROJECT_ROOT / "research" / "research-notebook.md"
MANUAL_REVIEW_PATH = PROJECT_ROOT / "data" / "manual_review" / "test_variants.csv"

PROJECT_EXPLANATION = (
    "Variant Time Machine asks whether information available about an uncertain "
    "genetic variant at an earlier date can help predict its later ClinVar "
    "classification. The project is currently focused on careful historical data "
    "matching, not machine learning or medical decisions."
)

PROGRESS_ITEMS: tuple[dict[str, str | int], ...] = (
    {
        "step": 1,
        "name": "Project setup",
        "status": "Complete",
        "explanation": (
            "The folders, Python environment, documentation, and tests are set up."
        ),
    },
    {
        "step": 2,
        "name": "Load genetic data",
        "status": "Working",
        "explanation": (
            "Loading tools exist, but no large real ClinVar release is stored locally."
        ),
    },
    {
        "step": 3,
        "name": "Clean and organize variants",
        "status": "Working",
        "explanation": (
            "The parser creates a standard table and still needs testing on full "
            "releases."
        ),
    },
    {
        "step": 4,
        "name": "Compare old and new ClinVar releases",
        "status": "Working",
        "explanation": (
            "Conservative matching works on fake data and needs review on real "
            "examples."
        ),
    },
    {
        "step": 5,
        "name": "Create timeline dataset",
        "status": "Working",
        "explanation": (
            "The output format exists, but no verified research dataset exists yet."
        ),
    },
    {
        "step": 6,
        "name": "Find useful biological clues",
        "status": "Not Started",
        "explanation": (
            "Biological features will wait until variant matching is reliable."
        ),
    },
    {
        "step": 7,
        "name": "Train prediction models",
        "status": "Not Started",
        "explanation": (
            "No model training will begin before the timeline dataset is checked."
        ),
    },
    {
        "step": 8,
        "name": "Evaluate results",
        "status": "Not Started",
        "explanation": (
            "Evaluation comes after a valid dataset and honest baseline models exist."
        ),
    },
    {
        "step": 9,
        "name": "Create final science fair presentation",
        "status": "Not Started",
        "explanation": (
            "The presentation will report only methods and results that were verified."
        ),
    },
)

FOLDER_GUIDE: tuple[dict[str, str], ...] = (
    {"folder": "research/", "purpose": "Plans, decisions, sources, and dated notes."},
    {"folder": "data/", "purpose": "Fake examples and local research data areas."},
    {"folder": "src/", "purpose": "Reusable Python code for the research pipeline."},
    {
        "folder": "scripts/",
        "purpose": "Commands for validation, matching, and this dashboard.",
    },
    {
        "folder": "tests/",
        "purpose": "Checks that expected software behavior stays correct.",
    },
    {"folder": "docs/", "purpose": "Methods, field definitions, and limitations."},
    {
        "folder": "outputs/",
        "purpose": "Generated tables, figures, and future model files.",
    },
    {"folder": "website/", "purpose": "This local dashboard and future website work."},
)

NEXT_TASKS: tuple[str, ...] = (
    "Review the selected ClinVar release dates and archive format plan.",
    "Test the parser and matcher on a small, manually checked real sample.",
    "Write clear rules for resolving or excluding every ambiguous match type.",
)


def _latest_notebook_entry() -> dict[str, str]:
    """Return the latest main entry from the research notebook."""
    if not NOTEBOOK_PATH.is_file():
        return {"title": "Research notebook unavailable", "content": ""}

    lines = NOTEBOOK_PATH.read_text(encoding="utf-8").splitlines()
    section_starts = [
        index for index, line in enumerate(lines) if line.startswith("## ")
    ]
    if not section_starts:
        return {
            "title": "Research notebook",
            "content": NOTEBOOK_PATH.read_text(encoding="utf-8").strip(),
        }

    start = section_starts[-1]
    return {
        "title": lines[start].removeprefix("## ").strip(),
        "content": "\n".join(lines[start + 1 :]).strip(),
    }


def _latest_pipeline_output() -> str:
    """Describe the newest saved timeline file without claiming it is validated."""
    outputs = sorted(
        TABLES_DIR.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    if not outputs:
        return "No saved timeline output found"
    newest = outputs[0]
    modified = datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat()
    return f"{newest.relative_to(PROJECT_ROOT)} modified {modified}"


def _system_status() -> dict[str, Any]:
    """Build a small status summary from the current local checkout."""
    in_virtual_environment = sys.prefix != sys.base_prefix
    test_files = sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
    raw_files = [path for path in RAW_DATA_DIR.iterdir() if path.name != ".gitkeep"]
    timeline_files = sorted(TABLES_DIR.glob("*.csv"))
    disk = shutil.disk_usage(PROJECT_ROOT)
    extracted_files = sorted(PILOT_EXTRACTED_DIR.glob("*.json"))
    files_created = [str(path.relative_to(PROJECT_ROOT)) for path in timeline_files]
    if EXAMPLE_DATA_PATH.is_file():
        files_created.insert(0, str(EXAMPLE_DATA_PATH.relative_to(PROJECT_ROOT)))

    environment = (
        "virtual environment active" if in_virtual_environment else "system Python"
    )
    return {
        "python_environment": f"Python {sys.version.split()[0]}, {environment}",
        "python_executable": sys.executable,
        "recommended_python": "Python 3.12",
        "python_migration": (
            "Confirmed" if sys.version_info[:2] == (3, 12) else "Not confirmed"
        ),
        "database": "CSV and TSV files; no database is needed yet",
        "tests": f"{len(test_files)} test files available",
        "last_pipeline_run": _latest_pipeline_output(),
        "files_created": files_created,
        "raw_clinvar_files": len(raw_files),
        "pilot_release_pair": "2024-02-01 to 2025-02-06 VCV XML",
        "pilot_extraction": (
            f"{len(extracted_files)} small JSON output files"
            if extracted_files
            else "Historical data unavailable; extraction has not been run"
        ),
        "storage": (
            f"{disk.free / (1024**3):.1f} GiB free; full XML archives retained: no"
        ),
    }


def _pilot_payload(pilot_path: Path, review_path: Path) -> dict[str, object]:
    """Build pilot rows with an explicit missing-historical-data state."""
    rows = read_pilot_rows(pilot_path)
    reviews = load_reviews(review_path)
    comparison_path = PILOT_EXTRACTED_DIR / "pilot_comparisons.json"
    comparisons: dict[str, dict[str, object]] = {}
    data_status = "Historical data unavailable; confirmed extraction has not been run."
    if comparison_path.is_file():
        try:
            payload = json.loads(comparison_path.read_text(encoding="utf-8"))
            comparison_rows = payload.get("comparisons", [])
            comparisons = {
                str(row["variation_id"]): row
                for row in comparison_rows
                if isinstance(row, dict) and row.get("variation_id") is not None
            }
            data_status = "Extracted comparisons available; manual review is required."
        except (OSError, ValueError, TypeError):
            data_status = "Historical comparison file is unreadable."

    combined = []
    for row in rows:
        variation_id = row["variation_id"]
        comparison = comparisons.get(variation_id, {})
        combined.append(
            {
                **row,
                "older_germline_classification": comparison.get(
                    "older_germline_classification"
                ),
                "newer_germline_classification": comparison.get(
                    "newer_germline_classification"
                ),
                "match_status": comparison.get("match_status", "not_extracted"),
                "classification_change": comparison.get(
                    "classification_change", "Unable_to_Verify"
                ),
                "automatic_verification_status": comparison.get(
                    "automatic_verification_status", "requires_manual_review"
                ),
                "record_history_flags": comparison.get("record_history_flags", []),
                "manual_review": reviews.get(
                    variation_id, {"status": "Not reviewed", "notes": ""}
                ),
            }
        )
    releases = {
        label: {
            "release_date": release.release_date.isoformat(),
            "schema_version": release.schema_version,
            "compressed_size_bytes": release.compressed_size_bytes,
            "source_url": release.source_url,
            "expected_md5": release.md5,
        }
        for label, release in PILOT_XML_RELEASES.items()
    }
    return {
        "notice": (
            "Current facts are real NCBI data. Historical fields are not available "
            "until extraction runs."
        ),
        "historical_data_status": data_status,
        "releases": releases,
        "review_statuses": REVIEW_STATUSES,
        "rows": combined,
    }


def _example_dataset_preview() -> list[dict[str, str]]:
    """Load the fake beginner example data without treating it as pipeline output."""
    if not EXAMPLE_DATA_PATH.is_file():
        raise FileNotFoundError(f"Example dataset is missing: {EXAMPLE_DATA_PATH}")

    with EXAMPLE_DATA_PATH.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    expected_columns = {
        "Data Label",
        "Variant ID",
        "Gene",
        "Old Classification",
        "New Classification",
        "Result",
    }
    if not rows or set(rows[0]) != expected_columns:
        raise ValueError("Example dataset columns do not match the dashboard schema.")
    if any(row["Data Label"] != SYNTHETIC_NOTICE for row in rows):
        raise ValueError("Every example row must contain the synthetic data label.")

    return [
        {
            "variant_id": row["Variant ID"],
            "gene": row["Gene"],
            "old_classification": row["Old Classification"],
            "new_classification": row["New Classification"],
            "result": row["Result"],
        }
        for row in rows
    ]


def _classification_group(value: str) -> str:
    """Normalize equivalent uncertain terms for dashboard change counts."""
    normalized = value.strip().casefold()
    if normalized in {
        "vus",
        "uncertain significance",
        "vus-high",
        "vus-mid",
        "vus-low",
    }:
        return "uncertain"
    return normalized


def _historical_comparison_status() -> dict[str, object]:
    """Count only complete rows from the manual verification table."""
    if not MANUAL_REVIEW_PATH.is_file():
        return {
            "total_verified_variants": 0,
            "variants_with_classification_changes": 0,
            "last_verified_comparison": "None yet",
        }

    with MANUAL_REVIEW_PATH.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    required_fields = (
        "variant_id",
        "gene",
        "old_release_date",
        "new_release_date",
        "old_classification",
        "new_classification",
        "verification_source",
    )

    def is_complete_historical_row(row: dict[str, str | None]) -> bool:
        if not all(str(row.get(field) or "").strip() for field in required_fields):
            return False
        try:
            old_date = date.fromisoformat(str(row["old_release_date"]))
            new_date = date.fromisoformat(str(row["new_release_date"]))
        except ValueError:
            return False
        return old_date < new_date

    verified = [row for row in rows if is_complete_historical_row(row)]
    changed = sum(
        _classification_group(row["old_classification"])
        != _classification_group(row["new_classification"])
        for row in verified
    )
    last_comparison = "None yet"
    if verified:
        last = verified[-1]
        last_comparison = (
            f"Variation ID {last['variant_id']}, checked through "
            f"{last['new_release_date']}"
        )
    return {
        "total_verified_variants": len(verified),
        "variants_with_classification_changes": changed,
        "last_verified_comparison": last_comparison,
    }


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the local Flask dashboard."""
    app = Flask(__name__)
    app.config.from_mapping(
        PILOT_VARIANTS_PATH=PILOT_VARIANTS_PATH,
        PILOT_REVIEW_PATH=PILOT_REVIEW_PATH,
    )
    if test_config:
        app.config.update(test_config)
    lookup_state: dict[str, object] = {
        "connection_status": "Not connected",
        "message": "No live lookup has been run in this dashboard session.",
        "last_lookup": None,
    }

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/variant_lookup.html")
    def variant_lookup_page():
        return send_from_directory(Path(__file__).parent, "variant_lookup.html")

    @app.get("/historical_pilot.html")
    def historical_pilot_page():
        return send_from_directory(Path(__file__).parent, "historical_pilot.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "project_name": "Variant Time Machine",
                "project_explanation": PROJECT_EXPLANATION,
                "current_milestone": "Historical ClinVar matching pipeline",
                "folders": FOLDER_GUIDE,
                "next_tasks": NEXT_TASKS,
                "system": _system_status(),
                "research_notes": _latest_notebook_entry(),
                "clinvar_connection": lookup_state,
                "historical_comparison": _historical_comparison_status(),
            }
        )

    @app.get("/api/progress")
    def api_progress():
        return jsonify({"items": PROGRESS_ITEMS})

    @app.get("/api/dataset")
    def api_dataset():
        return jsonify(
            {
                "notice": SYNTHETIC_NOTICE,
                "source": str(EXAMPLE_DATA_PATH.relative_to(PROJECT_ROOT)),
                "rows": _example_dataset_preview(),
            }
        )

    @app.get("/api/pilot")
    def api_pilot():
        try:
            return jsonify(
                _pilot_payload(
                    Path(app.config["PILOT_VARIANTS_PATH"]),
                    Path(app.config["PILOT_REVIEW_PATH"]),
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Pilot data unavailable: {exc}"}), 503

    @app.post("/api/pilot/review/<variation_id>")
    def api_pilot_review(variation_id: str):
        try:
            valid_ids = {
                row["variation_id"]
                for row in read_pilot_rows(Path(app.config["PILOT_VARIANTS_PATH"]))
            }
            if variation_id not in valid_ids:
                return jsonify({"error": "Variation ID is not in the pilot."}), 404
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "A JSON review body is required."}), 400
            review = save_review(
                Path(app.config["PILOT_REVIEW_PATH"]),
                variation_id,
                str(body.get("status", "")),
                str(body.get("notes", "")),
            )
            return jsonify({"variation_id": variation_id, "manual_review": review})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/clinvar/status")
    def api_clinvar_status():
        return jsonify(lookup_state)

    @app.get("/api/clinvar/lookup")
    def api_clinvar_lookup():
        identifier = request.args.get("variant_id", "")
        try:
            variant = lookup_clinvar_variant(identifier)
        except InvalidVariantIdentifier as exc:
            return jsonify({"error": str(exc)}), 400
        except ClinVarRecordNotFound as exc:
            lookup_state.update(
                {
                    "connection_status": "Connected",
                    "message": str(exc),
                    "last_lookup": None,
                }
            )
            return jsonify({"error": str(exc)}), 404
        except ClinVarConnectionError as exc:
            lookup_state.update(
                {
                    "connection_status": "Not connected",
                    "message": str(exc),
                    "last_lookup": None,
                }
            )
            return jsonify({"error": str(exc)}), 502
        except ClinVarAPIError as exc:
            lookup_state.update(
                {
                    "connection_status": "Not connected",
                    "message": str(exc),
                    "last_lookup": None,
                }
            )
            return jsonify({"error": str(exc)}), 502

        result = variant.to_dict()
        lookup_state.update(
            {
                "connection_status": "Connected",
                "message": "The last lookup received a current NCBI ClinVar response.",
                "last_lookup": {
                    "variant": result["variant_identifier"],
                    "gene": result["gene_name"],
                    "classification": result["classification"],
                },
            }
        )
        return jsonify({"variant": result})

    return app


app = create_app()


def run_dashboard() -> None:
    """Run the dashboard locally without Flask debug mode."""
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    run_dashboard()
