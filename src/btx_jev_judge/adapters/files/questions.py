"""Questions read from a JSON file."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...domain import InputError, Question, parse_questions
from ._text import read_text

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["load_questions"]


def load_questions(path: Path) -> list[Question]:
    """Questions from a JSON file holding a list; see :func:`parse_questions`.

    Args:
        path: The JSON file.

    Returns:
        The typed questions, in file order.

    Raises:
        InputError: The file is unreadable, not JSON, or not a valid question list.
    """
    try:
        raw = json.loads(read_text(path))
    except ValueError as exc:
        raise InputError(f"{path}: not JSON ({exc})") from exc
    try:
        return parse_questions(raw)
    except InputError as exc:
        raise InputError(f"{path}: {exc}") from exc
