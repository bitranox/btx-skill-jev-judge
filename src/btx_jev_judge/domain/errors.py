"""Domain-specific exceptions for typed error handling at boundaries."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Missing, invalid, or incomplete configuration.

    Raised when required configuration values are absent, malformed, or
    logically inconsistent. Typically caught at CLI boundaries to provide
    user-friendly error messages.

    Example:
        >>> from btx_jev_judge.domain.errors import ConfigurationError
        >>> err = ConfigurationError("No API key configured")
        >>> str(err)
        'No API key configured'
    """


__all__ = [
    "ConfigurationError",
]
