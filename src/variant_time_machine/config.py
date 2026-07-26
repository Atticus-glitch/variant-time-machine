"""Central paths and project-wide configuration."""

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

REQUIRED_DIRECTORIES: tuple[Path, ...] = (
    PROJECT_ROOT / "research",
    RAW_DATA_DIR,
    INTERIM_DATA_DIR,
    PROCESSED_DATA_DIR,
    PROJECT_ROOT / "src" / "variant_time_machine",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "notebooks",
    PROJECT_ROOT / "tests",
    FIGURES_DIR,
    TABLES_DIR,
    MODELS_DIR,
    PROJECT_ROOT / "website",
    PROJECT_ROOT / "docs",
)

IMPORTANT_FILES: tuple[Path, ...] = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "LICENSE",
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "research" / "one-page-research-plan.md",
    PROJECT_ROOT / "docs" / "data-dictionary.md",
)
