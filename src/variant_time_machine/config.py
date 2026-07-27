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
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"
MODELS_DIR = OUTPUTS_DIR / "models"

DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(levelname)s: %(message)s"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120
LARGE_DOWNLOAD_THRESHOLD_BYTES = 500_000_000
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

REQUIRED_DIRECTORIES: tuple[Path, ...] = (
    PROJECT_ROOT / "research",
    DATA_DIR,
    RAW_DATA_DIR,
    INTERIM_DATA_DIR,
    PROCESSED_DATA_DIR,
    DATA_DIR / "manual_review",
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
    PROJECT_ROOT / "research" / "data-size-options.md",
    PROJECT_ROOT / "research" / "how-to-select-first-variant.md",
    PROJECT_ROOT / "research" / "research-notebook.md",
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
    PROJECT_ROOT / "src" / "variant_time_machine" / "parse.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "match.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot_record.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "pilot_workspace.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "remote_archive.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "vcv_history.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "vcv_history_store.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "features.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "train.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "evaluate.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "utils.py",
    PROJECT_ROOT / "scripts" / "download_data.py",
    PROJECT_ROOT / "scripts" / "build_timeline_dataset.py",
    PROJECT_ROOT / "scripts" / "train_baseline.py",
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
    PROJECT_ROOT / "website" / "dashboard" / "static" / "styles.css",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "app.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "lookup.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "workspace.js",
    PROJECT_ROOT / "website" / "dashboard" / "static" / "version_history.js",
    PROJECT_ROOT / "docs" / "data-dictionary.md",
    PROJECT_ROOT / "docs" / "methods.md",
    PROJECT_ROOT / "docs" / "limitations.md",
    PROJECT_ROOT / "docs" / "clinvar-api.md",
)
