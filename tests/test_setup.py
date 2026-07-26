"""Tests for package configuration and setup utilities."""

from pathlib import Path

import variant_time_machine
from scripts.validate_setup import (
    validate_dataframe_round_trip,
    validate_dependencies,
    validate_paths,
    validate_python_version,
)
from variant_time_machine.config import (
    DATA_DIR,
    IMPORTANT_FILES,
    PROJECT_ROOT,
    REQUIRED_DIRECTORIES,
)
from variant_time_machine.utils import missing_paths, path_is_within


def test_package_imports() -> None:
    """The local package should expose its initial version."""
    assert variant_time_machine.__version__ == "0.1.0"


def test_expected_directories_exist() -> None:
    """Every configured project directory should resolve and exist."""
    assert not missing_paths(REQUIRED_DIRECTORIES)
    assert all(path.is_dir() for path in REQUIRED_DIRECTORIES)


def test_important_files_exist() -> None:
    """Core project files should be available from configuration."""
    assert not missing_paths(IMPORTANT_FILES)


def test_configuration_stays_inside_repository() -> None:
    """Configured storage paths must not escape the repository."""
    configured_paths = (*REQUIRED_DIRECTORIES, *IMPORTANT_FILES, DATA_DIR)
    assert PROJECT_ROOT.name == "variant-time-machine"
    assert all(path_is_within(path, PROJECT_ROOT) for path in configured_paths)


def test_setup_path_utilities(tmp_path: Path) -> None:
    """Path checks should detect missing files and reject outside locations."""
    present = tmp_path / "present.txt"
    present.write_text("test", encoding="utf-8")
    absent = tmp_path / "absent.txt"

    assert missing_paths([present, absent]) == [absent.resolve()]
    assert path_is_within(present, tmp_path)
    assert not path_is_within(PROJECT_ROOT.parent, PROJECT_ROOT)


def test_setup_validator_accepts_valid_setup() -> None:
    """Validator functions should accept the supported local setup."""
    assert validate_python_version((3, 11)) == []
    assert validate_paths() == []
    assert validate_dependencies({"pathlib": "pathlib"}) == []
    assert validate_dataframe_round_trip() == []


def test_setup_validator_reports_failures(tmp_path: Path) -> None:
    """Validator functions should explain version, path, and import failures."""
    file_instead_of_directory = tmp_path / "not-a-directory"
    file_instead_of_directory.write_text("test", encoding="utf-8")
    directory_instead_of_file = tmp_path / "not-a-file"
    directory_instead_of_file.mkdir()

    assert "Python 3.11 or newer" in validate_python_version((3, 10))[0]
    path_errors = validate_paths(
        [file_instead_of_directory], [directory_instead_of_file]
    )
    assert path_errors == [
        f"Missing required directory: {file_instead_of_directory.resolve()}",
        f"Missing important file: {directory_instead_of_file.resolve()}",
    ]
    dependency_errors = validate_dependencies(
        {"missing test dependency": "module_that_does_not_exist_for_setup_test"}
    )
    assert "Cannot import missing test dependency" in dependency_errors[0]
