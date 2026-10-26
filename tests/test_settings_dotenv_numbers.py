"""Digit-only .env values reach every text setting as the text the operator wrote.

lib_layered_config's dotenv and environment layers turn an unquoted value into an int or float
whenever that number reads back as the same text (``2026`` stays ``2026``). A pydantic ``str``
field is strict about type, so every model that validates a configuration section must turn such
a number back into its digits; otherwise an ordinary ``.env`` line such as ``JUDGE__MODEL=4``
stops the program.

These tests load a real ``.env`` through the real loader, so a change in the library's coercion
shows up here rather than on a host.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from btx_skill_jev_judge.adapters.config.judge_settings import run_config, summary_config
from btx_skill_jev_judge.adapters.config.loader import get_config
from btx_skill_jev_judge.adapters.logging.setup import (
    _build_runtime_config,  # pyright: ignore[reportPrivateUsage]
)
from btx_skill_jev_judge.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config import Config


def _load_dotenv(directory: Path, line: str) -> Config:
    dotenv = directory / ".env"
    dotenv.write_text(f"{line}\n", encoding="utf-8")
    return get_config(dotenv_path=str(dotenv))


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("env_key", "attr"),
    [("LIB_LOG_RICH__SERVICE", "service"), ("LIB_LOG_RICH__ENVIRONMENT", "environment")],
)
def test_a_digit_only_logging_name_is_read_as_its_digits(
    tmp_path: Path, clear_config_cache: None, env_key: str, attr: str
) -> None:
    config = _load_dotenv(tmp_path, f"{env_key}=2026")
    # Premise: the library hands the value over as a number. Without it the test proves nothing.
    assert isinstance(config.get("lib_log_rich", {})[attr], int)

    runtime = _build_runtime_config(config)  # pyright: ignore[reportPrivateUsage]

    assert getattr(runtime, attr) == "2026"


@pytest.mark.os_agnostic
def test_a_digit_only_model_name_is_read_as_its_digits(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load_dotenv(tmp_path, "JUDGE__MODEL=4")
    assert isinstance(config.get("judge", {})["model"], int)

    assert run_config(config).model == "4"


@pytest.mark.os_agnostic
def test_numeric_settings_still_read_as_numbers(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load_dotenv(tmp_path, "JUDGE__WORKERS=3")

    assert run_config(config).workers == 3


@pytest.mark.os_agnostic
def test_an_out_of_range_digit_only_value_is_still_refused(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load_dotenv(tmp_path, "SUMMARY__MIN_CONFIDENCE=5")

    with pytest.raises(ConfigurationError, match=r"summary\.min_confidence"):
        summary_config(config)
