"""API key lookup: the environment first, then a private keyfile; the key is never echoed."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from btx_skill_jev_judge.adapters.key import KEY_ENV, KEYFILE, KEYFILE_FORBIDDEN_BITS, load_key

if TYPE_CHECKING:
    from pathlib import Path

KEY = "tk_" + "a" * 40


def _keyfile(home: Path, text: str, mode: int = 0o600) -> Path:
    path = home / KEYFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def test_the_env_key_wins_over_the_keyfile(tmp_path: Path) -> None:
    _keyfile(tmp_path, "tk_other")
    assert load_key({KEY_ENV: " " + KEY + "\n"}, tmp_path) == (KEY, "env")


def test_the_keyfile_is_read_when_no_env_key(tmp_path: Path) -> None:
    _keyfile(tmp_path, "\ufeff" + KEY + "\n")
    assert load_key({}, tmp_path) == (KEY, "keyfile")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not exist on Windows")
def test_a_group_readable_keyfile_is_refused(tmp_path: Path) -> None:
    _keyfile(tmp_path, KEY, mode=0o640)
    key, reason = load_key({}, tmp_path)
    assert key is None
    assert "permissions" in reason


def test_no_key_anywhere_says_so(tmp_path: Path) -> None:
    assert load_key({}, tmp_path) == (None, "no TYPESAFE_API_KEY in the environment or a .env, and no keyfile")


def test_a_key_that_is_not_printable_ascii_is_refused(tmp_path: Path) -> None:
    key, reason = load_key({KEY_ENV: "tk_\u00e9\u00e9"}, tmp_path)
    assert key is None
    assert "printable ascii" in reason


def test_a_keyfile_with_non_ascii_text_is_refused(tmp_path: Path) -> None:
    non_ascii_key = "tk_k\u00e9y"
    _keyfile(tmp_path, non_ascii_key, mode=0o600)
    key, reason = load_key({}, tmp_path)
    assert key is None
    assert "printable ascii" in reason
    assert non_ascii_key not in reason


def test_an_empty_keyfile_says_it_is_empty(tmp_path: Path) -> None:
    _keyfile(tmp_path, "\n")
    assert load_key({}, tmp_path) == (None, "keyfile is empty: paste the key into it")


def test_a_keyfile_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = _keyfile(tmp_path, "")
    path.write_bytes(b"\xff\xfe\x00bad")
    assert load_key({}, tmp_path) == (None, "keyfile unreadable: save it as UTF-8 text")


def test_the_forbidden_bits_are_the_group_and_other_bits() -> None:
    assert KEYFILE_FORBIDDEN_BITS == 0o077


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not exist on Windows")
def test_no_message_ever_contains_the_key_literal(tmp_path: Path) -> None:
    keyfile = _keyfile(tmp_path, KEY, mode=0o644)
    messages = [
        load_key({}, tmp_path)[1],
        load_key({KEY_ENV: KEY + "\u00e9"}, tmp_path)[1],
        load_key({KEY_ENV: KEY}, tmp_path)[1],
    ]
    keyfile.chmod(0o600)
    messages.append(load_key({}, tmp_path)[1])
    assert all(KEY not in message for message in messages)
