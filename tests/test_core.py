"""The batch core: client, retries, rate limit, redaction, input validation, rows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

import jev_judge as jj
from conftest import JevStub

KEY = "tk_" + "a" * 40
GITHUB_TOKEN = "ghp_" + "B" * 36


def _noul(value: float, tokens: int = 11) -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "usage": {"input_tokens": tokens, "output_tokens": 3},
        "answers": {"dup": {"type": "noul", "noul": value}},
    }


def _dup_by_title(body: dict[str, Any], _n: int) -> tuple[int, Any, dict[str, str]]:
    return 200, _noul(0.9 if "dup" in body["state"]["title"] else 0.1), {}


def _questions() -> list[jj.Question]:
    return jj.parse_questions(
        [{"id": "dup", "type": "noul", "instructions": "Is `title` a duplicate report of an existing issue?"}]
    )


def _client(stub: JevStub, waits: list[float] | None = None, attempts: int = 4) -> jj.JevClient:
    def sleep(seconds: float) -> None:
        if waits is not None:
            waits.append(seconds)

    return jj.JevClient(
        key=KEY,
        base_url=stub.url,
        timeout=5.0,
        attempts=attempts,
        limiter=jj.RateLimiter(rate=1000.0, sleep=sleep),
        sleep=sleep,
    )


def _judge(stub: JevStub, items: list[tuple[str, dict[str, Any]]], **kw: Any) -> list[jj.Row]:
    waits = kw.pop("waits", None)
    attempts = kw.pop("attempts", 4)
    with _client(stub, waits, attempts) as client:
        return jj.judge_all(
            [jj.Item(id=i, state=s) for i, s in items],
            _questions(),
            client=client,
            key=KEY,
            settings=jj.Settings(**kw),
        )


# --- answering -------------------------------------------------------------------------------


def test_every_item_is_answered_in_input_order(jev: JevStub) -> None:
    jev.reply = _dup_by_title
    rows = _judge(
        jev,
        [("a", {"title": "dup of 12"}), ("b", {"title": "new crash"}), ("c", {"title": "dup"})],
        workers=3,
    )
    assert [r.id for r in rows] == ["a", "b", "c"]
    assert [r.answers["dup"].value for r in rows] == [0.9, 0.1, 0.9]
    assert all(r.ok and r.input_tokens == 11 and r.model == "jev-1.13.0" for r in rows)


def test_the_request_carries_model_bearer_key_and_question_shape(jev: JevStub) -> None:
    jev.reply = _dup_by_title
    _judge(jev, [("a", {"title": "x"})])
    body, headers = jev.seen[0], jev.headers[0]
    assert body["model"] == "jev-latest"
    assert body["questions"] == {
        "dup": {"type": "noul", "instructions": "Is `title` a duplicate report of an existing issue?"}
    }
    assert headers["authorization"] == "Bearer " + KEY


def test_choice_and_score_answers_are_normalised(jev: JevStub) -> None:
    questions = jj.parse_questions(
        [
            {
                "id": "team",
                "type": "choice",
                "instructions": "Which team owns `title`?",
                "criteria": {"billing": "payments", "tech": None},
            },
            {
                "id": "sev",
                "type": "score",
                "instructions": "How severe is `title`?",
                "criteria": ["cosmetic", "annoying", "blocking"],
            },
        ]
    )
    jev.reply = lambda body, n: (
        200,
        {
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 40},
            "answers": {
                "team": {
                    "type": "choice",
                    "choice": "tech",
                    "probabilities": {"billing": 0.1, "tech": 0.9},
                    "confidence": 0.8,
                },
                "sev": {
                    "type": "score",
                    "score": 1.7,
                    "legend": {"0": "cosmetic", "1": "annoying", "2": "blocking"},
                    "probabilities": {"0": 0.0, "1": 0.3, "2": 0.7},
                    "confidence": 0.6,
                },
            },
        },
        {},
    )
    with _client(jev) as client:
        row = jj.judge_all([jj.Item(id="a", state={"title": "x"})], questions, client=client, key=KEY)[0]
    assert row.ok
    assert (row.answers["team"].value, row.answers["team"].confidence) == ("tech", 0.8)
    sev = row.answers["sev"]
    assert sev.probabilities is not None
    assert (sev.value, sev.probabilities["2"]) == (1.7, 0.7)


def test_an_answer_missing_a_question_is_a_failed_row(jev: JevStub) -> None:
    jev.reply = lambda body, n: (200, {"model": "jev-1.13.0", "usage": {}, "answers": {}}, {})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.ok is False and row.reason is not None and "dup" in row.reason


def test_a_malformed_body_is_a_failed_row(jev: JevStub) -> None:
    jev.reply = lambda body, n: (200, b"not json", {})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.ok is False and row.reason is not None and row.reason.startswith("bad response")


# --- retries -----------------------------------------------------------------------------------


def test_a_rate_limit_is_retried_after_the_servers_retry_after(jev: JevStub) -> None:
    jev.reply = lambda body, n: (
        (429, {"error": "slow"}, {"Retry-After": "3"}) if n == 1 else (200, _noul(0.5), {})
    )
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], waits=waits)[0]
    assert row.ok and row.attempts == 2 and len(jev.seen) == 2
    assert 3.0 in waits


def test_an_overload_without_retry_after_backs_off_exponentially(jev: JevStub) -> None:
    jev.reply = lambda body, n: (529, {}, {}) if n < 3 else (200, _noul(0.5), {})
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], waits=waits)[0]
    assert row.ok and row.attempts == 3
    assert [w for w in waits if w >= 1] == [2.0, 4.0]


def test_retries_give_up_with_the_last_reason(jev: JevStub) -> None:
    jev.reply = lambda body, n: (529, {}, {})
    row = _judge(jev, [("a", {"title": "x"})], attempts=3)[0]
    assert row.ok is False and row.reason == "http 529" and row.attempts == 3
    assert len(jev.seen) == 3


@pytest.mark.parametrize("status", [401, 422])
def test_a_rejected_request_is_a_failed_row_sent_once(jev: JevStub, status: int) -> None:
    jev.reply = lambda body, n: (status, {"detail": "bad question"}, {})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.ok is False and row.reason is not None
    assert row.reason.startswith(f"http {status}")
    assert len(jev.seen) == 1


def test_an_unreachable_host_is_a_failed_row_not_an_exception() -> None:
    dead = JevStub(url="http://127.0.0.1:9")  # discard port: nothing listens there
    row = _judge(dead, [("a", {"title": "x"})], attempts=2)[0]
    assert row.ok is False and row.reason is not None and row.reason.startswith("connection")


# --- egress: redaction and state shape ---------------------------------------------------------


def test_the_key_and_a_github_token_are_redacted_before_they_leave(jev: JevStub) -> None:
    jev.reply = _dup_by_title
    rows = _judge(jev, [("a", {"title": f"token {KEY} and {GITHUB_TOKEN}"})])
    sent = jev.seen[0]["state"]["title"]
    assert KEY not in sent and GITHUB_TOKEN not in sent
    assert sent.count("[REDACTED]") == 2 and rows[0].redactions == 2


def test_nested_state_keeps_its_structure_and_is_redacted_inside(jev: JevStub) -> None:
    jev.reply = lambda body, n: (200, _noul(0.2), {})
    _judge(jev, [("a", {"title": "t", "labels": ["bug", f"key {GITHUB_TOKEN}"], "n": 3})])
    state = jev.seen[0]["state"]
    assert state["labels"] == ["bug", "key [REDACTED]"] and state["n"] == 3


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
    text, n = jj.redact(f"before {secret} after", key=None)
    assert n >= 1 and "before" in text and "after" in text
    assert "s3cr3t" not in text and "hunter2" not in text and "MIIEow" not in text
    assert "abcdefghijklmnopqrstuvwxyz012345" not in text and "AKIAABCD" not in text


def test_ordinary_text_is_not_redacted() -> None:
    text = "the key point: retry 3 times, then mark the issue as a duplicate"
    assert jj.redact(text, key=None) == (text, 0)


def test_a_long_field_keeps_head_and_tail_and_marks_the_cut() -> None:
    fields, _n = jj.prepare_state({"body": "H" * 50 + "M" * 1000 + "T" * 50}, key=None, cap=200)
    body = fields["body"]
    assert isinstance(body, str)
    assert len(body) <= 200 and body.startswith("H" * 50) and body.endswith("T" * 50)
    assert "chars cut" in body


# --- rate limiter ------------------------------------------------------------------------------


def test_the_limiter_spaces_requests_at_the_configured_rate() -> None:
    waits: list[float] = []
    limiter = jj.RateLimiter(rate=10.0, clock=lambda: 100.0, sleep=waits.append)
    for _ in range(4):
        limiter.acquire()
    assert waits == pytest.approx([0.1, 0.2, 0.3])


# --- input files -------------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_items_accepts_int_and_string_ids_and_skips_blank_lines(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n\n{"id": "x", "state": {"t": "b"}}\n')
    assert [(i.id, i.state) for i in jj.load_items(p)] == [("1", {"t": "a"}), ("x", {"t": "b"})]


def test_load_items_refuses_a_duplicate_id_naming_the_line(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n{"id": "1", "state": {"t": "b"}}\n')
    with pytest.raises(jj.UsageError, match="line 2: duplicate id '1'"):
        jj.load_items(p)


def test_load_items_refuses_an_empty_state_naming_the_field(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {}}\n')
    with pytest.raises(jj.UsageError, match=r"line 1: state: "):
        jj.load_items(p)


def test_load_items_refuses_invalid_json_naming_the_line(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n{oops\n')
    with pytest.raises(jj.UsageError, match="line 2: not JSON"):
        jj.load_items(p)


def test_load_questions_refuses_a_one_option_choice(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "q.json",
        json.dumps([{"id": "k", "type": "choice", "instructions": "pick", "criteria": {"one": "x"}}]),
    )
    with pytest.raises(jj.UsageError, match="criteria"):
        jj.load_questions(p)


def test_load_questions_refuses_an_eleven_level_score() -> None:
    with pytest.raises(jj.UsageError, match="criteria"):
        jj.parse_questions(
            [{"id": "s", "type": "score", "instructions": "rate", "criteria": [str(i) for i in range(11)]}]
        )


def test_load_questions_refuses_a_duplicate_question_id() -> None:
    q = {"id": "d", "type": "noul", "instructions": "yes?"}
    with pytest.raises(jj.UsageError, match="duplicate question id 'd'"):
        jj.parse_questions([q, q])


def test_load_questions_refuses_an_unknown_type() -> None:
    with pytest.raises(jj.UsageError, match="type"):
        jj.parse_questions([{"id": "d", "type": "maybe", "instructions": "yes?"}])


def test_structured_instructions_and_noul_criteria_are_accepted() -> None:
    q = jj.parse_questions(
        [
            {
                "id": "same",
                "type": "noul",
                "instructions": {
                    "candidate": {"name": "J. Smith"},
                    "question": "Is `person` the same as `candidate`?",
                },
                "criteria": {"true": "same person", "false": "different"},
            }
        ]
    )[0]
    instructions = q.to_api()["instructions"]
    assert isinstance(instructions, dict)
    assert instructions["candidate"] == {"name": "J. Smith"}
    assert q.to_api()["criteria"] == {"true": "same person", "false": "different"}


# --- key and endpoint --------------------------------------------------------------------------


def test_the_env_key_wins_over_the_keyfile(tmp_path: Path) -> None:
    assert jj.load_key({"TYPESAFE_API_KEY": " " + KEY + "\n"}, tmp_path) == (KEY, "env")


def test_the_keyfile_is_read_when_no_env_key(tmp_path: Path) -> None:
    keyfile = tmp_path / ".credentials" / "typesafe.key"
    keyfile.parent.mkdir()
    keyfile.write_text("﻿" + KEY + "\n", encoding="utf-8")
    keyfile.chmod(0o600)
    assert jj.load_key({}, tmp_path) == (KEY, "keyfile")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not exist on Windows")
def test_a_group_readable_keyfile_is_refused(tmp_path: Path) -> None:
    keyfile = tmp_path / ".credentials" / "typesafe.key"
    keyfile.parent.mkdir()
    keyfile.write_text(KEY, encoding="utf-8")
    keyfile.chmod(0o640)
    key, reason = jj.load_key({}, tmp_path)
    assert key is None and "permissions" in reason


def test_no_key_anywhere_says_so(tmp_path: Path) -> None:
    assert jj.load_key({}, tmp_path) == (None, "no TYPESAFE_API_KEY and no keyfile")


def test_a_key_that_is_not_printable_ascii_is_refused(tmp_path: Path) -> None:
    key, reason = jj.load_key({"TYPESAFE_API_KEY": "tk_éé"}, tmp_path)
    assert key is None and "printable ascii" in reason


def test_a_non_loopback_base_url_override_is_ignored() -> None:
    assert jj.resolve_base_url({"JEV_JUDGE_BASE_URL": "https://evil.example"}) == jj.DEFAULT_BASE_URL
    assert jj.resolve_base_url({"JEV_JUDGE_BASE_URL": "http://127.0.0.1:8123"}) == "http://127.0.0.1:8123"


def test_an_empty_keyfile_says_it_is_empty(tmp_path: Path) -> None:
    keyfile = tmp_path / ".credentials" / "typesafe.key"
    keyfile.parent.mkdir()
    keyfile.write_text("\n", encoding="utf-8")
    keyfile.chmod(0o600)
    assert jj.load_key({}, tmp_path) == (None, "keyfile is empty: paste the key into it")
