"""The Jev adapter: pooled client, retries, rate limiter, loopback-only base URL override."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import JevStub

from btx_jev_judge.adapters.jev import DEFAULT_BASE_URL, JevClient, RateLimiter, resolve_base_url
from btx_jev_judge.application.judge import JudgeSettings, judge_all
from btx_jev_judge.domain.errors import InputError
from btx_jev_judge.domain.models import Item, Question, Row, parse_questions

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


def _client(stub: JevStub, waits: list[float] | None = None, attempts: int = 4) -> JevClient:
    def sleep(seconds: float) -> None:
        if waits is not None:
            waits.append(seconds)

    return JevClient(
        key=KEY,
        base_url=stub.url,
        timeout=5.0,
        attempts=attempts,
        limiter=RateLimiter(rate=1000.0, sleep=sleep),
        sleep=sleep,
    )


def _judge(stub: JevStub, items: list[tuple[str, dict[str, Any]]], **kw: Any) -> list[Row]:
    waits = kw.pop("waits", None)
    attempts = kw.pop("attempts", 4)
    with _client(stub, waits, attempts) as client:
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


def test_a_non_positive_rate_is_refused() -> None:
    with pytest.raises(InputError, match="rate must be positive"):
        RateLimiter(rate=0.0)


def test_a_non_loopback_base_url_override_is_ignored() -> None:
    assert resolve_base_url({"JEV_JUDGE_BASE_URL": "https://evil.example"}) == DEFAULT_BASE_URL
    assert resolve_base_url({"JEV_JUDGE_BASE_URL": "http://127.0.0.1:8123"}) == "http://127.0.0.1:8123"
