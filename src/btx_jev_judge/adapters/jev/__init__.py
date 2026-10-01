"""Jev adapter - the HTTP client behind the ``JudgeClient`` port.

Contents:
    * :mod:`.client` - constants, response models, retrying pooled client
    * :mod:`.limiter` - request spacing shared across worker threads
"""

from __future__ import annotations

from .client import (
    BASE_URL_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_RATE,
    ENDPOINT,
    MAX_RETRY_WAIT,
    RETRY_STATUSES,
    JevClient,
    JevSettings,
    resolve_base_url,
)
from .limiter import RateLimiter

__all__ = [
    "BASE_URL_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_RATE",
    "ENDPOINT",
    "MAX_RETRY_WAIT",
    "RETRY_STATUSES",
    "JevClient",
    "JevSettings",
    "RateLimiter",
    "resolve_base_url",
]
