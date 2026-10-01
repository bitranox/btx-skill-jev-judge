"""The judge use case: redact each item's state, ask the client, collect one row per item.

System Role:
    Depends only on the domain and the :class:`~btx_jev_judge.application.ports.JudgeClient` port;
    the HTTP adapter that implements the port is wired in by the composition root.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..domain.models import Row
from ..domain.redaction import DEFAULT_CAP, prepare_state

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from ..domain.models import Item, Outcome, Question
    from .ports import JudgeClient


@dataclass(frozen=True)
class JudgeSettings:
    """What the use case itself needs; rate, retries and timeout belong to the client.

    Attributes:
        workers: Items judged concurrently.
        cap: Longest string, in characters, that is sent.
    """

    workers: int = 8
    cap: int = DEFAULT_CAP


def _row(item: Item, outcome: Outcome, redactions: int) -> Row:
    return Row(
        id=item.id,
        ok=outcome.answers is not None,
        answers=outcome.answers or {},
        reason=outcome.reason,
        redactions=redactions,
        attempts=outcome.attempts,
        latency_ms=outcome.latency_ms,
        input_tokens=outcome.input_tokens,
        model=outcome.model,
    )


def iter_judged(
    items: Sequence[Item],
    questions: Sequence[Question],
    *,
    client: JudgeClient,
    key: str | None,
    settings: JudgeSettings,
) -> Iterator[Row]:
    """Yield rows in input order as each is ready, so a caller can write as it goes.

    Args:
        items: What to judge.
        questions: Asked about every item, in one request per item.
        client: The judge, behind its port.
        key: The API key, redacted from every state as a literal.
        settings: Worker count and per-string cap.

    Yields:
        One row per item, in input order; a failed item is a row with its reason.
    """

    def one(item: Item) -> Row:
        state, redactions = prepare_state(item.state, key=key, cap=settings.cap)
        return _row(item, client.ask(state, questions), redactions)

    with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
        yield from pool.map(one, items)


def judge_all(
    items: Sequence[Item],
    questions: Sequence[Question],
    *,
    client: JudgeClient,
    key: str | None,
    settings: JudgeSettings,
) -> list[Row]:
    """Judge every item and return the rows in input order.

    Args:
        items: What to judge.
        questions: Asked about every item, in one request per item.
        client: The judge, behind its port.
        key: The API key, redacted from every state as a literal.
        settings: Worker count and per-string cap.

    Returns:
        One row per item; a failed item is a row with ``ok`` False and its reason.
    """
    return list(iter_judged(items, questions, client=client, key=key, settings=settings))


__all__ = ["JudgeSettings", "iter_judged", "judge_all"]
