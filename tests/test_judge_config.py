"""The [judge] and [summary] configuration sections: bundled defaults, overrides and refusals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import rtoml
from lib_layered_config import Config

from btx_skill_jev_judge.adapters.config import apply_overrides, get_default_config_path
from btx_skill_jev_judge.adapters.config.judge_settings import RunConfig, SummaryConfig, run_config, summary_config
from btx_skill_jev_judge.adapters.jev import DEFAULT_MODEL, DEFAULT_RATE, JevSettings
from btx_skill_jev_judge.application.judge import JudgeSettings
from btx_skill_jev_judge.domain.errors import ConfigurationError
from btx_skill_jev_judge.domain.summary import DEFAULT_BAND, DEFAULT_MIN_CONFIDENCE

ConfigFactory = Callable[[dict[str, Any]], Config]


def _shipped_section(name: str) -> dict[str, Any]:
    shipped = get_default_config_path().parent / "defaultconfig.d" / "60-judge.toml"
    return rtoml.loads(shipped.read_text(encoding="utf-8"))[name]


def test_shipped_judge_section_equals_the_model_defaults() -> None:
    assert RunConfig.model_validate(_shipped_section("judge")) == RunConfig()


def test_shipped_summary_section_equals_the_model_defaults() -> None:
    assert SummaryConfig.model_validate(_shipped_section("summary")) == SummaryConfig()


def test_shipped_sections_state_every_key() -> None:
    assert set(_shipped_section("judge")) == set(RunConfig.model_fields)
    assert set(_shipped_section("summary")) == set(SummaryConfig.model_fields)


def test_run_defaults_agree_with_the_code_constants() -> None:
    cfg = RunConfig()
    jev, judge = JevSettings(), JudgeSettings()
    assert (cfg.model, cfg.rate) == (DEFAULT_MODEL, DEFAULT_RATE)
    assert (cfg.timeout, cfg.attempts, cfg.workers) == (jev.timeout, jev.attempts, jev.workers)
    assert (cfg.workers, cfg.cap) == (judge.workers, judge.cap)


def test_summary_defaults_agree_with_the_domain_constants() -> None:
    cfg = SummaryConfig()
    assert (cfg.band_low, cfg.band_high) == DEFAULT_BAND
    assert cfg.min_confidence == DEFAULT_MIN_CONFIDENCE


def test_missing_sections_fall_back_to_defaults(config_factory: ConfigFactory) -> None:
    config = config_factory({})
    assert run_config(config) == RunConfig()
    assert summary_config(config) == SummaryConfig()


def test_a_set_override_reaches_the_run_config(config_factory: ConfigFactory) -> None:
    config = apply_overrides(config_factory({"judge": {"workers": 3}}), ("judge.rate=5",))
    cfg = run_config(config)
    assert cfg.rate == 5.0
    assert cfg.workers == 3


def test_a_set_override_reaches_the_summary_config(config_factory: ConfigFactory) -> None:
    config = apply_overrides(config_factory({}), ("summary.min_confidence=0.9",))
    assert summary_config(config).min_confidence == 0.9


def test_an_api_key_in_config_is_refused_naming_the_key(config_factory: ConfigFactory) -> None:
    config = config_factory({"judge": {"api_key": "x"}})
    with pytest.raises(ConfigurationError, match=r"judge\.api_key"):
        run_config(config)


def test_the_refusal_never_echoes_the_key_value(config_factory: ConfigFactory) -> None:
    config = config_factory({"judge": {"api_key": "sekrit-value-123"}})
    with pytest.raises(ConfigurationError) as caught:
        run_config(config)
    assert "sekrit-value-123" not in str(caught.value)


@pytest.mark.parametrize(("low", "high"), [(0.8, 0.2), (0.5, 0.5)])
def test_band_low_must_stay_below_band_high(config_factory: ConfigFactory, low: float, high: float) -> None:
    config = config_factory({"summary": {"band_low": low, "band_high": high}})
    with pytest.raises(ConfigurationError, match=r"band_low.*band_high") as caught:
        summary_config(config)
    assert str(low) not in str(caught.value).split("band_high", 1)[1]


@pytest.mark.parametrize(
    ("key", "value"),
    [("rate", 0), ("workers", 0), ("attempts", 0), ("attempts", 11), ("timeout", -1), ("cap", 10), ("model", "")],
)
def test_out_of_range_judge_values_are_refused(config_factory: ConfigFactory, key: str, value: object) -> None:
    with pytest.raises(ConfigurationError, match=rf"judge\.{key}"):
        run_config(config_factory({"judge": {key: value}}))


def test_summary_values_outside_zero_one_are_refused(config_factory: ConfigFactory) -> None:
    with pytest.raises(ConfigurationError, match=r"summary\.min_confidence"):
        summary_config(config_factory({"summary": {"min_confidence": 1.5}}))
