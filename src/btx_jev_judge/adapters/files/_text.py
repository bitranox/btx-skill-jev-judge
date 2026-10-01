"""Shared text reading for the file adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.errors import InputError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["read_text"]


def read_text(path: Path) -> str:
    """Read a UTF-8 file, tolerating a byte-order mark.

    Args:
        path: The file to read.

    Returns:
        The decoded text without a leading BOM.

    Raises:
        InputError: The file cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc
