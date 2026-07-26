"""Central paths and project-wide configuration."""

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

REQUIRED_DIRECTORIES: tuple[Path, ...] = (
    PROJECT_ROOT / "research",
    DATA_DIR,
    RAW_DATA_DIR,
    INTERIM_DATA_DIR,
    PROCESSED_DATA_DIR,
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
    PROJECT_ROOT / "docs",
)

IMPORTANT_FILES: tuple[Path, ...] = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "LICENSE",
    PROJECT_ROOT / ".gitignore",
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "research" / "one-page-research-plan.md",
    PROJECT_ROOT / "research" / "research-notebook.md",
    PROJECT_ROOT / "research" / "project-decisions.md",
    PROJECT_ROOT / "research" / "sources.md",
    PROJECT_ROOT / "research" / "competition-notes.md",
    PROJECT_ROOT / "data" / "README.md",
    RAW_DATA_DIR / ".gitkeep",
    INTERIM_DATA_DIR / ".gitkeep",
    PROCESSED_DATA_DIR / ".gitkeep",
    PROJECT_ROOT / "src" / "variant_time_machine" / "__init__.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "config.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "download.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "parse.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "match.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "features.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "train.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "evaluate.py",
    PROJECT_ROOT / "src" / "variant_time_machine" / "utils.py",
    PROJECT_ROOT / "scripts" / "download_data.py",
    PROJECT_ROOT / "scripts" / "build_timeline_dataset.py",
    PROJECT_ROOT / "scripts" / "train_baseline.py",
    PROJECT_ROOT / "scripts" / "validate_setup.py",
    PROJECT_ROOT / "notebooks" / "README.md",
    PROJECT_ROOT / "tests" / "__init__.py",
    PROJECT_ROOT / "tests" / "test_setup.py",
    FIGURES_DIR / ".gitkeep",
    TABLES_DIR / ".gitkeep",
    MODELS_DIR / ".gitkeep",
    PROJECT_ROOT / "website" / "README.md",
    PROJECT_ROOT / "docs" / "data-dictionary.md",
    PROJECT_ROOT / "docs" / "methods.md",
    PROJECT_ROOT / "docs" / "limitations.md",
)
