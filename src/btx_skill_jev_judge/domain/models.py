"""Typed shapes of the judging domain: questions, items, answers, rows and outcomes.

Questions are a discriminated union on ``type``, so a malformed one is refused with the field that
is wrong. Every model is frozen and rejects unknown fields.

Contents:
    * :class:`NoulQuestion`, :class:`ChoiceQuestion`, :class:`ScoreQuestion`, :data:`Question`
    * :class:`Item`, :class:`Answer`, :class:`Row`, :class:`Outcome`
    * :func:`parse_questions` - validate a decoded question list.
    * :func:`describe_validation_error` - one readable line per validation problem.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from .enums import QuestionType
from .errors import InputError

NonEmptyStr = Annotated[str, Field(min_length=1)]
# A rubric or instruction may be prose, or structured data the prose refers to by `name`.
Text = NonEmptyStr | dict[str, JsonValue] | list[JsonValue]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NoulCriteria(_Strict):
    """What a yes and a no mean; both optional."""

    true: Text | None = None
    false: Text | None = None


class _QuestionBase(_Strict):
    id: NonEmptyStr
    instructions: Text

    def to_api(self) -> dict[str, JsonValue]:
        """Render the question as the API expects it inside the ``questions`` map.

        Returns:
            ``{"type", "instructions"}`` plus ``"criteria"`` when the question has any.
        """
        return self.model_dump(mode="json", exclude={"id"}, exclude_none=True)


class NoulQuestion(_QuestionBase):
    """A yes/no question; the answer is the probability of yes."""

    type: Literal[QuestionType.NOUL]
    criteria: NoulCriteria | None = None


class ChoiceQuestion(_QuestionBase):
    """Pick one of 2-255 options; a None description means the key says it all."""

    type: Literal[QuestionType.CHOICE]
    criteria: Annotated[dict[str, Text | None], Field(min_length=2, max_length=255)]


class ScoreQuestion(_QuestionBase):
    """A position on 2-10 ordered levels."""

    type: Literal[QuestionType.SCORE]
    criteria: Annotated[list[Text], Field(min_length=2, max_length=10)]


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]
QUESTIONS_ADAPTER = TypeAdapter(list[Question])


class Item(_Strict):
    """One thing to judge: an id unique in its file, and the named fields Jev reads."""

    id: str
    state: Annotated[dict[str, JsonValue], Field(min_length=1)]


class Answer(_Strict):
    """One answer in one shape: noul and score carry a number, choice the chosen option."""

    type: QuestionType
    value: float | str
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


class Row(_Strict):
    """The result for one item. A failure is a row with ``ok`` False and a ``reason``."""

    id: str
    ok: bool
    answers: dict[str, Answer] = Field(default_factory=dict)
    reason: str | None = None
    redactions: int = 0
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class Outcome:
    """What one judgment produced: answers and accounting, or the reason there are none."""

    answers: dict[str, Answer] | None
    reason: str | None
    attempts: int
    latency_ms: int = 0
    input_tokens: int = 0
    model: str = ""


def describe_validation_error(error: ValidationError) -> str:
    """One ``<field>: <reason>`` per problem, instead of pydantic's internal type names.

    Args:
        error: The validation error to render.

    Returns:
        The problems joined with ``"; "``.

    Example:
        >>> try:
        ...     Item.model_validate({"id": "a", "state": {}})
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        'state: Dictionary should have at least 1 item after validation, not 0'
    """
    parts: list[str] = []
    for problem in error.errors():
        where = ".".join(str(p) for p in problem["loc"]) or "value"
        parts.append(f"{where}: {problem['msg']}")
    return "; ".join(parts)


def parse_questions(raw: object) -> list[Question]:
    """Validate a decoded question list against the shapes Jev accepts.

    Args:
        raw: The decoded JSON: a non-empty list of question objects.

    Returns:
        The typed questions, in order.

    Raises:
        InputError: The list is empty, a question is malformed, or an id repeats.

    Examples:
        >>> parse_questions([{"id": "bug", "type": "noul", "instructions": "Is `x` a bug?"}])[0].id
        'bug'
    """
    if not isinstance(raw, list) or not raw:
        raise InputError("questions: need a non-empty JSON list")
    try:
        questions = QUESTIONS_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise InputError(f"questions: {describe_validation_error(exc)}") from exc
    repeated = sorted(qid for qid, n in Counter(q.id for q in questions).items() if n > 1)
    if repeated:
        raise InputError(f"questions: duplicate question id {repeated[0]!r}")
    return questions


__all__ = [
    "QUESTIONS_ADAPTER",
    "Answer",
    "ChoiceQuestion",
    "Item",
    "NoulCriteria",
    "NoulQuestion",
    "Outcome",
    "Question",
    "Row",
    "ScoreQuestion",
    "describe_validation_error",
    "parse_questions",
]
