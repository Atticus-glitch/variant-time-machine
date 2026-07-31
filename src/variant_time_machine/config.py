"""Central paths and project-wide configuration."""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
TEMP_DATA_DIR = DATA_DIR / "tmp"
HISTORICAL_RAW_DATA_DIR = RAW_DATA_DIR / "clinvar"
HISTORICAL_VARIANT_DB_PATH = PROCESSED_DATA_DIR / "clinvar_history.sqlite3"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CLUE_SCORE_CONFIG_PATH = PROJECT_ROOT / "config" / "clue_score_v1.yaml"
CLUE_SCORE_RESULTS_DIR = OUTPUTS_DIR / "clue_score_v1"
CLUE_SCORE_RESULTS_DB_PATH = PROCESSED_DATA_DIR / "clue_score_v1.sqlite3"
CLUE_SCORE_DEVELOPMENT_DB_PATH = (
    PROCESSED_DATA_DIR / "clue_score_v1_development.sqlite3"
)
CLUE_SCORE_REVIEW_PATH = DATA_DIR / "manual_review" / "clue_score_v1_reviews.json"
RESOLVED_DIRECTION_CONFIG_PATH = PROJECT_ROOT / "config" / "resolved_direction_v2.yaml"
RESOLVED_DIRECTION_RESULTS_DIR = OUTPUTS_DIR / "resolved_direction_v2"
RESOLVED_DIRECTION_RESULTS_DB_PATH = (
    PROCESSED_DATA_DIR / "resolved_direction_v2.sqlite3"
)
RESOLVED_DIRECTION_REVIEW_PATH = (
    DATA_DIR / "manual_review" / "resolved_direction_v2_reviews.json"
)
STATISTICAL_MODEL_V3_CONFIG_PATH = PROJECT_ROOT / "config" / "statistical_model_v3.yaml"
STATISTICAL_MODEL_V3_RESULTS_DIR = OUTPUTS_DIR / "statistical_model_v3"
AI_HOLDOUT_V4_CONFIG_PATH = PROJECT_ROOT / "config" / "ai_holdout_v4.yaml"
AI_HOLDOUT_V4_RESULTS_DIR = OUTPUTS_DIR / "ai_holdout_v4"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"
MODELS_DIR = OUTPUTS_DIR / "models"

DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(levelname)s: %(message)s"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120
LARGE_DOWNLOAD_THRESHOLD_BYTES = 500_000_000
HISTORICAL_DOWNLOAD_LIMIT_BYTES = 5_000_000_000
HISTORICAL_FREE_SPACE_FRACTION = 0.10
HISTORICAL_MINIMUM_FREE_BYTES = 20_000_000_000
PILOT_CURRENT_API_ESTIMATE_BYTES = 1_000_000
PILOT_HISTORICAL_API_LIMIT_BYTES = 10_000_000


@dataclass(frozen=True)
class ClinVarRelease:
    """Configuration for one fixed ClinVar archive release."""

    label: str
    release_date: date
    source_url: str
    expected_size_bytes: int | None = None
    expected_sha256: str | None = None

    @property
    def filename(self) -> str:
        """Return the filename from the configured source URL."""
        return self.source_url.rsplit("/", maxsplit=1)[-1]


@dataclass(frozen=True)
class ClinVarXMLRelease:
    """Metadata for one official monthly VCV XML archive."""

    label: str
    release_date: date
    source_url: str
    compressed_size_bytes: int
    md5: str
    schema_version: str

    @property
    def filename(self) -> str:
        return self.source_url.rsplit("/", maxsplit=1)[-1]


OLDER_CLINVAR_RELEASE = date(2022, 1, 6)
NEWER_CLINVAR_RELEASE = date(2024, 1, 4)
OLDER_VARIANT_SUMMARY_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2022/"
    "variant_summary_2022-01.txt.gz"
)
NEWER_VARIANT_SUMMARY_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/2024/"
    "variant_summary_2024-01.txt.gz"
)

CLINVAR_RELEASES: dict[str, ClinVarRelease] = {
    "older": ClinVarRelease(
        label="older",
        release_date=OLDER_CLINVAR_RELEASE,
        source_url=OLDER_VARIANT_SUMMARY_URL,
        expected_size_bytes=95_791_203,
    ),
    "newer": ClinVarRelease(
        label="newer",
        release_date=NEWER_CLINVAR_RELEASE,
        source_url=NEWER_VARIANT_SUMMARY_URL,
        expected_size_bytes=223_649_945,
    ),
}

PILOT_XML_RELEASES: dict[str, ClinVarXMLRelease] = {
    "older": ClinVarXMLRelease(
        label="older",
        release_date=date(2024, 2, 1),
        source_url=(
            "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/xml/archive/2024/"
            "ClinVarVCVRelease_2024-02.xml.gz"
        ),
        compressed_size_bytes=3_334_050_859,
        md5="669267f97e208014ca04d629b6681cf6",
        schema_version="ClinVar VCV 2.0",
    ),
    "newer": ClinVarXMLRelease(
        label="newer",
        release_date=date(2025, 2, 6),
        source_url=(
            "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/xml/"
            "ClinVarVCVRelease_2025-02.xml.gz"
        ),
        compressed_size_bytes=4_556_267_423,
        md5="9ab805f0abb0b72099bc90eb9474fa22",
        schema_version="ClinVar VCV 2.2",
    ),
}

PILOT_MAX_RECORDS = 10
PILOT_MAX_TEMP_BYTES = 50 * 1024 * 1024
PILOT_PROGRESS_BYTES = 100 * 1024 * 1024
PILOT_EXTRACTED_DIR = DATA_DIR / "manual_review" / "extracted"
PILOT_VARIANTS_PATH = DATA_DIR / "manual_review" / "pilot_variants.csv"
PILOT_RECORD_PATH = DATA_DIR / "manual_review" / "pilot_variant_001.json"
PILOT_REVIEW_PATH = DATA_DIR / "manual_review" / "pilot_review.json"
PILOT_WORKSPACE_PATH = DATA_DIR / "manual_review" / "pilot_workspace.json"
VCV_HISTORY_DIR = DATA_DIR / "manual_review" / "vcv_history"
PILOT_RESULTS_DIR = DATA_DIR / "pilot_results"

REQUIRED_DIRECTORIES: tuple[Path, ...] = (
    PROJECT_ROOT / "research",
    PROJECT_ROOT / "config",
    DATA_DIR,
    RAW_DATA_DIR,
    INTERIM_DATA_DIR,
    PROCESSED_DATA_DIR,
    TEMP_DATA_DIR,
    HISTORICAL_RAW_DATA_DIR,
    DATA_DIR / "manual_review",
    PILOT_RESULTS_DIR,
    PILOT_EXTRACTED_DIR,
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "src" / "variant_time_machine",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "notebooks",
    PROJECT_ROOT / "tests",
    OUTPUTS_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    MODELS_DIR,
    PROJECT_ROOT / "website",
    PROJECT_ROOT / "website" / "dashboard",
    PROJECT_ROOT / "website" / "dashboard" / "templates",
    PROJECT_ROOT / "website" / "dashboard" / "static",
    PROJECT_ROOT / "docs",
)

IMPORTANT_FILES: tuple[Path, ...] = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "LICENSE",
    PROJECT_ROOT / ".gitignore",
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "research" / "one-page-research-plan.md",
    PROJECT_ROOT / "research" / "clinvar-data-plan.md",
    PROJECT_ROOT / "research" / "historical-data-plan.md",
    PROJECT_ROOT / "research" / "download-strategy.md",
    PROJECT_ROOT / "research" / "clue-score-v1-development-validation.md",
    PROJECT_ROOT / "research" / "clue-score-v1-results.md",
    PROJECT_ROOT / "research" / "resolved-direction-v2-results.md",
    PROJECT_ROOT / "research" / "statistical-model-v3-results.md",
    PROJECT_ROOT / "research" / "ai-holdout-v4-training.md",
    CLUE_SCORE_CONFIG_PATH,
    RESOLVED_DIRECTION_CONFIG_PATH,
    STATISTICAL_MODEL_V3_CONFIG_PATH,
    AI_HOLDOUT_V4_CONFIG_PATH,
    PROJECT_ROOT / "research" / "data-size-options.md",
    PROJECT_ROOT / "research" / "how-to-select-first-variant.md",
    PROJECT_ROOT / "research" / "research-notebook.md",
    PROJECT_ROOT / "research" / "pilot-results.md",
    PROJECT_ROOT / "research" / "project-decisions.md",
    PROJECT_ROOT / "research" / "sources.md",
    PROJECT_ROOT / "research" / "competition-notes.md",
    PROJECT_ROOT / "data" / "README.md",
    DATA_DIR / "example_variants.csv",
    DATA_DIR / "manual_review" / "README.md",
    DATA_DIR / "manual_review" / "test_variants.csv",
    PILOT_VARIANTS_PATH,
    PILOT_RECORD_PATH,
    PILOT_WORKSPACE_PATH,
    PILOT_RESULTS_DIR / "batch_manifest.json",
    PILOT_RESULTS_DIR / "pilot_results.csv",
    PILOT_RESULTS_DIR / "pilot_summary.json",
    PILOT_RESULTS_DIR / "pilot_report.md",
    PILOT_RESULTS_DIR / "transfer_manifest.json",
    PILOT_RESULTS_DIR / "manual_review.csv",
    VCV_HISTORY_DIR / ".gitkeep",
    PILOT_EXTRACTED_DIR / ".gitkeep",
    INTERIM_DATA_DIR / "example_clinvar_timeline.csv",
    RAW_DATA_DIR / ".gitkeep",
    INTERIM_DATA_DIR / ".gitkeep",
    PROCESSED_DATA_DIR / ".gitkeep",
    PROJECT_ROOT / "src" / "variant_time_machine" / "__init__.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "config.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "clinvar_api.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "download.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "historical_dataset.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "historical_variants.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "clue_score.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "clue_score_experiment.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "resolved_direction.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "statistical_model_v3.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "ai_holdout_v4.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "parse.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "match.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot_record.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot_workspace.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot_results.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "remote_archive.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "vcv_history.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "vcv_history_store.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "features.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "train.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "evaluate.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "utils.py",
    PROJECT_ROOT / "scripts" / "download_data.py",
    PROJECT_ROOT / "scripts" / "build_timeline_dataset.py",
    PROJECT_ROOT / "scripts" / "build_historical_spreadsheet.py",
    PROJECT_ROOT / "scripts" / "train_baseline.py",
    PROJECT_ROOT / "scripts" / "run_statistical_model_v3.py",
    PROJECT_ROOT / "scripts" / "train_ai_holdout_v4.py",
    PROJECT_ROOT / "scripts" / "validate_setup.py",
    PROJECT_ROOT / "scripts" / "start_dashboard.py",
    PROJECT_ROOT / "scripts" / "test_clinvar_connection.py",
    PROJECT_ROOT / "scripts" / "review_variant.py",
    PROJECT_ROOT / "scripts" / "extract_pilot_history.py",
    PROJECT_ROOT / "scripts" / "pilot_mode.py",
    PROJECT_ROOT / "scripts" / "select_pilot_variant.py",
    PROJECT_ROOT / "scripts" / "run_pilot_workflow.py",
    PROJECT_ROOT / "notebooks" / "README.md",
    PROJECT_ROOT / "tests" / "__init__.py",
    PROJECT_ROOT / "tests" / "test_setup.py",
    PROJECT_ROOT / "tests" / "test_historical_dataset.py",
    PROJECT_ROOT / "tests" / "test_historical_variants.py",
    PROJECT_ROOT / "tests" / "test_clue_score.py",
    PROJECT_ROOT / "tests" / "test_clue_score_experiment.py",
    PROJECT_ROOT / "tests" / "test_resolved_direction.py",
    PROJECT_ROOT / "tests" / "test_statistical_model_v3.py",
    PROJECT_ROOT / "tests" / "test_ai_holdout_v4.py",
    FIGURES_DIR / ".gitkeep",
    TABLES_DIR / ".gitkeep",
    MODELS_DIR / ".gitkeep",
    PROJECT_ROOT / "website" / "README.md",
    PROJECT_ROOT / "website" / "dashboard" / "README.md",
    PROJECT_ROOT / "website" / "dashboard" / "app.py",
    PROJECT_ROOT / "website" / "dashboard" / "templates" / "index.html",
    PROJECT_ROOT / "website" / "dashboard" / "variant_lookup.html",
    PROJECT_ROOT / "website" / "dashboard" / "pilot_workspace.html",
    PROJECT_ROOT / "website" / "dashboard" / "version_history.html",
    PROJECT_ROOT / "website" / "dashboard" / "pilot_results.html",
    PROJECT_ROOT / "website" / "dashboard" / "historical_dataset.html",
    PROJECT_ROOT / "website" / "dashboard" / "historical_variants.html",
    PROJECT_ROOT / "website" / "dashboard" / "overview.html",
    PROJECT_ROOT / "website" / "dashboard" / "prediction_results.html",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "styles.css",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "app.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "lookup.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "workspace.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "version_history.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "pilot_results.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "historical_dataset.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "historical_variants.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "overview.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "prediction_results.js",
    PROJECT_ROOT / "docs" / "data-dictionary.md",
    PROJECT_ROOT / "docs" / "methods.md",
    PROJECT_ROOT / "docs" / "limitations.md",
    PROJECT_ROOT / "docs" / "clinvar-api.md",
)
