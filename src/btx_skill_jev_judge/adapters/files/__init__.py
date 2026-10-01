"""File adapters - items, questions and result rows on disk.

Contents:
    * :mod:`.items` - :func:`load_items`, a JSONL file of items
    * :mod:`.questions` - :func:`load_questions`, a JSON file of questions
    * :mod:`.rows` - :func:`write_rows` (streaming) and :func:`read_rows`
"""

from __future__ import annotations

from .items import load_items
from .questions import load_questions
from .rows import read_rows, write_rows

__all__ = ["load_items", "load_questions", "read_rows", "write_rows"]
