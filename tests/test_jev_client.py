"""The Jev adapter: pooled client, retries, rate limiter, loopback-only base URL override."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from conftest import JevStub

from btx_skill_jev_judge.adapters.jev import (
    DEFAULT_BASE_URL,
    MAX_RETRY_WAIT,
    JevClient,
    JevSettings,
    RateLimiter,
    resolve_base_url,
)
from btx_skill_jev_judge.application.judge import JudgeSettings, judge_all
from btx_skill_jev_judge.domain.errors import InputError
from btx_skill_jev_judge.domain.models import Item, Question, Row, parse_questions

KEY = "tk_" + "a" * 40


def _noul(value: float, tokens: int = 11) -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "usage": {"input_tokens": tokens, "output_tokens": 3},
        "answers": {"dup": {"type": "noul", "noul": value}},
    }


def _dup_by_title(body: dict[str, Any], _n: int) -> tuple[int, Any, dict[str, str]]:
    return 200, _noul(0.9 if "dup" in body["state"]["title"] else 0.1), {}


def _questions() -> list[Question]:
    return parse_questions(
        [{"id": "dup", "type": "noul", "instructions": "Is `title` a duplicate report of an existing issue?"}]
    )


def _client(
    stub: JevStub, waits: list[float] | None = None, attempts: int = 4, timeout: float = 5.0, workers: int = 8
) -> JevClient:
    def sleep(seconds: float) -> None:
        if waits is not None:
            waits.append(seconds)

    return JevClient(
        key=KEY,
        base_url=stub.url,
        settings=JevSettings(timeout=timeout, attempts=attempts, workers=workers),
        limiter=RateLimiter(rate=1000.0, sleep=sleep),
        sleep=sleep,
    )


def _judge(stub: JevStub, items: list[tuple[str, dict[str, Any]]], **kw: Any) -> list[Row]:
    waits = kw.pop("waits", None)
    attempts = kw.pop("attempts", 4)
    timeout = kw.pop("timeout", 5.0)
    with _client(stub, waits, attempts, timeout) as client:
        return judge_all(
            [Item(id=i, state=s) for i, s in items],
            _questions(),
            client=client,
            key=KEY,
            settings=JudgeSettings(**kw),
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
    questions = parse_questions(
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
        row = judge_all(
            [Item(id="a", state={"title": "x"})], questions, client=client, key=KEY, settings=JudgeSettings()
        )[0]
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
    jev.reply = lambda body, n: (429, {"error": "slow"}, {"Retry-After": "3"}) if n == 1 else (200, _noul(0.5), {})
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


def test_a_retry_after_above_the_ceiling_is_clamped(jev: JevStub) -> None:
    jev.reply = lambda body, n: (429, {}, {"Retry-After": "3600"}) if n == 1 else (200, _noul(0.5), {})
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], waits=waits)[0]
    assert row.ok and row.attempts == 2
    assert [w for w in waits if w >= 1] == [MAX_RETRY_WAIT]


def test_a_non_numeric_retry_after_falls_back_to_exponential_backoff(jev: JevStub) -> None:
    jev.reply = lambda body, n: (
        (503, {}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        if n == 1
        else (
            200,
            _noul(0.5),
            {},
        )
    )
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], waits=waits)[0]
    assert row.ok and row.attempts == 2
    assert [w for w in waits if w >= 1] == [2.0]


def test_the_exponential_backoff_is_capped_at_the_ceiling(jev: JevStub) -> None:
    jev.reply = lambda body, n: (529, {}, {})
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], attempts=10, waits=waits)[0]
    assert row.ok is False and row.attempts == 10
    assert [w for w in waits if w >= 1] == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0, 60.0]
    assert max(waits) == MAX_RETRY_WAIT


def test_a_undecodable_response_is_a_failed_row_not_an_exception_and_not_retried(jev: JevStub) -> None:
    jev.reply = lambda body, n: (200, b"plainly not gzip", {"Content-Encoding": "gzip"})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.ok is False and row.reason is not None and "DecodingError" in row.reason
    assert len(jev.seen) == 1


def test_an_error_body_quoted_in_the_reason_is_redacted(jev: JevStub) -> None:
    token = "ghp_" + "b" * 36
    jev.reply = lambda body, n: (400, {"detail": f"bad {KEY} and {token}"}, {})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.ok is False and row.reason is not None and row.reason.startswith("http 400")
    assert KEY not in row.reason and token not in row.reason


@pytest.mark.parametrize("secret", [KEY, "ghp_" + "b" * 36], ids=["api-key", "github-token"])
def test_a_secret_straddling_the_quote_limit_leaks_no_prefix(jev: JevStub, secret: str) -> None:
    # Starts inside the quoted 200 characters and ends past them: cut first, the remaining head
    # no longer matches the full pattern and would be quoted verbatim.
    body = ("x" * 189 + " " + secret + " tail").encode()
    jev.reply = lambda _body, _n: (400, body, {})
    row = _judge(jev, [("a", {"title": "x"})])[0]
    assert row.reason is not None and row.reason.startswith("http 400: ")
    assert secret[:8] not in row.reason


def test_a_request_timeout_is_reported_as_timeout_and_retried(jev: JevStub) -> None:
    def slow_once(body: dict[str, Any], n: int) -> tuple[int, Any, dict[str, str]]:
        if n == 1:
            time.sleep(0.6)  # outlasts the 0.1 s client timeout; the stub thread, not the client, waits
        return 200, _noul(0.5), {}

    jev.reply = slow_once
    waits: list[float] = []
    row = _judge(jev, [("a", {"title": "x"})], waits=waits, timeout=0.1)[0]
    assert row.ok and row.attempts == 2 and len(jev.seen) == 2
    assert [w for w in waits if w >= 1] == [2.0]


def test_a_timeout_on_every_attempt_is_a_failed_row_with_reason_timeout(jev: JevStub) -> None:
    def always_slow(body: dict[str, Any], n: int) -> tuple[int, Any, dict[str, str]]:
        time.sleep(0.4)
        return 200, _noul(0.5), {}

    jev.reply = always_slow
    row = _judge(jev, [("a", {"title": "x"})], attempts=2, timeout=0.1)[0]
    assert row.ok is False and row.reason == "timeout" and row.attempts == 2


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


# --- rate limiter ------------------------------------------------------------------------------


def test_the_limiter_spaces_requests_at_the_configured_rate() -> None:
    waits: list[float] = []
    limiter = RateLimiter(rate=10.0, clock=lambda: 100.0, sleep=waits.append)
    for _ in range(4):
        limiter.acquire()
    assert waits == pytest.approx([0.1, 0.2, 0.3])


def test_the_limiter_spaces_requests_across_worker_threads() -> None:
    spacing: list[float] = []
    limiter = RateLimiter(rate=10.0, clock=lambda: 100.0, sleep=spacing.append)
    threads = [threading.Thread(target=limiter.acquire) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(spacing) == pytest.approx([0.1, 0.2, 0.3])


def test_a_shared_limiter_spaces_every_worker_of_a_batch(jev: JevStub) -> None:
    jev.reply = _dup_by_title
    spacing: list[float] = []
    client = JevClient(
        key=KEY,
        base_url=jev.url,
        settings=JevSettings(timeout=5.0, workers=3),
        limiter=RateLimiter(rate=10.0, clock=lambda: 100.0, sleep=spacing.append),
    )
    with client:
        rows = judge_all(
            [Item(id=str(i), state={"title": "x"}) for i in range(6)],
            _questions(),
            client=client,
            key=KEY,
            settings=JudgeSettings(workers=3),
        )
    assert all(r.ok for r in rows)
    assert sorted(spacing) == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])


def test_a_non_positive_rate_is_refused() -> None:
    with pytest.raises(InputError, match="rate must be positive"):
        RateLimiter(rate=0.0)


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ("http://127.0.0.1:8123", "http://127.0.0.1:8123"),
        ("http://127.0.0.1:8123/", "http://127.0.0.1:8123"),
        ("http://localhost:8123", "http://localhost:8123"),
        ("http://[::1]:8123", "http://[::1]:8123"),
        ("https://evil.example", DEFAULT_BASE_URL),
        ("http://127.0.0.1.evil.example", DEFAULT_BASE_URL),
        ("ftp://127.0.0.1", DEFAULT_BASE_URL),
        ("", DEFAULT_BASE_URL),
        ("   ", DEFAULT_BASE_URL),
    ],
)
def test_the_base_url_override_is_honoured_only_for_loopback(override: str, expected: str) -> None:
    assert resolve_base_url({"JEV_JUDGE_BASE_URL": override}) == expected


def test_an_absent_base_url_override_is_the_default() -> None:
    assert resolve_base_url({}) == DEFAULT_BASE_URL
