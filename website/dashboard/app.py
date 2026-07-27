"""Simple local development dashboard for Variant Time Machine."""

import csv
import json
import shutil
import sys
import threading
import uuid
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
    PILOT_WORKSPACE_PATH,
    RAW_DATA_DIR,
    TABLES_DIR,
    VCV_HISTORY_DIR,
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
from variant_time_machine.vcv_history import (  # noqa: E402
    CLINVAR_EFETCH_URL,
    DEFAULT_MAX_REQUESTS,
    MAX_RESPONSE_BYTES,
    MAX_TOTAL_BYTES,
    InvalidVCVAccession,
    RequestLimitError,
    RetrievalCancelled,
    TransferLimitError,
    VCVHistoryError,
    VCVHistoryResult,
    VersionResult,
    fetch_current_vcv,
    fetch_vcv_history,
    plan_version_range,
    validate_vcv_accession,
)
from variant_time_machine.vcv_history_store import (  # noqa: E402
    VCVHistoryStoreError,
    list_histories,
    load_history,
    progress_metrics,
    save_history,
    update_review,
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
            "The code, documentation, and tests exist. Python 3.12 migration is still "
            "pending on this VM."
        ),
    },
    {
        "step": 2,
        "name": "Load genetic data",
        "status": "Working",
        "explanation": (
            "Small official VCV EFetch records can be loaded individually. No full "
            "ClinVar release is stored locally."
        ),
    },
    {
        "step": 3,
        "name": "Clean and organize variants",
        "status": "Working",
        "explanation": (
            "The VCV parser keeps aggregate germline, somatic, and oncogenicity fields "
            "separate and preserves missing values."
        ),
    },
    {
        "step": 4,
        "name": "Compare historical records",
        "status": "Working",
        "explanation": (
            "One real three-version VCV history exists; its human verification is "
            "still incomplete."
        ),
    },
    {
        "step": 5,
        "name": "Timeline dataset",
        "status": "Working",
        "explanation": (
            "One real unverified history is stored. No verified research dataset "
            "exists yet."
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


def _json_body() -> dict[str, object]:
    """Return a JSON object or raise a consistent request error."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("A JSON request object is required.")
    return body


def _vcv_base(value: object) -> str:
    """Validate strict VCV input and return its canonical base accession."""
    if not isinstance(value, str):
        raise InvalidVCVAccession("VCV accession must be text.")
    return validate_vcv_accession(value).accession


def _public_version_result(result: VersionResult) -> dict[str, object]:
    """Serialize a source result without exposing retained XML."""
    value = result.to_dict()
    value.pop("raw_xml", None)
    return value


def _public_history_result(result: VCVHistoryResult) -> dict[str, object]:
    """Serialize a history result without exposing retained XML."""
    value = result.to_dict()
    current = value.get("current_result")
    if isinstance(current, dict):
        current.pop("raw_xml", None)
    for item in value.get("results", []):
        if isinstance(item, dict):
            item.pop("raw_xml", None)
    return value


def _git_commit() -> str:
    """Read the local Git revision without starting a subprocess."""
    head_path = PROJECT_ROOT / ".git" / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            reference = PROJECT_ROOT / ".git" / head.removeprefix("ref: ")
            return reference.read_text(encoding="utf-8").strip()
        return head
    except OSError:
        return "unavailable"


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
    history_count = len(list_histories(VCV_HISTORY_DIR))
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
        "pilot_strategy": "Ten to twenty-five manually reviewed VCV histories",
        "archive_scan": "Paused; metadata inspection only",
        "pilot_outputs": (
            f"{history_count} VCV history case(s); "
            f"{len(extracted_files)} legacy extracted JSON file(s)"
        ),
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
            "One VCV history exploration, capped at "
            f"{MAX_TOTAL_BYTES / (1024**2):.0f} MiB total; each response has a "
            f"{MAX_RESPONSE_BYTES / (1024**2):.0f} MiB (approximately 10 MB) hard cap"
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
        VCV_HISTORY_ROOT=VCV_HISTORY_DIR,
        VCV_CURRENT_FETCHER=fetch_current_vcv,
        VCV_HISTORY_FETCHER=fetch_vcv_history,
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
    state_lock = threading.RLock()
    ncbi_request_lock = threading.Lock()
    current_vcv_cache: dict[str, VersionResult] = {}
    operations: dict[str, dict[str, object]] = {}

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
        with state_lock:
            transfer_state["total_api_bytes"] = (
                int(transfer_state["total_api_bytes"]) + actual_bytes
            )
            transfer_state["current_transfer"] = "0 bytes; idle"
            transfer_state["last_request"] = result
        return result

    def perform_lookup(plan: dict[str, object]) -> tuple[list[dict[str, object]], int]:
        """Run only the approved small API calls declared by a lookup plan."""
        with state_lock:
            transfer_state["current_transfer"] = "Small approved request in progress"
        variants = []
        actual_bytes = 0
        with ncbi_request_lock:
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

    def reset_transfer() -> None:
        with state_lock:
            transfer_state["current_transfer"] = "0 bytes; idle"

    def history_root() -> Path:
        return Path(app.config["VCV_HISTORY_ROOT"])

    def history_plan(body: dict[str, object]) -> dict[str, object]:
        accession = _vcv_base(body.get("accession", body.get("identifier")))
        with state_lock:
            current = current_vcv_cache.get(accession)
        if current is None or current.status != "available" or current.record is None:
            raise LookupError(
                "Run and approve a successful current VCV lookup before planning "
                "history."
            )
        current_version = current.record.version
        mode = body.get("mode", "all")
        if mode not in {"all", "custom", "endpoints"}:
            raise ValueError("mode must be 'all', 'custom', or 'endpoints'.")
        versions = None
        start_version = None
        end_version = None
        if mode == "custom":
            start = body.get("start_version", body.get("start"))
            end = body.get("end_version", body.get("end"))
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
            ):
                raise ValueError(
                    "Custom mode requires integer start_version and end_version."
                )
            if start > end:
                raise ValueError("Custom start_version cannot exceed end_version.")
            start_version = start
            end_version = end
            versions = range(start, end + 1)
        if mode == "all" and current_version > DEFAULT_MAX_REQUESTS:
            raise RequestLimitError(
                f"All {current_version} versions exceed the 25-request limit; "
                "use custom or endpoints mode."
            )
        requested = plan_version_range(
            current_version,
            mode=mode,  # type: ignore[arg-type]
            versions=versions,
            max_requests=DEFAULT_MAX_REQUESTS,
        )
        count = len(requested)
        maximum = min(count * MAX_RESPONSE_BYTES, MAX_TOTAL_BYTES)
        plan = {
            "accession": accession,
            "current_version": current_version,
            "mode": mode,
            "requested_versions": list(requested),
            "request_count": count,
            "estimated_max_bytes": maximum,
            "max_possible_transfer_bytes": maximum,
            "estimated_storage_bytes": maximum,
            "source": CLINVAR_EFETCH_URL,
            "purpose": "Retrieve exact official historical VCV versions for comparison",
            "confirmation": (
                "I approve these bounded sequential official ClinVar EFetch requests."
            ),
            "requires_approval": True,
        }
        if mode == "custom":
            plan["start_version"] = start_version
            plan["end_version"] = end_version
        return plan

    def history_metrics() -> dict[str, object]:
        root = history_root()
        base = progress_metrics(root)
        available = 0
        recorded_transfer = 0
        for accession in list_histories(root):
            artifact = load_history(root, accession)
            versions = artifact["versions"]
            manifest = artifact["manifest"]
            if isinstance(versions, dict):
                available += sum(
                    isinstance(item, dict) and item.get("record") is not None
                    for item in versions.get("versions", [])
                )
            if isinstance(manifest, dict):
                recorded_transfer += int(manifest.get("total_bytes", 0))
        return {
            "histories_explored": base["histories"],
            "versions_retrieved": available,
            "histories_with_germline_change": base["changed_histories"],
            "manually_verified": base["verified"],
            "total_recorded_history_transfer_bytes": recorded_transfer,
            "storage_bytes": base["bytes"],
            "storage": base["storage"],
        }

    def research_progress() -> dict[str, object]:
        workspace = load_workspace(Path(app.config["PILOT_WORKSPACE_PATH"]))
        metrics = history_metrics()
        with state_lock:
            current_count = len(current_vcv_cache)
        return {
            "candidates_selected": len(workspace["records"]),
            "current_records_retrieved": max(
                int(metrics["histories_explored"]), current_count
            ),
            "current_records_retrieved_this_session": current_count,
            **metrics,
        }

    def dynamic_next_tasks(progress: dict[str, object]) -> tuple[str, ...]:
        if progress["candidates_selected"] == 0:
            first = "Select a current ClinVar candidate for the pilot workspace."
        else:
            first = "Confirm the selected candidate's current official VCV record."
        if progress["histories_explored"] == 0:
            second = "Plan and explore one bounded official VCV version history."
        else:
            second = "Review the saved version comparison and document ambiguities."
        if progress["manually_verified"] == 0:
            third = "Complete the history verification checklist before analysis."
        else:
            third = "Choose the next candidate using the recorded research criteria."
        return (first, second, third)

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

    @app.get("/version_history.html")
    def version_history_page():
        return send_from_directory(Path(__file__).parent, "version_history.html")

    @app.get("/api/status")
    def api_status():
        try:
            progress = research_progress()
        except (OSError, ValueError, json.JSONDecodeError, VCVHistoryStoreError):
            progress = {
                "candidates_selected": 0,
                "current_records_retrieved": 0,
                "current_records_retrieved_this_session": 0,
                "histories_explored": 0,
                "versions_retrieved": 0,
                "histories_with_germline_change": 0,
                "manually_verified": 0,
                "total_recorded_history_transfer_bytes": 0,
                "storage_bytes": 0,
                "storage": "0 B",
            }
        with state_lock:
            transfer_snapshot = dict(transfer_state)
        return jsonify(
            {
                "project_name": "Variant Time Machine",
                "project_explanation": PROJECT_EXPLANATION,
                "current_milestone": "First multi-version VCV pilot review",
                "folders": FOLDER_GUIDE,
                "next_tasks": dynamic_next_tasks(progress),
                "research_progress": progress,
                "system": _system_status(),
                "research_notes": _latest_notebook_entry(),
                "clinvar_connection": lookup_state,
                "historical_comparison": _historical_comparison_status(
                    Path(app.config["PILOT_WORKSPACE_PATH"])
                ),
                "transfer_safety": {
                    **_transfer_safety_status(transfer_snapshot),
                    "vcv_history_storage": progress["storage"],
                    "vcv_history_storage_bytes": progress["storage_bytes"],
                },
                "current_pilot_variant": _current_pilot_status(
                    Path(app.config["PILOT_WORKSPACE_PATH"])
                ),
            }
        )

    @app.post("/api/vcv-history/current-plan")
    def api_vcv_current_plan():
        try:
            body = _json_body()
            accession = _vcv_base(body.get("accession", body.get("identifier")))
            return jsonify(
                {
                    "plan": {
                        "accession": accession,
                        "request_count": 1,
                        "estimated_max_bytes": MAX_RESPONSE_BYTES,
                        "source": CLINVAR_EFETCH_URL,
                        "purpose": (
                            "Retrieve the current official VCV record and version"
                        ),
                        "requires_approval": True,
                    }
                }
            )
        except (InvalidVCVAccession, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/vcv-history/current")
    def api_vcv_current():
        try:
            body = _json_body()
            if body.get("approved") is not True:
                return jsonify(
                    {"error": "Review and approve the current-record transfer first."}
                ), 428
            accession = _vcv_base(body.get("accession", body.get("identifier")))
            with state_lock:
                transfer_state["current_transfer"] = (
                    "One approved current VCV request in progress"
                )
            fetcher = app.config["VCV_CURRENT_FETCHER"]
            with ncbi_request_lock:
                result = fetcher(accession)
            if not isinstance(result, VersionResult):
                raise VCVHistoryError("Current VCV fetcher returned an invalid result.")
            if result.status != "available" or result.record is None:
                with state_lock:
                    transfer_state["current_transfer"] = "0 bytes; idle"
                status = 404 if result.status == "missing" else 502
                return jsonify(
                    {
                        "error": result.message
                        or f"Current VCV record was {result.status}."
                    }
                ), status
            if result.record.accession != accession:
                raise VCVHistoryError("Current VCV response accession did not match.")
            with state_lock:
                current_vcv_cache[accession] = result
            plan = {
                "source": result.source_request,
                "estimated_max_bytes": MAX_RESPONSE_BYTES,
                "purpose": "Retrieve the current official VCV record and version",
                "is_small": True,
                "large_download_blocked": False,
            }
            transfer = transfer_result(plan, result.response_bytes)
            return jsonify(
                {
                    "accession": accession,
                    "current_version": result.record.version,
                    "current_identifier": result.record.accession_version,
                    "record": result.record.to_dict(),
                    "provenance": {
                        "source_request": result.source_request,
                        "retrieved_at_utc": result.retrieved_at_utc,
                        "status": result.status,
                    },
                    "transfer": transfer,
                }
            )
        except (InvalidVCVAccession, ValueError) as exc:
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 400
        except TransferLimitError as exc:
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 413
        except (VCVHistoryError, OSError) as exc:
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
            return jsonify({"error": str(exc)}), 502

    @app.post("/api/vcv-history/plan")
    def api_vcv_plan():
        try:
            return jsonify({"plan": history_plan(_json_body())})
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 409
        except RequestLimitError as exc:
            return jsonify({"error": str(exc)}), 413
        except (InvalidVCVAccession, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    def run_history_operation(
        operation_id: str,
        plan: dict[str, object],
        current: VersionResult,
        cancel_event: threading.Event,
    ) -> None:
        def report(event: dict[str, object]) -> None:
            with state_lock:
                operation = operations[operation_id]
                events = operation["progress_events"]
                assert isinstance(events, list)
                events.append({**event, "sequence": len(events) + 1})
                operation["progress"] = dict(events[-1])

        try:
            with state_lock:
                transfer_state["current_transfer"] = (
                    f"VCV history operation {operation_id} in progress"
                )
            fetcher = app.config["VCV_HISTORY_FETCHER"]
            with ncbi_request_lock:
                result = fetcher(
                    str(plan["accession"]),
                    mode="custom",
                    versions=tuple(plan["requested_versions"]),
                    max_requests=DEFAULT_MAX_REQUESTS,
                    max_total_bytes=MAX_TOTAL_BYTES,
                    cancel=cancel_event,
                    progress=report,
                    current_result=current,
                )
            if not isinstance(result, VCVHistoryResult):
                raise VCVHistoryError("History fetcher returned an invalid result.")
            saved_accession = None
            if not result.cancelled or result.results:
                save_history(
                    history_root(),
                    result,
                    app_version="0.1.0",
                    git_commit=_git_commit(),
                )
                saved_accession = result.requested_accession.split(".", 1)[0]
            historical_bytes = max(
                0, result.total_response_bytes - current.response_bytes
            )
            transfer = transfer_result(
                {
                    "source": CLINVAR_EFETCH_URL,
                    "estimated_max_bytes": plan["estimated_max_bytes"],
                    "purpose": plan["purpose"],
                    "is_small": True,
                    "large_download_blocked": False,
                },
                historical_bytes,
            )
            with state_lock:
                operation = operations[operation_id]
                operation["state"] = "cancelled" if result.cancelled else "completed"
                operation["result"] = {
                    "history": _public_history_result(result),
                    "saved_accession": saved_accession,
                    "transfer": transfer,
                }
                operation["finished_at_utc"] = datetime.now(UTC).isoformat()
        except RetrievalCancelled as exc:
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
                operations[operation_id].update(
                    state="cancelled",
                    error=str(exc),
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )
        except Exception as exc:  # background failures must remain observable
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
                operations[operation_id].update(
                    state="failed",
                    error=str(exc),
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )

    @app.post("/api/vcv-history/explore")
    def api_vcv_explore():
        try:
            body = _json_body()
            if body.get("approved") is not True:
                return jsonify(
                    {"error": "Review and approve the exact history plan first."}
                ), 428
            supplied_plan = body.get("plan", body)
            if not isinstance(supplied_plan, dict):
                raise ValueError("plan must be a JSON object.")
            plan = history_plan(supplied_plan)
            if (
                "requested_versions" in supplied_plan
                and supplied_plan["requested_versions"] != plan["requested_versions"]
            ):
                raise ValueError("Submitted requested_versions do not match the plan.")
            accession = str(plan["accession"])
            with state_lock:
                if any(item["state"] == "running" for item in operations.values()):
                    return jsonify(
                        {"error": "A VCV history exploration is already running."}
                    ), 409
                current = current_vcv_cache[accession]
                operation_id = uuid.uuid4().hex
                cancel_event = threading.Event()
                operations[operation_id] = {
                    "operation_id": operation_id,
                    "state": "running",
                    "plan": plan,
                    "progress": None,
                    "progress_events": [],
                    "result": None,
                    "error": None,
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "finished_at_utc": None,
                    "cancel_event": cancel_event,
                }
            thread = threading.Thread(
                target=run_history_operation,
                args=(operation_id, plan, current, cancel_event),
                daemon=True,
                name=f"vcv-history-{operation_id[:8]}",
            )
            thread.start()
            return jsonify({"operation_id": operation_id, "state": "running"}), 202
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 409
        except RequestLimitError as exc:
            return jsonify({"error": str(exc)}), 413
        except (InvalidVCVAccession, ValueError, KeyError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/vcv-history/operations/<operation_id>")
    def api_vcv_operation(operation_id: str):
        with state_lock:
            operation = operations.get(operation_id)
            if operation is None:
                return jsonify({"error": "VCV history operation not found."}), 404
            public = {
                key: value for key, value in operation.items() if key != "cancel_event"
            }
            return jsonify(public)

    @app.post("/api/vcv-history/operations/<operation_id>/cancel")
    def api_cancel_vcv_operation(operation_id: str):
        with state_lock:
            operation = operations.get(operation_id)
            if operation is None:
                return jsonify({"error": "VCV history operation not found."}), 404
            if operation["state"] != "running":
                return jsonify(
                    {"operation_id": operation_id, "state": operation["state"]}
                )
            cancel_event = operation["cancel_event"]
            assert isinstance(cancel_event, threading.Event)
            cancel_event.set()
            operation["cancellation_requested"] = True
            return jsonify(
                {
                    "operation_id": operation_id,
                    "state": "running",
                    "cancellation_requested": True,
                }
            )

    @app.get("/api/vcv-histories")
    def api_vcv_histories():
        try:
            histories = []
            for accession in list_histories(history_root()):
                artifact = load_history(history_root(), accession)
                histories.append(
                    {
                        "accession": accession,
                        "summary": artifact["metadata"]["summary"],
                        "review": artifact["review"],
                        "total_response_bytes": artifact["manifest"]["total_bytes"],
                    }
                )
            return jsonify({"histories": histories, "metrics": history_metrics()})
        except (OSError, VCVHistoryStoreError) as exc:
            return jsonify({"error": f"VCV histories unavailable: {exc}"}), 503

    @app.get("/api/vcv-histories/<accession>")
    def api_vcv_history(accession: str):
        try:
            canonical = _vcv_base(accession)
            if canonical != accession:
                raise InvalidVCVAccession("Use an unversioned canonical VCV accession.")
            if canonical not in list_histories(history_root()):
                return jsonify({"error": "VCV history not found."}), 404
            return jsonify(load_history(history_root(), canonical))
        except InvalidVCVAccession as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, VCVHistoryStoreError) as exc:
            return jsonify({"error": f"VCV history unavailable: {exc}"}), 503

    @app.patch("/api/vcv-histories/<accession>/review")
    def api_vcv_review(accession: str):
        actions = {
            "add_note": None,
            "mark_needs_review": "needs_review",
            "mark_ambiguous": "ambiguous",
            "mark_manually_verified": "manually_verified",
            "exclude": "excluded",
        }
        allowed = {
            "notes",
            "reviewer_decision",
            "manual_corrections",
            "verification",
            "sources",
        }
        try:
            canonical = _vcv_base(accession)
            if canonical != accession:
                raise InvalidVCVAccession("Use an unversioned canonical VCV accession.")
            if canonical not in list_histories(history_root()):
                return jsonify({"error": "VCV history not found."}), 404
            body = _json_body()
            action = body.get("action")
            if action not in actions:
                raise ValueError("Unknown review action.")
            changes = body.get("changes", body)
            if not isinstance(changes, dict):
                raise ValueError("Review changes must be a JSON object.")
            unknown = set(changes).difference(allowed | {"action", "changes"})
            if unknown:
                raise ValueError("Only manual review fields may be changed.")
            values = {key: changes[key] for key in allowed if key in changes}
            if action == "add_note":
                note = values.get("notes")
                if not isinstance(note, str) or not note.strip():
                    raise ValueError("add_note requires non-empty notes.")
                existing = load_history(history_root(), canonical)["review"]["notes"]
                values["notes"] = f"{existing}\n{note}".strip()
            review = update_review(
                history_root(),
                canonical,
                status=actions[action],  # type: ignore[arg-type]
                **values,
            )
            return jsonify({"accession": canonical, "review": review, "saved": True})
        except (InvalidVCVAccession, ValueError, VCVHistoryStoreError) as exc:
            return jsonify({"error": str(exc)}), 400
        except OSError as exc:
            return jsonify({"error": f"Could not save review: {exc}"}), 503

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
            reset_transfer()
            return jsonify({"error": str(exc)}), 400
        except ClinVarRecordNotFound as exc:
            reset_transfer()
            return jsonify({"error": str(exc)}), 404
        except ClinVarConnectionError as exc:
            reset_transfer()
            return jsonify({"error": str(exc)}), 502
        except ClinVarAPIError as exc:
            reset_transfer()
            return jsonify({"error": str(exc)}), 502

    @app.get("/api/transfer-safety")
    def api_transfer_safety():
        with state_lock:
            snapshot = dict(transfer_state)
        try:
            metrics = history_metrics()
        except (OSError, VCVHistoryStoreError):
            metrics = {"storage": "Unavailable", "storage_bytes": 0}
        return jsonify(
            {
                **_transfer_safety_status(snapshot),
                "vcv_history_storage": metrics["storage"],
                "vcv_history_storage_bytes": metrics["storage_bytes"],
            }
        )

    @app.get("/api/clinvar/status")
    def api_clinvar_status():
        return jsonify(lookup_state)

    return app


app = create_app()


def run_dashboard(*, open_browser: bool = True) -> None:
    """Run the dashboard locally without Flask debug mode."""
    if open_browser:
        threading.Timer(
            0.8, lambda: webbrowser.open("http://127.0.0.1:5000/version_history.html")
        ).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    run_dashboard()
