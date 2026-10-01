"""Summary: distribution per question, rows worth reading, and questions that look flat."""

from __future__ import annotations

from btx_skill_jev_judge.domain.enums import QuestionType
from btx_skill_jev_judge.domain.models import Answer, Row
from btx_skill_jev_judge.domain.summary import summarize


def _row(
    item_id: str, value: float | str, qtype: QuestionType = QuestionType.NOUL, confidence: float | None = None
) -> Row:
    return Row(
        id=item_id,
        ok=True,
        answers={"q": Answer(type=qtype, value=value, confidence=confidence)},
    )


def test_summarize_flags_a_noul_that_never_moves() -> None:
    summary = summarize([_row(str(i), 0.5) for i in range(12)])
    assert summary["flat"] == ["q"]


def test_summarize_passes_a_noul_that_separates_and_lists_the_middle_band() -> None:
    rows = [_row(f"lo{i}", 0.05) for i in range(6)] + [_row(f"hi{i}", 0.95) for i in range(6)] + [_row("mid", 0.5)]
    summary = summarize(rows)
    assert summary["flat"] == []
    assert summary["questions"]["q"]["uncertain"] == ["mid"]


def test_summarize_lists_low_confidence_choices_as_uncertain() -> None:
    rows = [_row(str(i), "a" if i % 2 else "b", QuestionType.CHOICE, 0.9) for i in range(10)]
    rows.append(_row("unsure", "a", QuestionType.CHOICE, 0.3))
    summary = summarize(rows)
    assert summary["flat"] == [] and summary["questions"]["q"]["uncertain"] == ["unsure"]
    assert summary["questions"]["q"]["counts"] == {"a": 6, "b": 5}


def test_summarize_does_not_call_a_handful_of_rows_flat() -> None:
    assert summarize([_row(str(i), 0.5) for i in range(3)])["flat"] == []


def test_summarize_flags_a_choice_that_always_answers_the_same() -> None:
    assert summarize([_row(str(i), "a", QuestionType.CHOICE, 0.9) for i in range(12)])["flat"] == ["q"]


def test_summarize_counts_failed_rows_without_describing_them() -> None:
    rows = [_row(str(i), 0.1 * i) for i in range(3)] + [Row(id="bad", ok=False, reason="boom")]
    summary = summarize(rows)
    assert (summary["rows"], summary["answered"], summary["failed"]) == (4, 3, ["bad"])
