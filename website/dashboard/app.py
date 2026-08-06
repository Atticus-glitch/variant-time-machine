"""Simple local development dashboard for Variant Time Machine."""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import uuid
import webbrowser
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.ai_holdout_v4 import (  # noqa: E402
    AIHoldoutV4Error,
    ai_holdout_v4_summary,
    test_ai_holdout_v4_once,
)
from variant_time_machine.ai_holdout_v5 import (  # noqa: E402
    AIHoldoutV5Error,
    ai_holdout_v5_summary,
    test_ai_holdout_v5_once,
)
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
from variant_time_machine.clue_score import load_clue_score_config  # noqa: E402
from variant_time_machine.clue_score_experiment import (  # noqa: E402
    OUTPUT_FILENAMES as CLUE_SCORE_OUTPUT_FILENAMES,
)
from variant_time_machine.clue_score_experiment import (  # noqa: E402
    ClueScoreExperimentError,
    list_predictions,
    load_prediction_reviews,
    prediction_detail,
    prediction_summary,
    update_prediction_review,
)
from variant_time_machine.config import (  # noqa: E402
    AI_HOLDOUT_V4_RESULTS_DIR,
    AI_HOLDOUT_V5_RESULTS_DIR,
    CLINVAR_RELEASES,
    CLUE_SCORE_RESULTS_DB_PATH,
    CLUE_SCORE_RESULTS_DIR,
    HISTORICAL_RAW_DATA_DIR,
    HISTORICAL_VARIANT_DB_PATH,
    LARGE_DOWNLOAD_THRESHOLD_BYTES,
    MODEL_ERROR_REVIEW_PATH,
    MODEL_REGISTRY_DIR,
    PILOT_CURRENT_API_ESTIMATE_BYTES,
    PILOT_EXTRACTED_DIR,
    PILOT_RESULTS_DIR,
    PILOT_WORKSPACE_PATH,
    PROJECT_TIMELINE_PATH,
    RAW_DATA_DIR,
    RESOLVED_DIRECTION_RESULTS_DB_PATH,
    RESOLVED_DIRECTION_RESULTS_DIR,
    RESOLVED_DIRECTION_REVIEW_PATH,
    STATISTICAL_MODEL_V3_RESULTS_DIR,
    TABLES_DIR,
    VCV_HISTORY_DIR,
)
from variant_time_machine.download import download_clinvar_release  # noqa: E402
from variant_time_machine.historical_dataset import (  # noqa: E402
    historical_download_plan,
    validate_download_preflight,
)
from variant_time_machine.historical_variants import (  # noqa: E402
    HistoricalVariantDatabaseError,
    historical_database_metadata,
    historical_variant_detail,
    search_historical_variants,
)
from variant_time_machine.model_registry import (  # noqa: E402
    RegistryError,
    load_model_dashboard,
    load_prediction_explorer,
    load_project_timeline,
    prediction_explorer_detail,
    update_error_review,
    update_timeline_status,
)
from variant_time_machine.pilot_results import (  # noqa: E402
    OUTPUT_FILENAMES,
    PilotResultsError,
    aggregate_pilot_results,
    download_content,
    export_pilot_results,
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
from variant_time_machine.resolved_direction import (  # noqa: E402
    OUTPUT_FILENAMES as RESOLVED_OUTPUT_FILENAMES,
)
from variant_time_machine.resolved_direction import (  # noqa: E402
    load_resolved_direction_config,
    run_resolved_direction_experiment,
)
from variant_time_machine.v8_presentation import (  # noqa: E402
    V8PresentationError,
    list_review_queue,
    load_case_studies,
    load_json_object,
    load_review_notes,
    load_summary,
    sha256_file,
    update_review_decision,
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
PILOT_BATCH_MAX_BYTES = 100_000_000
PILOT_BATCH_MAX_CANDIDATES = 10
PILOT_BATCH_MANIFEST_MAX_BYTES = 1024 * 1024

PROJECT_EXPLANATION = (
    "Variant Time Machine asks whether information available about an uncertain "
    "genetic variant at an earlier date can help predict its later ClinVar "
    "classification. The project combines careful historical matching with an "
    "interpretable statistical experiment; it does not make medical decisions."
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
        "status": "Complete",
        "explanation": (
            "Resolved Direction V2 reuses frozen 2022-only summary-record clues."
        ),
    },
    {
        "step": 7,
        "name": "Models",
        "status": "Working",
        "explanation": (
            "The rule-based baseline is complete. No machine-learning model is "
            "complete."
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
    v5_output = AI_HOLDOUT_V5_RESULTS_DIR / "training_summary.json"
    if v5_output.is_file():
        modified = datetime.fromtimestamp(v5_output.stat().st_mtime, UTC).isoformat()
        return f"{v5_output.relative_to(PROJECT_ROOT)} modified {modified}"
    ai_output = AI_HOLDOUT_V4_RESULTS_DIR / "training_summary.json"
    if ai_output.is_file():
        modified = datetime.fromtimestamp(ai_output.stat().st_mtime, UTC).isoformat()
        return f"{ai_output.relative_to(PROJECT_ROOT)} modified {modified}"
    statistical_output = STATISTICAL_MODEL_V3_RESULTS_DIR / "metric_summary.json"
    if statistical_output.is_file():
        modified = datetime.fromtimestamp(
            statistical_output.stat().st_mtime, UTC
        ).isoformat()
        return f"{statistical_output.relative_to(PROJECT_ROOT)} modified {modified}"
    resolved_output = RESOLVED_DIRECTION_RESULTS_DIR / "metric_summary.json"
    if resolved_output.is_file():
        modified = datetime.fromtimestamp(
            resolved_output.stat().st_mtime, UTC
        ).isoformat()
        return f"{resolved_output.relative_to(PROJECT_ROOT)} modified {modified}"
    clue_score_output = CLUE_SCORE_RESULTS_DIR / "metric_summary.json"
    if clue_score_output.is_file():
        modified = datetime.fromtimestamp(
            clue_score_output.stat().st_mtime, UTC
        ).isoformat()
        return f"{clue_score_output.relative_to(PROJECT_ROOT)} modified {modified}"
    pilot_output = PILOT_RESULTS_DIR / "pilot_results.csv"
    if pilot_output.is_file():
        modified = datetime.fromtimestamp(pilot_output.stat().st_mtime, UTC).isoformat()
        return f"{pilot_output.relative_to(PROJECT_ROOT)} modified {modified}"
    outputs = sorted(
        TABLES_DIR.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    if not outputs:
        return "No saved timeline output found"
    newest = outputs[0]
    modified = datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat()
    return f"{newest.relative_to(PROJECT_ROOT)} modified {modified}"


def _system_status(pilot_results_root: Path = PILOT_RESULTS_DIR) -> dict[str, Any]:
    """Build a small status summary from the current local checkout."""
    in_virtual_environment = sys.prefix != sys.base_prefix
    test_files = sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
    raw_files = [
        path
        for path in RAW_DATA_DIR.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    timeline_files = sorted(TABLES_DIR.glob("*.csv"))
    disk = shutil.disk_usage(PROJECT_ROOT)
    extracted_files = sorted(PILOT_EXTRACTED_DIR.glob("*.json"))
    history_count = len(list_histories(VCV_HISTORY_DIR))
    files_created = [str(path.relative_to(PROJECT_ROOT)) for path in timeline_files]
    pilot_output = pilot_results_root / "pilot_results.csv"
    if pilot_output.is_file():
        try:
            files_created.append(str(pilot_output.relative_to(PROJECT_ROOT)))
        except ValueError:
            files_created.append(str(pilot_output))
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
        "database": "Indexed snapshots and Version 1, Version 2, and Version 3 results",
        "tests": f"{len(test_files)} test files available",
        "last_pipeline_run": _latest_pipeline_output(),
        "files_created": files_created,
        "raw_clinvar_files": len(raw_files),
        "pilot_strategy": "Review baseline errors; keep Version 1 frozen",
        "archive_scan": "Two archived summary snapshots indexed and evaluated",
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
        PILOT_RESULTS_ROOT=PILOT_RESULTS_DIR,
        VCV_HISTORY_ROOT=VCV_HISTORY_DIR,
        VCV_CURRENT_FETCHER=fetch_current_vcv,
        VCV_HISTORY_FETCHER=fetch_vcv_history,
        HISTORICAL_RAW_ROOT=HISTORICAL_RAW_DATA_DIR,
        HISTORICAL_DOWNLOADER=download_clinvar_release,
        HISTORICAL_DISK_USAGE=shutil.disk_usage,
        HISTORICAL_VARIANT_DB_PATH=HISTORICAL_VARIANT_DB_PATH,
        CLUE_SCORE_RESULTS_DB_PATH=RESOLVED_DIRECTION_RESULTS_DB_PATH,
        CLUE_SCORE_RESULTS_DIR=RESOLVED_DIRECTION_RESULTS_DIR,
        CLUE_SCORE_REVIEW_PATH=RESOLVED_DIRECTION_REVIEW_PATH,
        CLUE_SCORE_PARENT_DB_PATH=CLUE_SCORE_RESULTS_DB_PATH,
        CLUE_SCORE_RUNNER=run_resolved_direction_experiment,
        AI_HOLDOUT_V4_RESULTS_DIR=AI_HOLDOUT_V4_RESULTS_DIR,
        AI_HOLDOUT_V4_SOURCE_DB_PATH=RESOLVED_DIRECTION_RESULTS_DB_PATH,
        AI_HOLDOUT_V5_RESULTS_DIR=AI_HOLDOUT_V5_RESULTS_DIR,
        AI_HOLDOUT_V5_SOURCE_DB_PATH=RESOLVED_DIRECTION_RESULTS_DB_PATH,
        MODEL_REGISTRY_DIR=MODEL_REGISTRY_DIR,
        MODEL_ERROR_REVIEW_PATH=MODEL_ERROR_REVIEW_PATH,
        PROJECT_TIMELINE_PATH=PROJECT_TIMELINE_PATH,
        V8_SUMMARY_PATH=(
            PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_public_summary.json"
        ),
        V8_CASE_STUDIES_PATH=(
            PROJECT_ROOT / "outputs" / "case_studies" / "v8_case_studies.json"
        ),
        V8_REVIEW_QUEUE_PATH=(
            PROJECT_ROOT / "outputs" / "manual_review" / "v8_review_queue.csv"
        ),
        V8_REVIEW_NOTES_PATH=(
            PROJECT_ROOT / "outputs" / "manual_review" / "v8_review_notes.json"
        ),
        V8_AI_REVIEW_PATH=(
            PROJECT_ROOT / "outputs" / "manual_review" / "v8_ai_review_suggestions.json"
        ),
        V9_DATASET_DIR=PROJECT_ROOT / "data" / "processed" / "v9",
        V9_EXPLORATORY_DIR=PROJECT_ROOT / "outputs" / "v9_exploratory",
        V9_EXPLORATORY_CONFIG_PATH=PROJECT_ROOT / "config" / "v9_exploratory.json",
        V9_EXPLORATORY_CLUE_CONFIG_PATH=(
            PROJECT_ROOT / "config" / "clue_score_v1.yaml"
        ),
        V9_EXPLORATORY_DATASET_PATH=(
            PROJECT_ROOT / "data" / "processed" / "v9" / "v9_messy_dataset.csv"
        ),
        V9_EXPLORATORY_DATASET_MANIFEST_PATH=(
            PROJECT_ROOT / "data" / "processed" / "v9" / "v9_dataset_manifest.json"
        ),
        V8_DOWNLOADS={
            "v8_public_summary.json": PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_public_summary.json",
            "v8_metrics.json": PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_metrics.json",
            "v8_protocol_audit.json": PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_protocol_audit.json",
            "v8_vault_commitment.json": PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_vault_commitment.json",
            "v8_model_commitment.json": PROJECT_ROOT
            / "outputs"
            / "evaluations"
            / "frozen"
            / "v8_model_commitment.json",
            "temporal_test_predictions.csv": PROJECT_ROOT
            / "outputs"
            / "ai_temporal_v8"
            / "temporal_test_predictions.csv",
            "wrong_predictions.csv": PROJECT_ROOT
            / "outputs"
            / "error_analysis"
            / "model_v8_errors.csv",
            "v8_case_studies.json": PROJECT_ROOT
            / "outputs"
            / "case_studies"
            / "v8_case_studies.json",
            "error_analysis.csv": PROJECT_ROOT
            / "outputs"
            / "error_analysis"
            / "model_v8_errors.csv",
            "v8_review_queue.csv": PROJECT_ROOT
            / "outputs"
            / "manual_review"
            / "v8_review_queue.csv",
            "v8_review_queue_manifest.json": PROJECT_ROOT
            / "outputs"
            / "manual_review"
            / "v8_review_queue_manifest.json",
            "v8_ai_review_suggestions.json": PROJECT_ROOT
            / "outputs"
            / "manual_review"
            / "v8_ai_review_suggestions.json",
            "v8-ai-assisted-review.md": PROJECT_ROOT
            / "research"
            / "v8-ai-assisted-review.md",
            "one-page-abstract.md": PROJECT_ROOT / "research" / "one-page-abstract.md",
            "v8-case-studies.md": PROJECT_ROOT / "research" / "v8-case-studies.md",
            "v8-error-analysis.md": PROJECT_ROOT / "research" / "v8-error-analysis.md",
            "ai-temporal-v8-preregistration.md": PROJECT_ROOT
            / "research"
            / "ai-temporal-v8-preregistration.md",
            "ai-temporal-v8-results.md": PROJECT_ROOT
            / "research"
            / "ai-temporal-v8-results.md",
            "v8_poster_outline.md": PROJECT_ROOT / "research" / "poster-outline.md",
            "poster-outline.md": PROJECT_ROOT / "research" / "poster-outline.md",
            "strongest_truthful_claim.txt": PROJECT_ROOT
            / "research"
            / "strongest-truthful-claim.md",
            "strongest-truthful-claim.md": PROJECT_ROOT
            / "research"
            / "strongest-truthful-claim.md",
        },
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
    issued_batch_plans: dict[str, str] = {}
    issued_historical_plans: dict[str, dict[str, object]] = {}
    historical_operations: dict[str, dict[str, object]] = {}
    prediction_operations: dict[str, dict[str, object]] = {}

    def historical_plan() -> dict[str, object]:
        """Return the current no-network plan for the fixed release pair."""
        return historical_download_plan(
            Path(app.config["HISTORICAL_RAW_ROOT"]),
            disk_usage=app.config["HISTORICAL_DISK_USAGE"],
        )

    def run_historical_download(operation_id: str, plan: dict[str, object]) -> None:
        """Download an approved fixed pair sequentially in a background thread."""
        try:
            fresh_plan = historical_plan()
            validate_download_preflight(fresh_plan)
            downloaded: list[dict[str, object]] = []
            release_rows = plan["releases"]
            assert isinstance(release_rows, list)
            with state_lock:
                transfer_state["current_transfer"] = (
                    f"Historical dataset operation {operation_id} in progress"
                )
            for index, row in enumerate(release_rows, start=1):
                assert isinstance(row, dict)
                if not row.get("download_required"):
                    continue
                role = str(row["role"])
                release = CLINVAR_RELEASES[role]
                with state_lock:
                    historical_operations[operation_id]["progress"] = {
                        "index": index,
                        "count": len(release_rows),
                        "role": role,
                        "filename": release.filename,
                        "state": "downloading",
                    }
                downloader = app.config["HISTORICAL_DOWNLOADER"]
                data_path, metadata_path = downloader(
                    release,
                    Path(app.config["HISTORICAL_RAW_ROOT"]),
                    confirm=True,
                    reason=str(plan["purpose"]),
                )
                downloaded.append(
                    {
                        "role": role,
                        "data_path": str(data_path),
                        "metadata_path": str(metadata_path),
                        "size_bytes": data_path.stat().st_size,
                    }
                )
            actual_bytes = sum(int(item["size_bytes"]) for item in downloaded)
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
                transfer_state["total_api_bytes"] = (
                    int(transfer_state["total_api_bytes"]) + actual_bytes
                )
                transfer_state["last_request"] = {
                    "source": "Official NCBI ClinVar tab-delimited archive",
                    "purpose": plan["purpose"],
                    "estimated_max_bytes": plan["estimated_transfer_bytes"],
                    "actual_bytes": actual_bytes,
                }
                historical_operations[operation_id].update(
                    state="completed",
                    result={"downloaded": downloaded, "actual_bytes": actual_bytes},
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )
        except Exception as exc:  # background failures must remain observable
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
                historical_operations[operation_id].update(
                    state="failed",
                    error=str(exc),
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )

    def run_prediction_operation(operation_id: str) -> None:
        """Run the frozen full baseline while exposing measured stage progress."""

        def report(event: dict[str, object]) -> None:
            with state_lock:
                operation = prediction_operations[operation_id]
                events = operation["progress_events"]
                assert isinstance(events, list)
                public = {**event, "sequence": len(events) + 1}
                events.append(public)
                operation["progress"] = public

        try:
            runner = app.config["CLUE_SCORE_RUNNER"]
            report({"stage": "selecting_resolved_direction_cohort"})
            summary = runner(
                Path(app.config["CLUE_SCORE_PARENT_DB_PATH"]),
                Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"]),
                Path(app.config["CLUE_SCORE_RESULTS_DIR"]),
                overwrite=True,
            )
            report(
                {
                    "stage": "resolved_results_saved",
                    "count": summary["resolved_direction_records"],
                }
            )
            with state_lock:
                prediction_operations[operation_id].update(
                    state="completed",
                    result=summary,
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )
        except Exception as exc:  # background failures must remain observable
            with state_lock:
                prediction_operations[operation_id].update(
                    state="failed",
                    error=str(exc),
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )

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
        output_root = Path(app.config["PILOT_RESULTS_ROOT"])
        results_file = output_root / "pilot_results.csv"
        output_bandwidth = 0
        result_candidates = 0
        summary_path = output_root / "pilot_summary.json"
        if summary_path.is_file() and not summary_path.is_symlink():
            try:
                result_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if isinstance(result_summary, dict):
                    output_bandwidth = int(
                        result_summary.get("total_bytes_transferred", 0)
                    )
                    result_candidates = int(
                        result_summary.get("candidates_attempted", 0)
                    )
            except (OSError, ValueError, json.JSONDecodeError):
                output_bandwidth = 0
                result_candidates = 0
        batch_manifest = output_root / "batch_manifest.json"
        if (
            output_bandwidth == 0
            and batch_manifest.is_file()
            and not batch_manifest.is_symlink()
        ):
            try:
                manifest = json.loads(batch_manifest.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    output_bandwidth = int(
                        manifest.get(
                            "actual_new_batch_bytes", manifest.get("batch_bytes", 0)
                        )
                    )
            except (OSError, ValueError, json.JSONDecodeError):
                output_bandwidth = 0
        return {
            "candidates_selected": max(len(workspace["records"]), result_candidates),
            "current_records_retrieved": max(
                int(metrics["histories_explored"]), current_count
            ),
            "current_records_retrieved_this_session": current_count,
            **metrics,
            "pilot_results_file_created": results_file.is_file(),
            "pilot_output_bandwidth_bytes": output_bandwidth,
        }

    def clue_score_progress() -> dict[str, object]:
        """Return real cross-reference and frozen-baseline status."""
        cross_reference_records = 0
        try:
            historical = historical_database_metadata(
                Path(app.config["HISTORICAL_VARIANT_DB_PATH"])
            )
            cross_reference_records = int(historical.get("variant_count", 0))
        except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError):
            pass
        empty = {
            "cross_reference_records": cross_reference_records,
            "older_vus_records": 0,
            "eligible_scoring_records": 0,
            "predictions_completed": 0,
            "correct": 0,
            "wrong": 0,
            "no_prediction": 0,
            "not_scorable": 0,
            "latest_baseline_accuracy": None,
            "formula_version": "Resolved Direction V2",
            "last_run_date": None,
            "available": False,
        }
        try:
            summary = prediction_summary(Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"]))
        except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError):
            return empty
        return {
            **empty,
            "older_vus_records": summary["eligible_older_vus_records"],
            "eligible_scoring_records": summary["eligible_older_vus_records"],
            "predictions_completed": summary["predictions_made"],
            "correct": summary["correct"],
            "wrong": summary["wrong"],
            "no_prediction": summary["no_prediction"],
            "not_scorable": summary["not_scorable"],
            "latest_baseline_accuracy": summary["overall_accuracy"],
            "formula_version": summary["scoring_version"],
            "last_run_date": summary["completed_at_utc"],
            "available": True,
        }

    def dynamic_next_tasks(progress: dict[str, object]) -> tuple[str, ...]:
        v5_summary = ai_holdout_v5_summary(
            Path(app.config["AI_HOLDOUT_V5_RESULTS_DIR"])
        )
        if v5_summary.get("state") == "tested":
            return (
                "Review V5 errors without selecting only the favorable metric.",
                "Compare V5 accuracy and balanced accuracy with V4.",
                "Plan an independent later-snapshot validation cohort.",
            )
        if v5_summary.get("available"):
            return (
                "Open Prediction Results and approve the fresh V5 test once.",
                "Keep the V5 hidden records excluded from retraining.",
                "Report V5 accuracy and balanced accuracy whether better or worse.",
            )
        ai_summary = ai_holdout_v4_summary(
            Path(app.config["AI_HOLDOUT_V4_RESULTS_DIR"])
        )
        if ai_summary.get("state") == "tested":
            return (
                "Train frozen AI Holdout V5 without opening its fresh 100 records.",
                "Preserve the completed V4 result as a comparison baseline.",
                "Test V5 once from the Prediction Results page.",
            )
        if ai_summary.get("available"):
            return (
                "Open Prediction Results and approve the 100-record AI test once.",
                "Keep the hidden records excluded from all model training.",
                "Preserve the basic predictor as a comparison baseline.",
            )
        if Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"]).is_file():
            return (
                "Train AI Holdout V4 without opening its hidden 100 records.",
                "Review the unchanged basic predictor as a comparison baseline.",
                "Test the trained AI once from the Prediction Results page.",
            )
        if progress.get("pilot_results_file_created"):
            return (
                "Manually verify every detected classification change",
                "Review ambiguous or missing histories",
                "Expand the verified pilot to 25 variants",
            )
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

    def pilot_batch_plan(body: dict[str, object]) -> dict[str, object]:
        """Build a deterministic, no-network plan for a small pilot batch."""
        candidates = body.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidates must be a JSON list.")
        if not candidates:
            raise ValueError("Select at least one pilot candidate.")
        if len(candidates) > PILOT_BATCH_MAX_CANDIDATES:
            raise ValueError("A pilot batch is limited to 10 candidates.")
        accessions = [_vcv_base(candidate) for candidate in candidates]
        if len(set(accessions)) != len(accessions):
            raise ValueError("Pilot candidate VCV accessions must be unique.")
        reuse_existing = body.get("reuse_existing", True)
        if not isinstance(reuse_existing, bool):
            raise ValueError("reuse_existing must be true or false.")
        selection_rule = body.get("candidate_selection_rule", "")
        if not isinstance(selection_rule, str):
            raise ValueError("candidate_selection_rule must be text.")
        if len(selection_rule) > 1000:
            raise ValueError("candidate_selection_rule is limited to 1000 characters.")
        selection_bytes = body.get("candidate_selection_bytes", 0)
        selection_requests = body.get("candidate_selection_requests", [])
        if (
            not isinstance(selection_bytes, int)
            or isinstance(selection_bytes, bool)
            or selection_bytes < 0
        ):
            raise ValueError("candidate_selection_bytes must be a nonnegative integer.")
        if not isinstance(selection_requests, list) or len(selection_requests) > 10:
            raise ValueError(
                "candidate_selection_requests must contain at most 10 items."
            )
        cleaned_selection_requests: list[dict[str, object]] = []
        for item in selection_requests:
            if not isinstance(item, dict):
                raise ValueError("Each candidate selection request must be an object.")
            accession = _vcv_base(item.get("accession"))
            source = item.get("source_request")
            response_bytes = item.get("response_bytes")
            retrieved = item.get("retrieved_at_utc")
            if (
                not isinstance(source, str)
                or not source.startswith(f"{CLINVAR_EFETCH_URL}?")
                or len(source) > 2000
            ):
                raise ValueError(
                    "Candidate selection sources must be official EFetch requests."
                )
            if (
                not isinstance(response_bytes, int)
                or isinstance(response_bytes, bool)
                or response_bytes < 0
                or response_bytes > MAX_RESPONSE_BYTES
            ):
                raise ValueError("Candidate selection response bytes are invalid.")
            if not isinstance(retrieved, str) or not retrieved or len(retrieved) > 100:
                raise ValueError("Candidate selection retrieval time is required.")
            cleaned_selection_requests.append(
                {
                    "accession": accession,
                    "source_request": source,
                    "response_bytes": response_bytes,
                    "retrieved_at_utc": retrieved,
                }
            )
        if (
            sum(int(item["response_bytes"]) for item in cleaned_selection_requests)
            != selection_bytes
        ):
            raise ValueError(
                "candidate_selection_bytes must equal the recorded selection responses."
            )

        saved = set(list_histories(history_root())) if reuse_existing else set()
        planned_candidates = [
            {
                "accession": accession,
                "reused": accession in saved,
                "estimated_max_requests": 0 if accession in saved else 3,
            }
            for accession in accessions
        ]
        request_count = sum(
            int(candidate["estimated_max_requests"]) for candidate in planned_candidates
        )
        estimated_transfer = request_count * MAX_RESPONSE_BYTES
        reused_source_bytes = sum(
            int(load_history(history_root(), accession)["manifest"]["total_bytes"])
            for accession in accessions
            if accession in saved
        )
        estimated_total_pilot_transfer = (
            selection_bytes + reused_source_bytes + estimated_transfer
        )
        if estimated_total_pilot_transfer >= PILOT_BATCH_MAX_BYTES:
            raise TransferLimitError(
                "Pilot batch plans must remain below the 100,000,000-byte limit."
            )
        reused_count = sum(
            bool(candidate["reused"]) for candidate in planned_candidates
        )
        return {
            "schema_version": 1,
            "candidates": planned_candidates,
            "candidate_count": len(planned_candidates),
            "reused_count": reused_count,
            "reuse_existing": reuse_existing,
            "estimated_max_requests": request_count,
            "estimated_max_transfer": estimated_transfer,
            "estimated_total_pilot_transfer": estimated_total_pilot_transfer,
            "candidate_selection_bytes": selection_bytes,
            "candidate_selection_requests": cleaned_selection_requests,
            "reused_source_bytes": reused_source_bytes,
            "source": CLINVAR_EFETCH_URL,
            "purpose": (
                "Retrieve each selected candidate's current, first, and newest "
                "official ClinVar VCV records"
            ),
            "candidate_selection_rule": selection_rule,
            "confirmation": (
                "I approve this bounded, sequential official ClinVar EFetch pilot "
                "batch."
            ),
            "requires_approval": True,
        }

    def pilot_batch_plan_digest(plan: dict[str, object]) -> str:
        """Identify the exact server-issued plan approved by the researcher."""
        content = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(content).hexdigest()

    def write_batch_manifest(payload: dict[str, object]) -> None:
        """Atomically write one bounded manifest in the configured output root."""
        root = Path(app.config["PILOT_RESULTS_ROOT"])
        if root.is_symlink():
            raise OSError("The pilot results root cannot be a symbolic link.")
        root.mkdir(parents=True, exist_ok=True)
        path = root / "batch_manifest.json"
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise OSError("Refusing to replace an unsafe batch manifest.")
        content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        if len(content) > PILOT_BATCH_MANIFEST_MAX_BYTES:
            raise ValueError("The pilot batch manifest exceeds its 1 MB limit.")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".batch_manifest.", suffix=".tmp", dir=root
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def run_pilot_batch_operation(
        operation_id: str,
        plan: dict[str, object],
        cancel_event: threading.Event,
    ) -> None:
        """Retrieve one approved pilot batch serially and export its outputs."""
        attempts: list[dict[str, object]] = []
        batch_bytes = 0
        stopped_error: str | None = None
        cancelled = False

        def report(accession: str, index: int, event: dict[str, object]) -> None:
            with state_lock:
                operation = operations[operation_id]
                events = operation["progress_events"]
                assert isinstance(events, list)
                scoped = {
                    **event,
                    "candidate": accession,
                    "candidate_index": index,
                    "candidate_count": plan["candidate_count"],
                    "sequence": len(events) + 1,
                }
                events.append(scoped)
                operation["progress"] = dict(scoped)

        try:
            with state_lock:
                transfer_state["current_transfer"] = (
                    f"Pilot batch operation {operation_id} in progress"
                )
            candidates = plan["candidates"]
            assert isinstance(candidates, list)
            for index, candidate in enumerate(candidates, start=1):
                assert isinstance(candidate, dict)
                accession = str(candidate["accession"])
                attempt: dict[str, object] = {
                    "accession": accession,
                    "vcv_accession": accession,
                    "attempted": True,
                    "reused": bool(candidate["reused"]),
                    "status": "pending",
                    "failure": "",
                    "batch_bytes": 0,
                    "bytes_transferred": 0,
                    "source_urls": [CLINVAR_EFETCH_URL],
                    "source_requests": [{"request": CLINVAR_EFETCH_URL}],
                }
                attempts.append(attempt)
                if cancel_event.is_set():
                    attempt["status"] = "cancelled"
                    attempt["failure"] = "Batch cancelled before this candidate."
                    cancelled = True
                    break
                if candidate["reused"]:
                    attempt["status"] = "reused"
                    report(accession, index, {"event": "reused"})
                    continue

                report(accession, index, {"event": "candidate_started"})
                before_candidate = batch_bytes
                try:
                    current_fetcher = app.config["VCV_CURRENT_FETCHER"]
                    with ncbi_request_lock:
                        current = current_fetcher(accession)
                    if not isinstance(current, VersionResult):
                        raise VCVHistoryError(
                            "Current VCV fetcher returned an invalid result."
                        )
                    if (
                        current.record is not None
                        and current.record.accession != accession
                    ):
                        raise VCVHistoryError(
                            "Current VCV response accession did not match."
                        )
                    batch_bytes += current.response_bytes
                    attempt["batch_bytes"] = current.response_bytes
                    attempt["bytes_transferred"] = current.response_bytes
                    attempt["source_urls"] = [current.source_request]
                    attempt["source_requests"] = [{"request": current.source_request}]
                    if batch_bytes >= PILOT_BATCH_MAX_BYTES:
                        raise TransferLimitError(
                            "Pilot batch reached the 100,000,000-byte limit."
                        )
                    if current.status != "available" or current.record is None:
                        attempt["status"] = "failed"
                        attempt["failure"] = current.message or (
                            f"Current VCV record was {current.status}."
                        )
                        report(accession, index, {"event": "candidate_failed"})
                        continue

                    max_candidate_total = min(
                        MAX_TOTAL_BYTES, PILOT_BATCH_MAX_BYTES - before_candidate - 1
                    )
                    history_fetcher = app.config["VCV_HISTORY_FETCHER"]

                    def candidate_progress(
                        event: dict[str, object],
                        candidate_accession: str = accession,
                        candidate_index: int = index,
                    ) -> None:
                        report(candidate_accession, candidate_index, event)

                    with ncbi_request_lock:
                        result = history_fetcher(
                            accession,
                            mode="endpoints",
                            max_requests=2,
                            max_total_bytes=max_candidate_total,
                            cancel=cancel_event,
                            progress=candidate_progress,
                            current_result=current,
                        )
                    if not isinstance(result, VCVHistoryResult):
                        raise VCVHistoryError(
                            "History fetcher returned an invalid result."
                        )
                    candidate_bytes = result.total_response_bytes
                    if before_candidate + candidate_bytes >= PILOT_BATCH_MAX_BYTES:
                        raise TransferLimitError(
                            "Pilot batch reached the 100,000,000-byte limit."
                        )
                    batch_bytes = before_candidate + candidate_bytes
                    attempt["batch_bytes"] = candidate_bytes
                    attempt["bytes_transferred"] = candidate_bytes
                    attempt["source_urls"] = list(
                        dict.fromkeys(
                            item.source_request
                            for item in (result.current_result, *result.results)
                        )
                    )
                    attempt["source_requests"] = [
                        {"request": source}
                        for source in attempt["source_urls"]
                        if isinstance(source, str)
                    ]
                    save_history(
                        history_root(),
                        result,
                        app_version="0.1.0",
                        git_commit=_git_commit(),
                    )
                    attempt["status"] = "partial" if result.cancelled else "completed"
                    report(
                        accession,
                        index,
                        {"event": "candidate_saved", "status": attempt["status"]},
                    )
                    if result.cancelled:
                        cancelled = True
                        break
                except RetrievalCancelled as exc:
                    attempt["status"] = "cancelled"
                    attempt["failure"] = str(exc)
                    cancelled = True
                    break
                except TransferLimitError as exc:
                    attempt["status"] = "failed"
                    attempt["failure"] = str(exc)
                    stopped_error = str(exc)
                    report(accession, index, {"event": "budget_failed"})
                    break
                except Exception as exc:  # candidate failures must not stop the batch
                    attempt["status"] = "failed"
                    attempt["failure"] = str(exc)
                    report(accession, index, {"event": "candidate_failed"})

            completed_at = datetime.now(UTC).isoformat()
            manifest = {
                "schema_version": 1,
                "candidate_selection_rule": plan["candidate_selection_rule"],
                "candidate_selection_bytes": plan["candidate_selection_bytes"],
                "candidate_selection_requests": plan["candidate_selection_requests"],
                "candidates": attempts,
                "candidate_count": plan["candidate_count"],
                "reused_count": plan["reused_count"],
                "plan_estimate": {
                    "estimated_max_requests": plan["estimated_max_requests"],
                    "estimated_max_transfer": plan["estimated_max_transfer"],
                },
                "approved_plan_digest": plan["plan_digest"],
                "plan_issued_at_utc": plan["plan_issued_at_utc"],
                "approved_at_utc": plan["approved_at_utc"],
                "batch_bytes": batch_bytes,
                "actual_new_batch_bytes": batch_bytes,
                "source_urls": [CLINVAR_EFETCH_URL],
                "retrieval_completed_at_utc": completed_at,
            }
            write_batch_manifest(manifest)
            output = export_pilot_results(
                history_root(),
                Path(app.config["PILOT_RESULTS_ROOT"]),
                generated_at_utc=completed_at,
            )
            summary = output.get("summary", {})
            with state_lock:
                transfer_state["total_api_bytes"] = (
                    int(transfer_state["total_api_bytes"]) + batch_bytes
                )
                transfer_state["current_transfer"] = "0 bytes; idle"
                transfer_state["last_request"] = {
                    "source": CLINVAR_EFETCH_URL,
                    "purpose": plan["purpose"],
                    "actual_bytes": batch_bytes,
                    "estimated_max_bytes": plan["estimated_max_transfer"],
                }
                operations[operation_id].update(
                    state=(
                        "cancelled"
                        if cancelled
                        else "failed"
                        if stopped_error
                        else "completed"
                    ),
                    result={
                        "batch_bytes": batch_bytes,
                        "actual_new_batch_bytes": batch_bytes,
                        "manifest": manifest,
                        "output_summary": summary,
                    },
                    error=stopped_error,
                    finished_at_utc=completed_at,
                )
        except Exception as exc:  # background failures must remain observable
            with state_lock:
                transfer_state["current_transfer"] = "0 bytes; idle"
                operations[operation_id].update(
                    state="failed",
                    error=str(exc),
                    finished_at_utc=datetime.now(UTC).isoformat(),
                )

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/overview.html")
    def overview_page():
        return send_from_directory(Path(__file__).parent, "overview.html")

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

    @app.get("/pilot_results.html")
    def pilot_results_page():
        return send_from_directory(Path(__file__).parent, "pilot_results.html")

    @app.get("/historical_dataset.html")
    def historical_dataset_page():
        return send_from_directory(Path(__file__).parent, "historical_dataset.html")

    @app.get("/historical_variants.html")
    def historical_variants_page():
        return send_from_directory(Path(__file__).parent, "historical_variants.html")

    @app.get("/prediction_results.html")
    def prediction_results_page():
        return send_from_directory(Path(__file__).parent, "prediction_results.html")

    @app.get("/model_versions.html")
    def model_versions_page():
        return send_from_directory(Path(__file__).parent, "model_versions.html")

    @app.get("/prediction_explorer.html")
    def prediction_explorer_page():
        return send_from_directory(Path(__file__).parent, "prediction_explorer.html")

    @app.get("/research_timeline.html")
    def research_timeline_page():
        return send_from_directory(Path(__file__).parent, "research_timeline.html")

    @app.get("/v8_results.html")
    def v8_results_page():
        return send_from_directory(Path(__file__).parent, "v8_results.html")

    @app.get("/v8_review.html")
    def v8_review_page():
        return send_from_directory(Path(__file__).parent, "v8_review.html")

    @app.get("/v9_dataset.html")
    def v9_dataset_page():
        return send_from_directory(Path(__file__).parent, "v9_dataset.html")

    @app.get("/v9_training.html")
    def v9_training_page():
        return send_from_directory(Path(__file__).parent, "v9_training.html")

    @app.get("/v9_results.html")
    def v9_results_page():
        return send_from_directory(Path(__file__).parent, "v9_results.html")

    @app.get("/v9_explorer.html")
    def v9_explorer_page():
        return send_from_directory(Path(__file__).parent, "v9_explorer.html")

    @app.get("/api/v9/dataset-summary")
    def api_v9_dataset_summary():
        try:
            manifest = load_json_object(
                Path(app.config["V9_DATASET_DIR"]) / "v9_dataset_manifest.json"
            )
            notes_path = Path(app.config["V8_REVIEW_NOTES_PATH"])
            recorded_hashes = manifest.get("review_file_hashes", {})
            recorded_notes_hash = next(
                (
                    value
                    for key, value in recorded_hashes.items()
                    if str(key).endswith("v8_review_notes.json")
                ),
                None,
            )
            manifest["review_store_changed_since_build"] = (
                recorded_notes_hash != sha256_file(notes_path)
            )
            queue_path = Path(app.config["V8_REVIEW_QUEUE_PATH"])
            recorded_queue_hash = next(
                (
                    value
                    for key, value in recorded_hashes.items()
                    if str(key).endswith("v8_review_queue.csv")
                ),
                None,
            )
            stale_reasons = []
            if manifest["review_store_changed_since_build"]:
                stale_reasons.append("review store changed after dataset build")
            if recorded_queue_hash != sha256_file(queue_path):
                stale_reasons.append("review queue changed after dataset build")
            output_hashes = manifest.get("output_hashes", {})
            for filename, expected_hash in output_hashes.items():
                output_path = Path(app.config["V9_DATASET_DIR"]) / filename
                if (
                    not output_path.is_file()
                    or output_path.is_symlink()
                    or sha256_file(output_path) != expected_hash
                ):
                    stale_reasons.append(f"generated output changed: {filename}")
            for relative, expected_hash in manifest.get(
                "implementation_hashes", {}
            ).items():
                source_path = PROJECT_ROOT / relative
                if (
                    not source_path.is_file()
                    or source_path.is_symlink()
                    or sha256_file(source_path) != expected_hash
                ):
                    stale_reasons.append(f"implementation changed: {relative}")
            manifest["artifacts_stale"] = bool(stale_reasons)
            manifest["stale_reasons"] = stale_reasons
            return jsonify(manifest)
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V9 dataset preparation unavailable: {exc}"}), 503

    def load_v9_exploratory_bundle() -> tuple[Path, dict[str, Any], list[str]]:
        output_dir = Path(app.config["V9_EXPLORATORY_DIR"])
        manifest = load_json_object(output_dir / "run_manifest.json")
        if (
            manifest.get("status") != "exploratory_opened_v8_only"
            or manifest.get("official_v9_winner") is not None
            or manifest.get("final_test_evaluated") is not False
        ):
            raise V8PresentationError("Exploratory V9 lock state is invalid.")
        stale_reasons = []
        source_checks = {
            "config_sha256": Path(app.config["V9_EXPLORATORY_CONFIG_PATH"]),
            "clue_score_config_sha256": Path(
                app.config["V9_EXPLORATORY_CLUE_CONFIG_PATH"]
            ),
            "dataset_sha256": Path(app.config["V9_EXPLORATORY_DATASET_PATH"]),
            "dataset_manifest_sha256": Path(
                app.config["V9_EXPLORATORY_DATASET_MANIFEST_PATH"]
            ),
        }
        for field, path in source_checks.items():
            if (
                not path.is_file()
                or path.is_symlink()
                or manifest.get(field) != sha256_file(path)
            ):
                stale_reasons.append(f"source changed: {path.name}")
        for filename, expected_hash in manifest.get("output_hashes", {}).items():
            path = output_dir / filename
            if (
                not path.is_file()
                or path.is_symlink()
                or sha256_file(path) != expected_hash
            ):
                stale_reasons.append(f"generated output changed: {filename}")
        for relative, expected_hash in manifest.get(
            "implementation_hashes", {}
        ).items():
            path = PROJECT_ROOT / relative
            if (
                not path.is_file()
                or path.is_symlink()
                or sha256_file(path) != expected_hash
            ):
                stale_reasons.append(f"implementation changed: {relative}")
        return output_dir, manifest, stale_reasons

    @app.get("/api/v9/exploratory-summary")
    def api_v9_exploratory_summary():
        try:
            output_dir, manifest, stale_reasons = load_v9_exploratory_bundle()
            if stale_reasons:
                return jsonify(
                    {
                        "error": "V9 exploratory artifacts are stale.",
                        "artifacts_stale": True,
                        "stale_reasons": stale_reasons,
                    }
                ), 409
            return jsonify(
                {
                    "manifest": manifest,
                    "metrics": load_json_object(output_dir / "candidate_metrics.json"),
                    "bootstrap": load_json_object(
                        output_dir / "bootstrap_intervals.json"
                    ),
                    "artifacts_stale": False,
                    "stale_reasons": [],
                }
            )
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V9 exploration unavailable: {exc}"}), 503

    @app.get("/api/v9/exploratory/download/<filename>")
    def api_v9_exploratory_download(filename: str):
        allowed = {
            "bootstrap_intervals.json",
            "calibration_bins.csv",
            "candidate_failures.json",
            "candidate_metrics.csv",
            "candidate_metrics.json",
            "fold_assignments.csv",
            "nested_selections.json",
            "oof_predictions.csv",
            "run_manifest.json",
        }
        if filename not in allowed:
            return jsonify({"error": "Unknown V9 exploratory download."}), 404
        try:
            output_dir, _, stale_reasons = load_v9_exploratory_bundle()
            if stale_reasons:
                return jsonify(
                    {
                        "error": "V9 exploratory artifacts are stale.",
                        "stale_reasons": stale_reasons,
                    }
                ), 409
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V9 exploration unavailable: {exc}"}), 503
        path = output_dir / filename
        if not path.is_file() or path.is_symlink():
            return jsonify({"error": "V9 exploratory download is unavailable."}), 404
        return send_from_directory(output_dir, filename, as_attachment=True)

    @app.get("/api/v9/download/<filename>")
    def api_v9_download(filename: str):
        allowed = {
            "v9_messy_dataset.csv",
            "v9_clean_reviewed_dataset.csv",
            "v9_excluded_records.csv",
            "v9_needs_expert_review.csv",
            "v9_partition_manifest.csv",
            "v9_dataset_manifest.json",
        }
        if filename not in allowed:
            return jsonify({"error": "Unknown V9 dataset download."}), 404
        path = Path(app.config["V9_DATASET_DIR"]) / filename
        if not path.is_file() or path.is_symlink():
            return jsonify({"error": "V9 dataset download is unavailable."}), 404
        if filename != "v9_dataset_manifest.json":
            try:
                manifest = load_json_object(
                    Path(app.config["V9_DATASET_DIR"]) / "v9_dataset_manifest.json"
                )
                expected_hash = manifest.get("output_hashes", {}).get(filename)
                recorded_hashes = manifest.get("review_file_hashes", {})
                current_sources = {
                    "v8_review_queue.csv": sha256_file(
                        Path(app.config["V8_REVIEW_QUEUE_PATH"])
                    ),
                    "v8_review_notes.json": sha256_file(
                        Path(app.config["V8_REVIEW_NOTES_PATH"])
                    ),
                }
                sources_match = all(
                    any(
                        str(key).endswith(source_name) and value == current_hash
                        for key, value in recorded_hashes.items()
                    )
                    for source_name, current_hash in current_sources.items()
                )
                implementation_matches = all(
                    (PROJECT_ROOT / relative).is_file()
                    and not (PROJECT_ROOT / relative).is_symlink()
                    and sha256_file(PROJECT_ROOT / relative) == expected
                    for relative, expected in manifest.get(
                        "implementation_hashes", {}
                    ).items()
                )
                if (
                    expected_hash != sha256_file(path)
                    or not sources_match
                    or not implementation_matches
                ):
                    return jsonify(
                        {
                            "error": (
                                "V9 dataset artifact is stale; rebuild before download."
                            )
                        }
                    ), 409
            except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
                return jsonify(
                    {"error": f"V9 dataset integrity unavailable: {exc}"}
                ), 503
        return send_file(path, as_attachment=True, download_name=filename)

    @app.get("/api/v8/summary")
    def api_v8_summary():
        try:
            summary = load_summary(Path(app.config["V8_SUMMARY_PATH"]))
            queue = list_review_queue(
                Path(app.config["V8_REVIEW_QUEUE_PATH"]),
                Path(app.config["V8_REVIEW_NOTES_PATH"]),
            )
            return jsonify(
                {**summary, "completed_review_count": queue["completed_review_count"]}
            )
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V8 summary unavailable: {exc}"}), 503

    @app.get("/api/v8/case-studies")
    def api_v8_case_studies():
        try:
            return jsonify(load_case_studies(Path(app.config["V8_CASE_STUDIES_PATH"])))
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V8 case studies unavailable: {exc}"}), 503

    @app.get("/api/v8/review-queue")
    def api_v8_review_queue():
        try:

            def enabled(name: str) -> bool:
                return request.args.get(name, "").casefold() in {"1", "true", "yes"}

            return jsonify(
                list_review_queue(
                    Path(app.config["V8_REVIEW_QUEUE_PATH"]),
                    Path(app.config["V8_REVIEW_NOTES_PATH"]),
                    confusion_group=request.args.get("confusion_group", ""),
                    disagreement=enabled("disagreement"),
                    high_confidence=enabled("high_confidence"),
                    gene=request.args.get("gene", ""),
                    consequence=request.args.get("consequence", ""),
                    match_warning=enabled("match_warning"),
                    status=request.args.get("status", ""),
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("page_size", "25")),
                )
            )
        except (V8PresentationError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"V8 review queue unavailable: {exc}"}), 503

    @app.get("/api/v8/review-notes")
    def api_v8_review_notes():
        try:
            return jsonify(load_review_notes(Path(app.config["V8_REVIEW_NOTES_PATH"])))
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify({"error": f"V8 review notes unavailable: {exc}"}), 503

    @app.get("/api/v8/ai-review-suggestions")
    def api_v8_ai_review_suggestions():
        try:
            payload = load_json_object(Path(app.config["V8_AI_REVIEW_PATH"]))
            if (
                payload.get("review_type")
                != "ai_assisted_suggestion_not_human_manual_review"
                or payload.get("records_reviewed") != 105
            ):
                raise V8PresentationError("AI review suggestion artifact is invalid.")
            return jsonify(payload)
        except (OSError, json.JSONDecodeError, V8PresentationError) as exc:
            return jsonify(
                {"error": f"V8 AI review suggestions unavailable: {exc}"}
            ), 503

    @app.patch("/api/v8/review/<variation_id>")
    def api_v8_review_decision(variation_id: str):
        try:
            body = _json_body()
            review = update_review_decision(
                Path(app.config["V8_REVIEW_QUEUE_PATH"]),
                Path(app.config["V8_REVIEW_NOTES_PATH"]),
                variation_id,
                body,
            )
            return jsonify({"variation_id": variation_id, "review": review})
        except (V8PresentationError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not save V8 review: {exc}"}), 503

    @app.get("/api/v8/download/<filename>")
    def api_v8_download(filename: str):
        downloads = app.config["V8_DOWNLOADS"]
        path = Path(downloads[filename]) if filename in downloads else None
        if path is None:
            return jsonify({"error": "Unknown V8 download."}), 404
        if not path.is_file() or path.is_symlink():
            return jsonify({"error": "V8 download is unavailable."}), 404
        return send_file(path, as_attachment=True, download_name=filename)

    @app.get("/api/model-versions")
    def api_model_versions():
        try:
            return jsonify(load_model_dashboard(PROJECT_ROOT))
        except (OSError, RegistryError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Model registry unavailable: {exc}"}), 503

    @app.get("/api/model-versions/<model_id>")
    def api_model_version(model_id: str):
        try:
            payload = load_model_dashboard(PROJECT_ROOT)
            model = next(
                (
                    item
                    for item in payload["model_records"]
                    if item["model_id"].casefold() == model_id.casefold()
                ),
                None,
            )
            if model is None:
                return jsonify({"error": "Model version not found."}), 404
            return jsonify(model)
        except (OSError, RegistryError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Model registry unavailable: {exc}"}), 503

    @app.get("/api/prediction-explorer")
    def api_prediction_explorer():
        try:
            return jsonify(
                load_prediction_explorer(
                    PROJECT_ROOT, Path(app.config["MODEL_ERROR_REVIEW_PATH"])
                )
            )
        except (OSError, RegistryError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Prediction Explorer unavailable: {exc}"}), 503

    @app.get("/api/prediction-explorer/<variation_id>")
    def api_prediction_explorer_detail(variation_id: str):
        try:
            return jsonify(
                prediction_explorer_detail(
                    PROJECT_ROOT,
                    variation_id,
                    Path(app.config["MODEL_ERROR_REVIEW_PATH"]),
                )
            )
        except RegistryError as exc:
            return jsonify({"error": str(exc)}), 404
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Prediction detail unavailable: {exc}"}), 503

    @app.patch("/api/prediction-explorer/<model_id>/<variation_id>/review")
    def api_prediction_explorer_review(model_id: str, variation_id: str):
        try:
            body = _json_body()
            if model_id.upper() == "V8":
                raise RegistryError(
                    "V8 reviews must use the focused Manual Review Queue."
                )
            detail = prediction_explorer_detail(
                PROJECT_ROOT,
                variation_id,
                Path(app.config["MODEL_ERROR_REVIEW_PATH"]),
            )
            normalized_model = model_id.upper()
            if normalized_model not in detail["model_results"]:
                raise RegistryError(
                    "This Variation ID was not evaluated by the selected model."
                )
            review = update_error_review(
                Path(app.config["MODEL_ERROR_REVIEW_PATH"]),
                normalized_model,
                variation_id,
                status=str(body.get("status", "unreviewed")),
                category=str(body.get("category", "unknown")),
                notes=str(body.get("notes", "")),
            )
            return jsonify({"review": review})
        except RegistryError as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not save review: {exc}"}), 503

    @app.get("/api/research-timeline")
    def api_research_timeline():
        try:
            return jsonify(
                load_project_timeline(Path(app.config["PROJECT_TIMELINE_PATH"]))
            )
        except (OSError, RegistryError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Research timeline unavailable: {exc}"}), 503

    @app.patch("/api/research-timeline/status")
    def api_research_timeline_status():
        try:
            body = _json_body()
            task = update_timeline_status(
                Path(app.config["PROJECT_TIMELINE_PATH"]),
                str(body.get("title", "")),
                str(body.get("status", "")),
            )
            return jsonify({"task": task})
        except RegistryError as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not update timeline: {exc}"}), 503

    @app.get("/api/predictions/formula")
    def api_prediction_formula():
        try:
            return jsonify(
                {
                    "formula": load_resolved_direction_config(),
                    "parent_formula": load_clue_score_config(),
                }
            )
        except (OSError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 503

    @app.get("/api/ai-v4/summary")
    def api_ai_v4_summary():
        try:
            return jsonify(
                ai_holdout_v4_summary(Path(app.config["AI_HOLDOUT_V4_RESULTS_DIR"]))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"AI Holdout V4 is unavailable: {exc}"}), 503

    @app.post("/api/ai-v4/test")
    def api_ai_v4_test():
        try:
            if _json_body().get("approved") is not True:
                return jsonify(
                    {"error": "Approve opening the frozen 100-record test first."}
                ), 428
            metrics = test_ai_holdout_v4_once(
                Path(app.config["AI_HOLDOUT_V4_SOURCE_DB_PATH"]),
                Path(app.config["AI_HOLDOUT_V4_RESULTS_DIR"]),
            )
            return jsonify(metrics)
        except FileExistsError as exc:
            return jsonify({"error": str(exc)}), 409
        except (AIHoldoutV4Error, OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not test AI Holdout V4: {exc}"}), 503

    @app.get("/api/ai-v5/summary")
    def api_ai_v5_summary():
        try:
            return jsonify(
                ai_holdout_v5_summary(Path(app.config["AI_HOLDOUT_V5_RESULTS_DIR"]))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"AI Holdout V5 is unavailable: {exc}"}), 503

    @app.post("/api/ai-v5/test")
    def api_ai_v5_test():
        try:
            if _json_body().get("approved") is not True:
                return jsonify(
                    {"error": "Approve opening the fresh V5 hidden test first."}
                ), 428
            metrics = test_ai_holdout_v5_once(
                Path(app.config["AI_HOLDOUT_V5_SOURCE_DB_PATH"]),
                Path(app.config["AI_HOLDOUT_V5_RESULTS_DIR"]),
            )
            return jsonify(metrics)
        except FileExistsError as exc:
            return jsonify({"error": str(exc)}), 409
        except (AIHoldoutV5Error, OSError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not test AI Holdout V5: {exc}"}), 503

    @app.get("/api/predictions/summary")
    def api_prediction_summary():
        try:
            path = Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"])
            if not path.is_file():
                return jsonify(
                    {
                        "available": False,
                        "formula": load_resolved_direction_config(),
                        "parent_formula": load_clue_score_config(),
                        "message": "Resolved Direction V2 has not been run yet.",
                    }
                )
            return jsonify(
                {
                    "available": True,
                    "summary": prediction_summary(path),
                    "formula": load_resolved_direction_config(),
                    "parent_formula": load_clue_score_config(),
                }
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            return jsonify({"error": f"Prediction summary unavailable: {exc}"}), 503

    @app.get("/api/predictions")
    def api_predictions():
        try:
            review_document = load_prediction_reviews(
                Path(app.config["CLUE_SCORE_REVIEW_PATH"])
            )
            reviews = review_document["reviews"]
            result_filter = request.args.get("filter", "all")
            query_filter = "all" if result_filter == "needs_review" else result_filter
            result = list_predictions(
                Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"]),
                query=request.args.get("query", ""),
                result_filter=query_filter,
                sort=request.args.get("sort", "default"),
                page=request.args.get("page", 1, type=int) or 1,
                page_size=request.args.get("page_size", 50, type=int) or 50,
                reviews=reviews if isinstance(reviews, dict) else {},
            )
            if result_filter == "needs_review":
                result["rows"] = [
                    row
                    for row in result["rows"]
                    if row["manual_review_status"] in {"unreviewed", "ambiguous"}
                ]
            return jsonify(result)
        except (ClueScoreExperimentError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Prediction results unavailable: {exc}"}), 503

    @app.get("/api/predictions/<variation_id>")
    def api_prediction_detail(variation_id: str):
        try:
            reviews = load_prediction_reviews(
                Path(app.config["CLUE_SCORE_REVIEW_PATH"])
            )["reviews"]
            review = reviews.get(variation_id, {}) if isinstance(reviews, dict) else {}
            return jsonify(
                prediction_detail(
                    Path(app.config["CLUE_SCORE_RESULTS_DB_PATH"]),
                    variation_id,
                    review,
                )
            )
        except ClueScoreExperimentError as exc:
            return jsonify({"error": str(exc)}), 404
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Prediction detail unavailable: {exc}"}), 503

    @app.patch("/api/predictions/<variation_id>/review")
    def api_prediction_review(variation_id: str):
        try:
            review = update_prediction_review(
                variation_id,
                _json_body(),
                Path(app.config["CLUE_SCORE_REVIEW_PATH"]),
            )
            return jsonify({"variation_id": variation_id, "review": review})
        except (ClueScoreExperimentError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Could not save prediction review: {exc}"}), 503

    @app.post("/api/predictions/run")
    def api_run_predictions():
        try:
            body = _json_body()
            if body.get("approved") is not True:
                return jsonify(
                    {"error": "Review and approve frozen Resolved Direction V2 first."}
                ), 428
            if body.get("scoring_version") != "Resolved Direction V2":
                raise ValueError("Only frozen Resolved Direction V2 may be run here.")
            with state_lock:
                if any(
                    item["state"] == "running"
                    for item in prediction_operations.values()
                ):
                    return jsonify(
                        {"error": "A Clue Score experiment is already running."}
                    ), 409
                operation_id = uuid.uuid4().hex
                prediction_operations[operation_id] = {
                    "operation_id": operation_id,
                    "state": "running",
                    "progress": None,
                    "progress_events": [],
                    "result": None,
                    "error": None,
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "finished_at_utc": None,
                }
            thread = threading.Thread(
                target=run_prediction_operation,
                args=(operation_id,),
                daemon=True,
                name=f"clue-score-{operation_id[:8]}",
            )
            thread.start()
            return jsonify({"operation_id": operation_id, "state": "running"}), 202
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/predictions/operations/<operation_id>")
    def api_prediction_operation(operation_id: str):
        with state_lock:
            operation = prediction_operations.get(operation_id)
            if operation is None:
                return jsonify({"error": "Prediction operation not found."}), 404
            return jsonify(operation)

    @app.get("/api/predictions/download/<filename>")
    def api_prediction_download(filename: str):
        allowed_outputs = set(CLUE_SCORE_OUTPUT_FILENAMES) | set(
            RESOLVED_OUTPUT_FILENAMES
        )
        if filename not in allowed_outputs:
            return jsonify({"error": "Unknown prediction output."}), 404
        root = Path(app.config["CLUE_SCORE_RESULTS_DIR"])
        path = root / filename
        if not path.is_file() or path.is_symlink():
            return jsonify({"error": "Prediction output is unavailable."}), 404
        return send_from_directory(root, filename, as_attachment=True)

    @app.get("/api/historical-variants")
    def api_historical_variants():
        try:
            database = Path(app.config["HISTORICAL_VARIANT_DB_PATH"])
            result = search_historical_variants(
                database,
                query=request.args.get("query", ""),
                change_status=request.args.get("change_status", ""),
                page=request.args.get("page", 1, type=int) or 1,
                page_size=request.args.get("page_size", 50, type=int) or 50,
            )
            return jsonify(
                {**result, "metadata": historical_database_metadata(database)}
            )
        except HistoricalVariantDatabaseError as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Historical index unavailable: {exc}"}), 503

    @app.get("/api/historical-variants/<variation_id>")
    def api_historical_variant_detail(variation_id: str):
        try:
            return jsonify(
                historical_variant_detail(
                    Path(app.config["HISTORICAL_VARIANT_DB_PATH"]), variation_id
                )
            )
        except HistoricalVariantDatabaseError as exc:
            return jsonify({"error": str(exc)}), 404
        except (OSError, sqlite3.Error) as exc:
            return jsonify({"error": f"Historical index unavailable: {exc}"}), 503

    @app.post("/api/historical-dataset/plan")
    def api_historical_dataset_plan():
        try:
            plan = historical_plan()
            digest = hashlib.sha256(
                json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            with state_lock:
                issued_historical_plans[digest] = plan
            return jsonify({"plan": plan, "plan_digest": digest})
        except (OSError, ValueError) as exc:
            return jsonify({"error": f"Could not plan historical dataset: {exc}"}), 503

    @app.post("/api/historical-dataset/run")
    def api_run_historical_dataset():
        try:
            body = _json_body()
            if body.get("approved") is not True:
                return jsonify(
                    {"error": "Review and approve the exact release-pair plan first."}
                ), 428
            plan = body.get("plan")
            digest = body.get("plan_digest")
            if not isinstance(plan, dict) or not isinstance(digest, str):
                raise ValueError("A server-issued plan and digest are required.")
            calculated = hashlib.sha256(
                json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            with state_lock:
                issued = issued_historical_plans.pop(digest, None)
            if calculated != digest or issued != plan:
                raise ValueError("The approved plan was changed or was not issued.")
            validate_download_preflight(plan)
            if int(plan["estimated_transfer_bytes"]) == 0:
                return jsonify(
                    {"state": "ready", "message": "Both release files already exist."}
                )
            with state_lock:
                if any(
                    item["state"] == "running"
                    for item in historical_operations.values()
                ):
                    return jsonify(
                        {"error": "A historical dataset download is already running."}
                    ), 409
                operation_id = uuid.uuid4().hex
                historical_operations[operation_id] = {
                    "operation_id": operation_id,
                    "state": "running",
                    "plan": plan,
                    "progress": None,
                    "result": None,
                    "error": None,
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "finished_at_utc": None,
                }
            thread = threading.Thread(
                target=run_historical_download,
                args=(operation_id, plan),
                daemon=True,
                name=f"historical-dataset-{operation_id[:8]}",
            )
            thread.start()
            return jsonify({"operation_id": operation_id, "state": "running"}), 202
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/historical-dataset/operations/<operation_id>")
    def api_historical_dataset_operation(operation_id: str):
        with state_lock:
            operation = historical_operations.get(operation_id)
            if operation is None:
                return (
                    jsonify({"error": "Historical dataset operation not found."}),
                    404,
                )
            return jsonify(operation)

    @app.get("/api/pilot-results")
    def api_pilot_results():
        try:
            output_root = Path(app.config["PILOT_RESULTS_ROOT"])
            aggregation = aggregate_pilot_results(history_root(), output_root)
            output_files = {
                filename: (output_root / filename).is_file()
                and not (output_root / filename).is_symlink()
                for filename in OUTPUT_FILENAMES
            }
            return jsonify(
                {
                    **aggregation,
                    "output_files": output_files,
                    "all_outputs_exist": all(output_files.values()),
                }
            )
        except (OSError, PilotResultsError, VCVHistoryStoreError) as exc:
            return jsonify({"error": f"Pilot results unavailable: {exc}"}), 503

    @app.get("/api/pilot-results/download/<path:filename>")
    def api_pilot_results_download(filename: str):
        try:
            content, mimetype, safe_name = download_content(
                Path(app.config["PILOT_RESULTS_ROOT"]), filename
            )
            return send_file(
                BytesIO(content),
                mimetype=mimetype,
                as_attachment=True,
                download_name=safe_name,
            )
        except PilotResultsError as exc:
            return jsonify({"error": str(exc)}), 404

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
                "pilot_results_file_created": False,
                "pilot_output_bandwidth_bytes": 0,
            }
        with state_lock:
            transfer_snapshot = dict(transfer_state)
        try:
            model_dashboard = load_model_dashboard(PROJECT_ROOT)
            model_index = {item["model_id"]: item for item in model_dashboard["models"]}
            timeline = load_project_timeline(Path(app.config["PROJECT_TIMELINE_PATH"]))
            next_milestone = next(
                (
                    task
                    for task in timeline["tasks"]
                    if task["status"] not in {"completed", "cancelled"}
                ),
                None,
            )
            model_validation = {
                "project_stage": "V8 Results and Manual Review",
                "latest_model_version": model_dashboard["latest_model_version"],
                "best_validated_model": model_dashboard["best_validated_model"],
                "v4": model_index.get("V4"),
                "v5": model_index.get("V5"),
                "v6": model_index.get("V6"),
                "v7": model_index.get("V7"),
                "v8": model_index.get("V8"),
                "leakage_audit_status": {
                    item["model_id"]: item["leakage_status"]
                    for item in model_dashboard["models"]
                },
                "held_out_test_size": {
                    "V4": 100,
                    "V5": 100,
                    "V6": 1000,
                    "V7": 1000,
                    "V8": 1000,
                },
                "next_required_validation_step": (
                    "Review V8 errors and calibration, then replicate on a genuinely "
                    "later untouched snapshot without changing the reported V8 result."
                ),
                "upcoming_deadline": next_milestone,
                "github_status": (
                    "Remote configured; live sync is not checked by dashboard."
                ),
                "warnings": [
                    "V4/V5 used n=100 tests; V6 used a different n=1,000 test.",
                    "V7 is temporal at the record level; 69.9% shared a "
                    "development gene.",
                    "V8 is development-component-disjoint but retrospective; its "
                    "hidden membership is reconstructible.",
                    "V8 exceeded same-record V7 balanced accuracy by 0.4524 points, "
                    "but the component-bootstrap interval includes zero.",
                    "Scores across different cohorts are not paired improvements.",
                    "Preliminary research result; not medical advice or clinical use.",
                ],
            }
        except (OSError, RegistryError, json.JSONDecodeError):
            model_validation = {
                "project_stage": "V8 Results and Manual Review",
                "available": False,
                "warnings": ["Model registry is unavailable."],
            }
        return jsonify(
            {
                "project_name": "Variant Time Machine",
                "project_explanation": PROJECT_EXPLANATION,
                "current_milestone": "V8 Results and Manual Review",
                "folders": FOLDER_GUIDE,
                "next_tasks": dynamic_next_tasks(progress),
                "research_progress": progress,
                "clue_score_baseline": clue_score_progress(),
                "system": _system_status(Path(app.config["PILOT_RESULTS_ROOT"])),
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
                "model_validation": model_validation,
            }
        )

    @app.post("/api/pilot-batch/plan")
    def api_pilot_batch_plan():
        try:
            plan = pilot_batch_plan(_json_body())
            digest = pilot_batch_plan_digest(plan)
            issued_at = datetime.now(UTC).isoformat()
            with state_lock:
                issued_batch_plans[digest] = issued_at
            return jsonify(
                {"plan": plan, "plan_digest": digest, "issued_at_utc": issued_at}
            )
        except TransferLimitError as exc:
            return jsonify({"error": str(exc)}), 413
        except (InvalidVCVAccession, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, VCVHistoryStoreError) as exc:
            return jsonify({"error": f"VCV histories unavailable: {exc}"}), 503

    @app.post("/api/pilot-batch/run")
    def api_run_pilot_batch():
        try:
            body = _json_body()
            if body.get("approved") is not True:
                return jsonify(
                    {"error": "Review and approve the exact pilot batch plan first."}
                ), 428
            supplied_plan = body.get("plan")
            if not isinstance(supplied_plan, dict):
                raise ValueError("Plan the pilot batch before approving it.")
            supplied_candidates = supplied_plan.get("candidates")
            if not isinstance(supplied_candidates, list) or not all(
                isinstance(candidate, dict)
                and isinstance(candidate.get("accession"), str)
                for candidate in supplied_candidates
            ):
                raise ValueError("The supplied plan has invalid candidates.")
            plan = pilot_batch_plan(
                {
                    "candidates": [
                        candidate["accession"] for candidate in supplied_candidates
                    ],
                    "reuse_existing": supplied_plan.get("reuse_existing", True),
                    "candidate_selection_rule": supplied_plan.get(
                        "candidate_selection_rule", ""
                    ),
                    "candidate_selection_bytes": supplied_plan.get(
                        "candidate_selection_bytes", 0
                    ),
                    "candidate_selection_requests": supplied_plan.get(
                        "candidate_selection_requests", []
                    ),
                }
            )
            if supplied_plan != plan:
                raise ValueError(
                    "The supplied pilot batch plan does not match the current plan."
                )
            plan_digest = pilot_batch_plan_digest(plan)
            with state_lock:
                plan_issued_at = issued_batch_plans.pop(plan_digest, None)
            if plan_issued_at is None:
                raise ValueError(
                    "This exact plan was not issued for review. Plan the batch first."
                )
            plan = {
                **plan,
                "plan_digest": plan_digest,
                "plan_issued_at_utc": plan_issued_at,
                "approved_at_utc": datetime.now(UTC).isoformat(),
            }

            with state_lock:
                if any(item["state"] == "running" for item in operations.values()):
                    return jsonify(
                        {"error": "Another VCV operation is already running."}
                    ), 409
                operation_id = uuid.uuid4().hex
                cancel_event = threading.Event()
                operations[operation_id] = {
                    "operation_id": operation_id,
                    "state": "running",
                    "operation_type": "pilot_batch",
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
                target=run_pilot_batch_operation,
                args=(operation_id, plan, cancel_event),
                daemon=True,
                name=f"pilot-batch-{operation_id[:8]}",
            )
            thread.start()
            return jsonify({"operation_id": operation_id, "state": "running"}), 202
        except TransferLimitError as exc:
            return jsonify({"error": str(exc)}), 413
        except (InvalidVCVAccession, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except (OSError, VCVHistoryStoreError) as exc:
            return jsonify({"error": f"VCV histories unavailable: {exc}"}), 503

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
            results_root = Path(app.config["PILOT_RESULTS_ROOT"])
            if (results_root / "batch_manifest.json").is_file():
                export_pilot_results(history_root(), results_root)
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
            0.8, lambda: webbrowser.open("http://127.0.0.1:5000/overview.html")
        ).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    run_dashboard()
