"""Typed views of the ``[judge]`` and ``[summary]`` configuration sections.

Both models forbid unknown keys. That is what keeps the API key out of configuration: a
``judge.api_key`` entry is refused rather than silently ignored.

Defaults reference the constants owned by the domain, application and Jev layers so a change
there cannot leave this file stating a stale number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from btx_jev_judge.adapters.jev import DEFAULT_MODEL, DEFAULT_RATE, JevSettings
from btx_jev_judge.application.judge import JudgeSettings
from btx_jev_judge.domain.errors import ConfigurationError
from btx_jev_judge.domain.summary import DEFAULT_BAND, DEFAULT_MIN_CONFIDENCE

if TYPE_CHECKING:
    from lib_layered_config import Config

_JEV_DEFAULTS = JevSettings()
_JUDGE_DEFAULTS = JudgeSettings()


class RunConfig(BaseModel):
    """Settings of ``jev-judge run``: pacing, retries, batch size and model.

    Attributes:
        rate: Requests per second across all workers.
        workers: Items judged concurrently.
        attempts: Tries per judgment.
        timeout: Seconds before one request is abandoned.
        cap: Longest string, in characters, that is sent.
        model: Model name sent with every request.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rate: float = Field(default=DEFAULT_RATE, gt=0)
    workers: int = Field(default=_JUDGE_DEFAULTS.workers, ge=1)
    attempts: int = Field(default=_JEV_DEFAULTS.attempts, ge=1)
    timeout: float = Field(default=_JEV_DEFAULTS.timeout, gt=0)
    cap: int = Field(default=_JUDGE_DEFAULTS.cap, ge=100)
    model: str = Field(default=DEFAULT_MODEL, min_length=1)


class SummaryConfig(BaseModel):
    """Settings of ``jev-judge summarize``: the probability band and the confidence floor.

    Attributes:
        band_low: Probabilities below this count as a clear no.
        band_high: Probabilities above this count as a clear yes.
        min_confidence: Judgments below this confidence are flagged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    band_low: float = Field(default=DEFAULT_BAND[0], ge=0, le=1)
    band_high: float = Field(default=DEFAULT_BAND[1], ge=0, le=1)
    min_confidence: float = Field(default=DEFAULT_MIN_CONFIDENCE, ge=0, le=1)

    @model_validator(mode="after")
    def _band_is_ordered(self) -> SummaryConfig:
        """Refuse a band whose low edge is not below its high edge.

        Returns:
            The validated model.

        Raises:
            ValueError: ``band_low`` is greater than or equal to ``band_high``.
        """
        if self.band_low >= self.band_high:
            raise ValueError(f"band_low ({self.band_low}) must be below band_high ({self.band_high})")
        return self


def _describe(section: str, error: ValidationError) -> str:
    """One ``<section>.<key>: <reason>`` per problem; never the offending value.

    Args:
        section: Configuration section the model was validated from.
        error: The validation error to render.

    Returns:
        The problems joined with ``"; "``.
    """
    parts: list[str] = []
    for problem in error.errors(include_input=False):
        where = ".".join([section, *(str(p) for p in problem["loc"])])
        parts.append(f"{where}: {problem['msg']}")
    return "; ".join(parts)


def _section(config: Config, name: str) -> dict[str, Any]:
    """Return a section as a plain mapping, empty when absent.

    Args:
        config: The loaded configuration.
        name: Section name.

    Returns:
        The section's keys and values.
    """
    return dict(config.get(name, default={}))


def run_config(config: Config) -> RunConfig:
    """Read the ``[judge]`` section.

    Args:
        config: The loaded configuration.

    Returns:
        The validated run settings; defaults for absent keys.

    Raises:
        ConfigurationError: A key is unknown (``judge.api_key`` included) or out of range.
    """
    try:
        return RunConfig.model_validate(_section(config, "judge"))
    except ValidationError as exc:
        raise ConfigurationError(_describe("judge", exc)) from exc


def summary_config(config: Config) -> SummaryConfig:
    """Read the ``[summary]`` section.

    Args:
        config: The loaded configuration.

    Returns:
        The validated summary settings; defaults for absent keys.

    Raises:
        ConfigurationError: A key is unknown, out of range, or the band is not ordered.
    """
    try:
        return SummaryConfig.model_validate(_section(config, "summary"))
    except ValidationError as exc:
        raise ConfigurationError(_describe("summary", exc)) from exc


__all__ = ["RunConfig", "SummaryConfig", "run_config", "summary_config"]
