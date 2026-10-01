"""Domain-specific exceptions for typed error handling at boundaries."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Missing, invalid, or incomplete configuration.

    Raised when required configuration values are absent, malformed, or
    logically inconsistent. Typically caught at CLI boundaries to provide
    user-friendly error messages.

    Example:
        >>> from btx_skill_jev_judge.domain.errors import ConfigurationError
        >>> err = ConfigurationError("No API key configured")
        >>> str(err)
        'No API key configured'
    """


class InputError(Exception):
    """Input the caller must fix: an unreadable file, a malformed item or question, a bad option.

    The CLI maps it to exit code 2.

    Example:
        >>> from btx_skill_jev_judge.domain.errors import InputError
        >>> str(InputError("questions: need a non-empty JSON list"))
        'questions: need a non-empty JSON list'
    """


__all__ = [
    "ConfigurationError",
    "InputError",
]
