"""Summary of a run: per-question distribution, rows worth reading, and flat questions.

Contents:
    * :func:`summarize` - describe a list of result rows.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import TYPE_CHECKING, Any

from .enums import QuestionType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models import Answer, Row

# A noul or score whose answers spread less than this over at least FLAT_MIN_ROWS rows is not
# telling the items apart. That is a broken question until shown otherwise, never a consensus.
FLAT_STDEV = 0.02
FLAT_MIN_ROWS = 10
DEFAULT_BAND = (0.2, 0.8)
DEFAULT_MIN_CONFIDENCE = 0.6
# USD per million input tokens for jev-1.13 (docs.typesafe.ai/models, read 2026-10-01); output
# is free. Only used for the cost line, so a stale price misreports cost, never a judgment.
PRICE_PER_MTOK = 0.042


def summarize(
    rows: Sequence[Row],
    *,
    band: tuple[float, float] = DEFAULT_BAND,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, Any]:
    """Per-question distribution, the rows worth reading by hand, and which questions look flat.

    Args:
        rows: Rows from a run; failed rows are counted, not described.
        band: A noul strictly inside ``(low, high)`` is uncertain.
        min_confidence: A choice or score below this confidence is uncertain.

    Returns:
        ``{"rows", "answered", "failed", "questions": {qid: {...}}, "flat": [qid, ...]}``.

    Examples:
        >>> summarize([])["rows"]
        0
    """
    answered = [r for r in rows if r.ok]
    per: dict[str, list[tuple[str, Answer]]] = {}
    for row in answered:
        for qid, answer in row.answers.items():
            per.setdefault(qid, []).append((row.id, answer))
    questions = {
        qid: _describe_question(pairs, band=band, min_confidence=min_confidence) for qid, pairs in sorted(per.items())
    }
    return {
        "rows": len(rows),
        "answered": len(answered),
        "failed": [r.id for r in rows if not r.ok],
        "questions": questions,
        "flat": [qid for qid, s in questions.items() if s["flat"]],
    }


def _describe_question(
    pairs: Sequence[tuple[str, Answer]], *, band: tuple[float, float], min_confidence: float
) -> dict[str, Any]:
    qtype = pairs[0][1].type
    if qtype is QuestionType.NOUL:
        uncertain = [i for i, a in pairs if band[0] < float(a.value) < band[1]]
    else:
        uncertain = [i for i, a in pairs if a.confidence is not None and a.confidence < min_confidence]
    stats = _choice_stats(pairs) if qtype is QuestionType.CHOICE else _numeric_stats(pairs)
    return {"type": qtype.value, "n": len(pairs), **stats, "uncertain": uncertain}


def _choice_stats(pairs: Sequence[tuple[str, Answer]]) -> dict[str, Any]:
    counts = dict(sorted(Counter(str(a.value) for _, a in pairs).items()))
    return {"counts": counts, "flat": len(pairs) >= FLAT_MIN_ROWS and len(counts) == 1}


def _numeric_stats(pairs: Sequence[tuple[str, Answer]]) -> dict[str, Any]:
    values = [float(a.value) for _, a in pairs]
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.fmean(values), 4),
        "stdev": round(stdev, 4),
        "flat": len(values) >= FLAT_MIN_ROWS and stdev < FLAT_STDEV,
    }


__all__ = [
    "DEFAULT_BAND",
    "DEFAULT_MIN_CONFIDENCE",
    "FLAT_MIN_ROWS",
    "FLAT_STDEV",
    "PRICE_PER_MTOK",
    "summarize",
]
