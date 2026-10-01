"""Items read from a JSONL file."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ...domain import InputError, Item, describe_validation_error
from ._text import read_text

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["load_items"]


class _ItemIn(BaseModel):
    # The domain's strict base is private, so this repeats its config: frozen, no unknown fields.
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str | int
    state: Annotated[dict[str, JsonValue], Field(min_length=1)]


def load_items(path: Path) -> list[Item]:
    """Items from a JSONL file, one ``{"id": ..., "state": {...}}`` per line.

    Args:
        path: The JSONL file. Blank lines are skipped.

    Returns:
        The items in file order, ids normalised to strings.

    Raises:
        InputError: A line is not JSON or not the item shape, an id repeats, or there are none.
    """
    items: list[Item] = []
    seen: set[str] = set()
    for number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        item = _parse_item(line, where=f"{path} line {number}")
        if item.id in seen:
            raise InputError(f"{path} line {number}: duplicate id {item.id!r}")
        seen.add(item.id)
        items.append(item)
    if not items:
        raise InputError(f"{path}: no items")
    return items


def _parse_item(line: str, *, where: str) -> Item:
    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise InputError(f"{where}: not JSON ({exc})") from exc
    try:
        parsed = _ItemIn.model_validate(raw)
    except ValidationError as exc:
        raise InputError(f"{where}: {describe_validation_error(exc)}") from exc
    return Item(id=str(parsed.id), state=parsed.state)
