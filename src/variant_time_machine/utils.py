"""Shared validation and logging helpers."""

import logging
from collections.abc import Iterable
from pathlib import Path


def configure_logging(level: int = logging.INFO) -> None:
    """Configure concise console logging for project scripts."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,
    )


def missing_paths(paths: Iterable[Path]) -> list[Path]:
    """Return resolved paths that do not exist."""
    return [path.resolve() for path in paths if not path.exists()]


def path_is_within(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is inside or equal to a parent path."""
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents
