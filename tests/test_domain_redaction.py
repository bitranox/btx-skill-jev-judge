"""Redaction: no secret leaves in a state, ordinary text is left alone, long strings are capped."""

from __future__ import annotations

import pytest

from btx_skill_jev_judge.domain.redaction import REDACTED, prepare_state, redact

KEY = "tk_" + "a" * 40
GITHUB_TOKEN = "ghp_" + "B" * 36


def test_the_key_and_a_github_token_are_redacted_in_a_state() -> None:
    state, n = prepare_state({"title": f"token {KEY} and {GITHUB_TOKEN}"}, key=KEY, cap=1000)
    sent = state["title"]
    assert isinstance(sent, str)
    assert KEY not in sent and GITHUB_TOKEN not in sent
    assert sent.count(REDACTED) == 2 and n == 2


def test_nested_state_keeps_its_structure_and_is_redacted_inside() -> None:
    state, n = prepare_state({"title": "t", "labels": ["bug", f"key {GITHUB_TOKEN}"], "n": 3}, key=KEY, cap=1000)
    assert state["labels"] == ["bug", "key [REDACTED]"] and state["n"] == 3 and n == 1


@pytest.mark.parametrize(
    "secret",
    [
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
        "API_KEY=s3cr3tvalue123",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        "xoxb-1234567890-abcdefghijkl",
        "AKIAABCDEFGHIJKLMNOP",
        "https://user:hunter2pass@example.com/x",
    ],
)
def test_common_secret_shapes_are_redacted(secret: str) -> None:
    text, n = redact(f"before {secret} after", key=None)
    assert n >= 1 and "before" in text and "after" in text
    assert "s3cr3t" not in text and "hunter2" not in text and "MIIEow" not in text
    assert "abcdefghijklmnopqrstuvwxyz012345" not in text and "AKIAABCD" not in text


def test_ordinary_text_is_not_redacted() -> None:
    text = "the key point: retry 3 times, then mark the issue as a duplicate"
    assert redact(text, key=None) == (text, 0)


def test_a_long_field_keeps_head_and_tail_and_marks_the_cut() -> None:
    fields, _n = prepare_state({"body": "H" * 50 + "M" * 1000 + "T" * 50}, key=None, cap=200)
    body = fields["body"]
    assert isinstance(body, str)
    assert len(body) <= 200 and body.startswith("H" * 50) and body.endswith("T" * 50)
    assert "chars cut" in body
