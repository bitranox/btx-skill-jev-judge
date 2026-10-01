"""The judge use case: order, failure rows, redaction before the port, accounting."""

from __future__ import annotations

import inspect
import threading
import time
from typing import TYPE_CHECKING

from btx_skill_jev_judge.application.judge import JudgeSettings, iter_judged, judge_all
from btx_skill_jev_judge.domain.enums import QuestionType
from btx_skill_jev_judge.domain.models import Answer, Item, Outcome, parse_questions

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic import JsonValue

    from btx_skill_jev_judge.domain.models import Question

KEY = "tk_" + "a" * 40
GITHUB_TOKEN = "ghp_" + "B" * 36
QUESTIONS = parse_questions([{"id": "q", "type": "noul", "instructions": "Is it?"}])
ANSWER = Answer(type=QuestionType.NOUL, value=0.5, confidence=0.9)
SLOWEST_FIRST_MS = 5


class FakeClient:
    """A real JudgeClient: records each state it is asked about, answers from a script.

    The client sees only the state, so it identifies an item by the state's ``id`` (``"0"``,
    ``"1"``, ...), not by the row id ``_items`` gives it (``"i0"``, ``"i1"``, ...).
    """

    def __init__(self, fail_ids: frozenset[str] = frozenset(), *, slow_first_of: int = 0) -> None:
        self.states: list[Mapping[str, JsonValue]] = []
        self._lock = threading.Lock()
        self._fail_ids = fail_ids
        self._slow_first_of = slow_first_of

    def ask(self, state: Mapping[str, JsonValue], questions: Sequence[Question]) -> Outcome:
        """Record the state, then answer or fail as scripted."""
        item_id = str(state["id"])
        if self._slow_first_of:
            # Earlier items answer later, so rows arriving in input order prove the reordering.
            time.sleep(SLOWEST_FIRST_MS / 1000 * (self._slow_first_of - int(item_id)))
        with self._lock:
            self.states.append(state)
        if item_id in self._fail_ids:
            return Outcome(answers=None, reason="x", attempts=2)
        return Outcome(answers={"q": ANSWER}, reason=None, attempts=3, latency_ms=12, input_tokens=34, model="m1")


def _items(n: int) -> list[Item]:
    return [Item(id=f"i{i}", state={"id": str(i), "title": "t"}) for i in range(n)]


def test_rows_keep_input_order_with_several_workers() -> None:
    client = FakeClient(slow_first_of=6)
    rows = judge_all(_items(6), QUESTIONS, client=client, key=None, settings=JudgeSettings(workers=3))
    assert [r.id for r in rows] == [f"i{i}" for i in range(6)]


def test_iter_judged_is_a_generator_that_hands_over_one_row_at_a_time() -> None:
    assert inspect.isgeneratorfunction(iter_judged)
    rows = iter_judged(_items(3), QUESTIONS, client=FakeClient(), key=None, settings=JudgeSettings())
    assert next(rows).id == "i0"
    assert [r.id for r in rows] == ["i1", "i2"]


def test_zero_workers_still_judges_with_one() -> None:
    rows = judge_all(_items(2), QUESTIONS, client=FakeClient(), key=None, settings=JudgeSettings(workers=0))
    assert [r.id for r in rows] == ["i0", "i1"]


def test_a_failed_outcome_becomes_a_failed_row() -> None:
    client = FakeClient(fail_ids=frozenset({"1"}))
    ok_row, bad_row = judge_all(_items(2), QUESTIONS, client=client, key=None, settings=JudgeSettings(workers=1))
    assert ok_row.ok and ok_row.answers == {"q": ANSWER}
    assert not bad_row.ok and bad_row.reason == "x" and bad_row.answers == {}


def test_the_key_and_a_token_never_reach_the_client() -> None:
    item = Item(id="a", state={"id": "0", "note": f"{KEY} then {GITHUB_TOKEN}"})
    client = FakeClient()
    (row,) = judge_all([item], QUESTIONS, client=client, key=KEY, settings=JudgeSettings())
    sent = repr(client.states)
    assert KEY not in sent and GITHUB_TOKEN not in sent
    assert row.redactions == 2


def test_accounting_fields_are_copied_from_the_outcome() -> None:
    (row,) = judge_all(_items(1), QUESTIONS, client=FakeClient(), key=None, settings=JudgeSettings())
    assert (row.attempts, row.latency_ms, row.input_tokens, row.model) == (3, 12, 34, "m1")


def test_the_cap_is_applied_before_the_client_sees_the_state() -> None:
    item = Item(id="a", state={"id": "0", "note": "z" * 500})
    client = FakeClient()
    judge_all([item], QUESTIONS, client=client, key=None, settings=JudgeSettings(cap=50))
    note = client.states[0]["note"]
    assert isinstance(note, str) and len(note) < 500
