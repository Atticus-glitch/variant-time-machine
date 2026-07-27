"""Simple local development dashboard for Variant Time Machine."""

import csv
import json
import shutil
import sys
import threading
import webbrowser
from datetime import UTC, datetime
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
    normalize_gene_symbol,
    normalize_variant_identifier,
    search_clinvar_gene_result,
)
from variant_time_machine.config import (  # noqa: E402
    LARGE_DOWNLOAD_THRESHOLD_BYTES,
    PILOT_CURRENT_API_ESTIMATE_BYTES,
    PILOT_EXTRACTED_DIR,
    PILOT_HISTORICAL_API_LIMIT_BYTES,
    PILOT_WORKSPACE_PATH,
    RAW_DATA_DIR,
    TABLES_DIR,
)
from variant_time_machine.pilot_workspace import (  # noqa: E402
    CHECKLIST_FIELDS,
    CLASSIFICATION_OPTIONS,
    CLASSIFICATION_TYPES,
    REVIEW_STATUSES,
    PilotVariantNotFound,
    PilotWorkspaceError,
    add_record,
    find_record,
    load_workspace,
    new_pilot_record,
    public_record,
    refresh_current_record,
    update_record,
)

SYNTHETIC_NOTICE = "Synthetic example data. Not real scientific results."
EXAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "example_variants.csv"
NOTEBOOK_PATH = PROJECT_ROOT / "research" / "research-notebook.md"

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
        "name": "Compare historical records",
        "status": "Working",
        "explanation": (
            "The manual review workspace exists, but no historical match is complete."
        ),
    },
    {
        "step": 5,
        "name": "Timeline dataset",
        "status": "Working",
        "explanation": (
            "The output format exists, but no verified research dataset exists yet."
        ),
    },
    {
        "step": 6,
        "name": "Features",
        "status": "Not Started",
        "explanation": (
            "Biological features will wait until variant matching is reliable."
        ),
    },
    {
        "step": 7,
        "name": "Models",
        "status": "Not Started",
        "explanation": (
            "No model training will begin before the timeline dataset is checked."
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
    "Preview several clear current ClinVar candidates without saving them.",
    "Choose one variant for a written reason and run the confirmed pilot workflow.",
    "Investigate one official historical record and verify it manually.",
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
        "pilot_strategy": "Five to ten one-record API lookups",
        "archive_scan": "Paused; metadata inspection only",
        "pilot_outputs": f"{len(extracted_files)} small JSON output files",
        "storage": (
            f"{disk.free / (1024**3):.1f} GiB free; full XML archives retained: no"
        ),
    }


def _directory_size(path: Path) -> int:
    """Return bytes used by regular files below one local directory."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _format_bytes(size: int) -> str:
    """Format a byte count without hiding the exact value."""
    if size < 1024:
        return f"{size} bytes"
    if size < 1024**2:
        return f"{size / 1024:.1f} KiB ({size:,} bytes)"
    return f"{size / (1024**2):.1f} MiB ({size:,} bytes)"


def _transfer_safety_status(
    transfer_state: dict[str, object] | None = None,
) -> dict[str, object]:
    """Report local transfer policy and recorded storage use."""
    downloaded = sum(
        path.stat().st_size
        for path in RAW_DATA_DIR.iterdir()
        if path.is_file() and path.name != ".gitkeep"
    )
    session_bytes = int((transfer_state or {}).get("total_api_bytes", 0))
    return {
        "largest_planned_download": (
            "One versioned VCV API record, capped at "
            f"{PILOT_HISTORICAL_API_LIMIT_BYTES / 1_000_000:.0f} MB"
        ),
        "current_transfer": str(
            (transfer_state or {}).get("current_transfer", "0 bytes; idle")
        ),
        "total_downloaded": _format_bytes(downloaded + session_bytes),
        "storage_used": _format_bytes(_directory_size(PROJECT_ROOT / "data")),
        "large_download_protection": "ON",
        "large_download_threshold": (
            f"{LARGE_DOWNLOAD_THRESHOLD_BYTES / 1_000_000:.0f} MB"
        ),
        "last_request": (transfer_state or {}).get("last_request"),
    }


def _current_pilot_status(path: Path) -> dict[str, object]:
    """Return the first workspace record or an explicit empty state."""
    workspace = load_workspace(path)
    if not workspace["records"]:
        return {
            "selected": False,
            "variant": "No pilot variant selected",
            "gene": "No pilot variant selected",
            "current_classification": "No pilot variant selected",
            "historical_status": "No historical information investigated",
            "verification_status": "No pilot variant selected",
            "timeline": [],
        }
    record = workspace["records"][0]
    timeline = public_record(record)["timeline"]
    return {
        "selected": True,
        "variant": f"{record['vcv_accession']} (Variation ID {record['variant_id']})",
        "gene": record["gene"] or "Not listed",
        "current_classification": record["current_classification"] or "Not listed",
        "historical_status": timeline["change_category"],
        "verification_status": record["review_status"],
        "timeline": timeline,
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


def _historical_comparison_status(path: Path) -> dict[str, object]:
    """Count only browser workspace records that passed verification rules."""
    workspace = load_workspace(path)
    verified = [
        record
        for record in workspace["records"]
        if record["review_status"] == "verified"
    ]
    changed = sum(
        public_record(record)["timeline"]["change_category"].startswith("Changed from")
        for record in verified
    )
    last_comparison = "None yet"
    if verified:
        last = max(verified, key=lambda record: str(record["updated_at_utc"]))
        last_comparison = (
            f"Variation ID {last['variant_id']}, checked through "
            f"{last['newer_comparison_date']}"
        )
    return {
        "total_verified_variants": len(verified),
        "variants_with_classification_changes": changed,
        "last_verified_comparison": last_comparison,
    }


def _lookup_plan(query: str) -> dict[str, object]:
    """Validate one lookup query and return a no-network transfer plan."""
    cleaned = query.strip()
    if not cleaned or len(cleaned) > 40:
        raise InvalidVariantIdentifier(
            "Enter a Variation ID, VCV accession, or short gene symbol."
        )
    if cleaned.isdigit() or cleaned.upper().startswith("VCV"):
        variation_id = normalize_variant_identifier(cleaned)
        return {
            "query": cleaned,
            "query_type": "variant",
            "normalized_query": variation_id,
            "source": (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                f"?db=clinvar&id={variation_id}&retmode=json"
            ),
            "estimated_max_bytes": PILOT_CURRENT_API_ESTIMATE_BYTES,
            "purpose": "Retrieve current ClinVar information for one variant",
            "is_small": True,
            "large_download_blocked": False,
            "requires_approval": True,
        }
    gene = normalize_gene_symbol(cleaned)
    return {
        "query": cleaned,
        "query_type": "gene",
        "normalized_query": gene,
        "source": (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi and "
            "up to five https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
            "esummary.fcgi requests"
        ),
        "estimated_max_bytes": PILOT_CURRENT_API_ESTIMATE_BYTES * 6,
        "purpose": f"Find up to five current ClinVar candidates for {gene}",
        "is_small": True,
        "large_download_blocked": False,
        "requires_approval": True,
    }


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the local Flask dashboard."""
    app = Flask(__name__)
    app.config.from_mapping(
        PILOT_WORKSPACE_PATH=PILOT_WORKSPACE_PATH,
    )
    if test_config:
        app.config.update(test_config)
    lookup_state: dict[str, object] = {
        "connection_status": "Not connected",
        "message": "No live lookup has been run in this dashboard session.",
        "last_lookup": None,
    }
    lookup_cache: dict[str, object] = {}
    transfer_state: dict[str, object] = {
        "current_transfer": "0 bytes; idle",
        "total_api_bytes": 0,
        "last_request": None,
    }

    def transfer_result(
        plan: dict[str, object], actual_bytes: int
    ) -> dict[str, object]:
        result = {
            "source": plan["source"],
            "estimated_max_bytes": plan["estimated_max_bytes"],
            "actual_bytes": actual_bytes,
            "purpose": plan["purpose"],
            "is_small": plan["is_small"],
            "large_download_blocked": plan["large_download_blocked"],
        }
        transfer_state["total_api_bytes"] = (
            int(transfer_state["total_api_bytes"]) + actual_bytes
        )
        transfer_state["current_transfer"] = "0 bytes; idle"
        transfer_state["last_request"] = result
        return result

    def perform_lookup(plan: dict[str, object]) -> tuple[list[dict[str, object]], int]:
        """Run only the approved small API calls declared by a lookup plan."""
        transfer_state["current_transfer"] = "Small approved request in progress"
        variants = []
        actual_bytes = 0
        if plan["query_type"] == "variant":
            variant = lookup_clinvar_variant(str(plan["normalized_query"]))
            variants.append(variant)
            actual_bytes += variant.response_bytes or 0
        else:
            search = search_clinvar_gene_result(str(plan["normalized_query"]))
            actual_bytes += search.response_bytes
            for identifier in search.identifiers:
                variant = lookup_clinvar_variant(identifier)
                variants.append(variant)
                actual_bytes += variant.response_bytes or 0
        payloads = []
        for variant in variants:
            lookup_cache[variant.variation_id] = variant
            payloads.append(variant.to_dict())
        return payloads, actual_bytes

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/variant_lookup.html")
    def variant_lookup_page():
        return send_from_directory(Path(__file__).parent, "variant_lookup.html")

    @app.get("/historical_pilot.html")
    def historical_pilot_page():
        return send_from_directory(Path(__file__).parent, "pilot_workspace.html")

    @app.get("/pilot_workspace.html")
    def pilot_workspace_page():
        return send_from_directory(Path(__file__).parent, "pilot_workspace.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "project_name": "Variant Time Machine",
                "project_explanation": PROJECT_EXPLANATION,
                "current_milestone": "First single-variant research workflow",
                "folders": FOLDER_GUIDE,
                "next_tasks": NEXT_TASKS,
                "system": _system_status(),
                "research_notes": _latest_notebook_entry(),
                "clinvar_connection": lookup_state,
                "historical_comparison": _historical_comparison_status(
                    Path(app.config["PILOT_WORKSPACE_PATH"])
                ),
                "transfer_safety": _transfer_safety_status(transfer_state),
                "current_pilot_variant": _current_pilot_status(
                    Path(app.config["PILOT_WORKSPACE_PATH"])
                ),
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
            workspace = load_workspace(Path(app.config["PILOT_WORKSPACE_PATH"]))
            records = [public_record(record) for record in workspace["records"]]
            return jsonify(
                {
                    "records": records,
                    "count": len(records),
                    "first_run": len(records) == 0,
                    "review_statuses": REVIEW_STATUSES,
                    "classification_options": CLASSIFICATION_OPTIONS,
                    "classification_types": CLASSIFICATION_TYPES,
                    "checklist_fields": CHECKLIST_FIELDS,
                    "updated_at_utc": workspace["updated_at_utc"],
                }
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Pilot data unavailable: {exc}"}), 503

    @app.post("/api/pilot")
    def api_add_pilot():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON pilot record is required."}), 400
        try:
            variation_id = normalize_variant_identifier(str(body.get("variant_id", "")))
            if body.get("understood_current_only") is not True:
                raise PilotWorkspaceError(
                    "Confirm that current ClinVar information is not a historical "
                    "result."
                )
            variant = lookup_cache.get(variation_id)
            if variant is None:
                raise PilotWorkspaceError(
                    "Look up this variant in the workspace before adding it."
                )
            workspace_path = Path(app.config["PILOT_WORKSPACE_PATH"])
            on_duplicate = str(body.get("on_duplicate", "cancel"))
            workspace = load_workspace(workspace_path)
            try:
                existing = find_record(workspace, variation_id)
            except PilotVariantNotFound:
                existing = None
            if existing is not None:
                if on_duplicate == "update_current":
                    updated = refresh_current_record(
                        workspace_path, variation_id, variant
                    )
                    return jsonify({"record": public_record(updated), "updated": True})
                return (
                    jsonify(
                        {
                            "error": "This variant is already in the pilot.",
                            "duplicate": True,
                            "record": public_record(existing),
                            "options": ["open_existing", "update_current", "cancel"],
                        }
                    ),
                    409,
                )
            record = new_pilot_record(
                variant,
                str(body.get("selection_reason", "")),
                str(body.get("notes", "")),
                str(body.get("intended_historical_date", "")),
            )
            added = add_record(workspace_path, record)
            return jsonify({"record": public_record(added), "created": True}), 201
        except (InvalidVariantIdentifier, PilotWorkspaceError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not save the pilot: {exc}"}), 503

    @app.get("/api/pilot/<variation_id>")
    def api_get_pilot(variation_id: str):
        try:
            normalized = normalize_variant_identifier(variation_id)
            workspace = load_workspace(Path(app.config["PILOT_WORKSPACE_PATH"]))
            return jsonify(
                {"record": public_record(find_record(workspace, normalized))}
            )
        except (InvalidVariantIdentifier, PilotWorkspaceError) as exc:
            return jsonify({"error": str(exc)}), 404
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Pilot data unavailable: {exc}"}), 503

    @app.patch("/api/pilot/<variation_id>")
    def api_update_pilot(variation_id: str):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON review update is required."}), 400
        actions = {
            "save_draft": None,
            "mark_reviewing": "reviewing",
            "mark_verified": "verified",
            "mark_ambiguous": "ambiguous",
            "exclude": "excluded",
        }
        action = str(body.get("action", "save_draft"))
        if action not in actions:
            return jsonify({"error": "Unknown review action."}), 400
        changes = body.get("changes", {})
        if not isinstance(changes, dict):
            return jsonify({"error": "Review changes must be a JSON object."}), 400
        try:
            normalized = normalize_variant_identifier(variation_id)
            updated = update_record(
                Path(app.config["PILOT_WORKSPACE_PATH"]),
                normalized,
                changes,
                status=actions[action],
            )
            return jsonify({"record": public_record(updated), "saved": True})
        except (InvalidVariantIdentifier, PilotWorkspaceError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not save your work: {exc}"}), 503

    @app.post("/api/pilot/<variation_id>/verify")
    def api_verify_pilot(variation_id: str):
        body = request.get_json(silent=True)
        changes = body.get("changes", {}) if isinstance(body, dict) else {}
        if not isinstance(changes, dict):
            return jsonify({"error": "Verification changes must be an object."}), 400
        try:
            normalized = normalize_variant_identifier(variation_id)
            updated = update_record(
                Path(app.config["PILOT_WORKSPACE_PATH"]),
                normalized,
                changes,
                status="verified",
            )
            return jsonify({"record": public_record(updated), "verified": True})
        except (InvalidVariantIdentifier, PilotWorkspaceError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not verify the record: {exc}"}), 503

    @app.post("/api/clinvar/plan")
    def api_clinvar_plan():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Enter a lookup query."}), 400
        try:
            return jsonify({"plan": _lookup_plan(str(body.get("query", "")))})
        except InvalidVariantIdentifier as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/clinvar/lookup")
    def api_clinvar_lookup():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON lookup request is required."}), 400
        if body.get("approved") is not True:
            return (
                jsonify(
                    {
                        "error": (
                            "Review and approve the transfer estimate before lookup."
                        )
                    }
                ),
                428,
            )
        try:
            plan = _lookup_plan(str(body.get("query", "")))
            if int(plan["estimated_max_bytes"]) > LARGE_DOWNLOAD_THRESHOLD_BYTES:
                plan["large_download_blocked"] = True
                return jsonify(
                    {"error": "Large-download protection blocked this request."}
                ), 413
            variants, actual_bytes = perform_lookup(plan)
            if not variants:
                return jsonify({"error": "No current ClinVar records were found."}), 404
            transfer = transfer_result(plan, actual_bytes)
            latest = variants[0]
            lookup_state.update(
                {
                    "connection_status": "Connected",
                    "message": "Current ClinVar information received.",
                    "last_lookup": {
                        "variant": latest["variant_identifier"],
                        "gene": latest["gene_name"],
                        "classification": latest["classification"],
                    },
                }
            )
            return jsonify({"variants": variants, "transfer": transfer})
        except InvalidVariantIdentifier as exc:
            transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 400
        except ClinVarRecordNotFound as exc:
            transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 404
        except ClinVarConnectionError as exc:
            transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 502
        except ClinVarAPIError as exc:
            transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 502

    @app.get("/api/transfer-safety")
    def api_transfer_safety():
        return jsonify(_transfer_safety_status(transfer_state))

    @app.get("/api/clinvar/status")
    def api_clinvar_status():
        return jsonify(lookup_state)

    return app


app = create_app()


def run_dashboard(*, open_browser: bool = True) -> None:
    """Run the dashboard locally without Flask debug mode."""
    if open_browser:
        threading.Timer(
            0.8, lambda: webbrowser.open("http://127.0.0.1:5000/pilot_workspace.html")
        ).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    run_dashboard()
