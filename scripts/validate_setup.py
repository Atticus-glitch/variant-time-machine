#!/usr/bin/env python3
"""Validate the local project setup without accessing scientific datasets."""

import importlib
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.config import (  # noqa: E402
    IMPORTANT_FILES,
    REQUIRED_DIRECTORIES,
)

DEPENDENCIES: dict[str, str] = {
    "pandas": "pandas",
    "numpy": "numpy",
    "scikit-learn": "sklearn",
    "matplotlib": "matplotlib",
    "requests": "requests",
    "tqdm": "tqdm",
    "pyarrow": "pyarrow",
    "pydantic": "pydantic",
    "pytest": "pytest",
    "ruff": "ruff",
}


def validate_python_version(
    version: tuple[int, int] = sys.version_info[:2],
) -> list[str]:
    """Return an error when Python is older than the supported minimum."""
    if version < (3, 11):
        return [f"Python 3.11 or newer is required; found {version[0]}.{version[1]}."]
    return []


def validate_paths(
    required_directories: Sequence[Path] = REQUIRED_DIRECTORIES,
    important_files: Sequence[Path] = IMPORTANT_FILES,
) -> list[str]:
    """Return errors for missing or incorrectly typed project paths."""
    errors: list[str] = []
    for path in required_directories:
        if not path.is_dir():
            errors.append(f"Missing required directory: {path.resolve()}")
    for path in important_files:
        if not path.is_file():
            errors.append(f"Missing important file: {path.resolve()}")
    return errors


def validate_dependencies(
    dependencies: Mapping[str, str] = DEPENDENCIES,
) -> list[str]:
    """Return errors for dependencies that cannot be imported."""
    errors: list[str] = []
    for display_name, module_name in dependencies.items():
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"Cannot import {display_name} ({type(exc).__name__}): {exc}")
    return errors


def validate_dataframe_round_trip() -> list[str]:
    """Verify a tiny Parquet round trip in an isolated temporary directory."""
    try:
        import pandas as pd

        expected = pd.DataFrame(
            {"variant_id": [101, 102], "older_classification": ["VUS", "VUS"]}
        )
        with tempfile.TemporaryDirectory(prefix="variant-time-machine-") as temp_dir:
            test_path = Path(temp_dir) / "setup-test.parquet"
            expected.to_parquet(test_path, index=False)
            observed = pd.read_parquet(test_path)
        if not expected.equals(observed):
            return ["Temporary DataFrame changed during the Parquet round trip."]
    except Exception as exc:  # Validation should report failures rather than crash.
        return [f"Temporary DataFrame round trip failed: {exc}"]
    return []


def main() -> int:
    """Run all setup checks and return a process exit code."""
    print("Variant Time Machine setup validation")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Project root: {PROJECT_ROOT}")

    errors = validate_python_version()
    errors.extend(validate_paths())
    errors.extend(validate_dependencies())
    errors.extend(validate_dataframe_round_trip())

    if errors:
        print("\nFAILURE")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nSUCCESS: folders, files, imports, and temporary data I/O are working.")
    print("No ClinVar data were accessed or downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
