"""Result rows written to and read from a JSONL file."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pydantic import ValidationError

from ...domain import InputError, Row, describe_validation_error
from ._text import read_text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ["PROGRESS_EVERY", "read_rows", "write_rows"]

# One progress line per this many rows keeps a long run visibly alive without flooding stderr.
PROGRESS_EVERY = 100


def write_rows(path: Path, rows: Iterable[Row]) -> list[Row]:
    """Write each row as it arrives, so an interrupted run keeps what it already paid for.

    Args:
        path: The JSONL file to create or overwrite.
        rows: The rows, consumed lazily; each is flushed before the next is drawn.

    Returns:
        The rows written, in order.

    Raises:
        InputError: The file cannot be written.
    """
    written: list[Row] = []
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
                handle.flush()
                written.append(row)
                if len(written) % PROGRESS_EVERY == 0:
                    sys.stderr.write(f"jev-judge: {len(written)} rows written\n")
    except OSError as exc:
        raise InputError(f"cannot write {path}: {exc.strerror or exc}") from exc
    return written


def read_rows(path: Path) -> list[Row]:
    """Rows from a JSONL file written by :func:`write_rows`.

    Args:
        path: The JSONL file. Blank lines are skipped.

    Returns:
        The rows in file order.

    Raises:
        InputError: The file is unreadable or a line is not a valid row.
    """
    rows: list[Row] = []
    for number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(Row.model_validate_json(line))
        except ValidationError as exc:
            raise InputError(f"{path} line {number}: {describe_validation_error(exc)}") from exc
    return rows
