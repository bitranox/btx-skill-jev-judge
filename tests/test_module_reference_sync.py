"""The RunConfig and SummaryConfig tables in the module reference match the models.

A reader of ``docs/systemdesign/module_reference.md`` learns the configuration fields, their types
and their defaults from it; a table that drifted from ``judge_settings.py`` (a default changed, a
field renamed) tells them something the code no longer does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, get_args

import pytest

from btx_jev_judge.adapters.config.judge_settings import RunConfig, SummaryConfig

if TYPE_CHECKING:
    from pydantic import BaseModel

_MODULE_REFERENCE = Path(__file__).parent.parent / "docs" / "systemdesign" / "module_reference.md"
_ROW = re.compile(r"\|\s*`(\w+)`\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")


def _section(model: type[BaseModel]) -> list[str]:
    """The lines under ``### <Model>`` up to the next heading."""
    lines = _MODULE_REFERENCE.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"### {model.__name__}") + 1
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            break
        body.append(line)
    return body


def _documented(model: type[BaseModel]) -> dict[str, tuple[str, str]]:
    """Each ``| `field` | `type` | `default` |`` row of the model's table."""
    rows: dict[str, tuple[str, str]] = {}
    for line in _section(model):
        match = _ROW.match(line)
        if match:
            rows[match.group(1)] = (match.group(2).replace("\\|", "|"), match.group(3))
    return rows


def _spelled(annotation: object) -> str:
    """The annotation as the table spells it: bare class names, no module paths."""
    # get_args first: on Python 3.10 a parametrised builtin such as list[str] passes
    # isinstance(..., type), so its __name__ would spell it as plain "list".
    text = annotation.__name__ if isinstance(annotation, type) and not get_args(annotation) else str(annotation)
    return re.sub(r"\b(?:[a-z_]\w*\.)+(\w+)", r"\1", text)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("model", [RunConfig, SummaryConfig])
def test_every_config_field_is_documented_with_its_type_and_default(model: type[BaseModel]) -> None:
    documented = _documented(model)

    actual = {name: (_spelled(field.annotation), repr(field.default)) for name, field in model.model_fields.items()}

    assert documented == actual, f"{model.__name__}: documented table differs from the model's fields"
