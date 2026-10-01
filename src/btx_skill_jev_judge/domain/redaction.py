"""Redaction and capping of the strings in an item's state before it leaves the machine.

Contents:
    * :func:`redact` - replace secret shapes and the API key literal.
    * :func:`cap_text` - keep the head and tail of an over-long string.
    * :func:`prepare_state` - redact and cap every string in a nested state.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import JsonValue

REDACTED = "[REDACTED]"
# Characters per string. Jev reads at most 32k tokens of state plus the longest question, so a
# string this long is already most of the budget; the cap keeps its head and tail.
DEFAULT_CAP = 60_000

_SECRET_PATTERNS = tuple(
    re.compile(p, re.DOTALL)
    for p in (
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}",
        r"\bgithub_pat_[A-Za-z0-9_]{30,}",
        r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bAIza[0-9A-Za-z_-]{35}\b",
        r"\bsk-[A-Za-z0-9_-]{20,}",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    )
)
# Keep the label so a reader still sees what was there: "API_KEY=[REDACTED]".
_LABELLED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL)[A-Z0-9_]*\s*[=:]\s*)"
        r"[\"']?[^\s\"']{6,}",
        r"(\bauthorization:\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]{8,}",
        r"(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)[^/\s@]+(?=@)",
    )
)


def redact(text: str, key: str | None) -> tuple[str, int]:
    """Replace secrets in ``text`` with ``[REDACTED]``.

    Args:
        text: Any string about to leave the machine.
        key: The API key, redacted as a literal wherever it appears; None to skip.

    Returns:
        The redacted text and how many spans were replaced.

    Examples:
        >>> redact("token ghp_" + "x" * 36, key=None)
        ('token [REDACTED]', 1)
    """
    count = 0
    if key and key in text:
        count += text.count(key)
        text = text.replace(key, REDACTED)
    for pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        count += n
    for pattern in _LABELLED_PATTERNS:
        text, n = pattern.subn(lambda m: m.group(1) + REDACTED, text)
        count += n
    return text, count


def cap_text(text: str, cap: int) -> str:
    """Shorten ``text`` to at most ``cap`` characters, keeping its head and tail.

    Args:
        text: The string to shorten.
        cap: The longest the result may be.

    Returns:
        ``text`` unchanged when it fits, else head + a ``[... N chars cut ...]`` marker + tail.

    Examples:
        >>> cap_text("short", 100)
        'short'
    """
    if len(text) <= cap:
        return text
    marker = f" [... {len(text) - cap} chars cut ...] "
    keep = max(0, cap - len(marker))
    head = keep // 2
    return text[:head] + marker + text[len(text) - (keep - head) :]


def _scrub(value: JsonValue, *, key: str | None, cap: int) -> tuple[JsonValue, int]:
    """Redact and cap the strings in one JSON value, returning it with the redaction count."""
    if isinstance(value, str):
        text, n = redact(value, key)
        return cap_text(text, cap), n
    if isinstance(value, dict):
        scrubbed = {k: _scrub(v, key=key, cap=cap) for k, v in value.items()}
        return {k: v for k, (v, _) in scrubbed.items()}, sum(n for _, n in scrubbed.values())
    if isinstance(value, list):
        items = [_scrub(v, key=key, cap=cap) for v in value]
        return [v for v, _ in items], sum(n for _, n in items)
    return value, 0


def prepare_state(state: Mapping[str, JsonValue], *, key: str | None, cap: int) -> tuple[dict[str, JsonValue], int]:
    """Redact and cap every string in a state, keeping its structure.

    Args:
        state: The item's named fields; nested objects and lists are walked.
        key: The API key, redacted as a literal.
        cap: The longest a single string may be; longer ones keep their head and tail.

    Returns:
        The state to send, and the number of redacted spans.

    Examples:
        >>> prepare_state({"n": 3, "t": "fine"}, key=None, cap=100)
        ({'n': 3, 't': 'fine'}, 0)
    """
    scrubbed = {k: _scrub(v, key=key, cap=cap) for k, v in state.items()}
    return {k: v for k, (v, _) in scrubbed.items()}, sum(n for _, n in scrubbed.values())


__all__ = [
    "DEFAULT_CAP",
    "REDACTED",
    "cap_text",
    "prepare_state",
    "redact",
]
