"""Find the Jev API key. The key is never printed, logged or put on argv."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["KEYFILE", "KEYFILE_FORBIDDEN_BITS", "KEY_ENV", "load_key"]

KEY_ENV = "TYPESAFE_API_KEY"
KEYFILE = Path(".credentials") / "typesafe.key"
KEYFILE_FORBIDDEN_BITS = stat.S_IRWXG | stat.S_IRWXO


def load_key(env: Mapping[str, str], home: Path) -> tuple[str | None, str]:
    """Find the API key and say where it came from, or why there is none.

    Args:
        env: The environment; ``TYPESAFE_API_KEY`` wins when set.
        home: The home directory holding ``.credentials/typesafe.key``.

    Returns:
        ``(key, "env" | "keyfile")``, or ``(None, reason)``. No reason ever contains the key.
    """
    value = env.get(KEY_ENV, "").strip()
    source = "env"
    if not value:
        value, source = _read_keyfile(home / KEYFILE)
        if not value:
            return None, source
    if not (value.isascii() and value.isprintable()):
        return None, f"{source}: api key is not printable ascii"
    return value, source


def _read_keyfile(path: Path) -> tuple[str, str]:
    try:
        info = path.stat()
    except FileNotFoundError:
        return "", f"no {KEY_ENV} in the environment or a .env, and no keyfile"
    except OSError as exc:
        return "", f"keyfile unreadable: {exc.strerror or exc}"
    if os.name != "nt" and info.st_mode & KEYFILE_FORBIDDEN_BITS:
        return "", f"keyfile permissions: {path} must be mode 600"
    try:
        value = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return "", "keyfile unreadable: save it as UTF-8 text"
    return value, ("keyfile" if value else "keyfile is empty: paste the key into it")
