"""Question models: what Jev accepts, what the domain refuses, and how it says so."""

from __future__ import annotations

import pytest

from btx_skill_jev_judge.domain.enums import QuestionType
from btx_skill_jev_judge.domain.errors import InputError
from btx_skill_jev_judge.domain.models import Answer, Row, parse_questions


def test_a_one_option_choice_is_refused() -> None:
    raw = [{"id": "k", "type": "choice", "instructions": "pick", "criteria": {"one": "x"}}]
    with pytest.raises(InputError, match="criteria"):
        parse_questions(raw)


def test_an_eleven_level_score_is_refused() -> None:
    raw = [{"id": "s", "type": "score", "instructions": "rate", "criteria": [str(i) for i in range(11)]}]
    with pytest.raises(InputError, match="criteria"):
        parse_questions(raw)


def test_a_duplicate_question_id_is_refused() -> None:
    q = {"id": "d", "type": "noul", "instructions": "yes?"}
    with pytest.raises(InputError, match="duplicate question id 'd'"):
        parse_questions([q, q])


def test_an_unknown_type_is_refused() -> None:
    with pytest.raises(InputError, match="type"):
        parse_questions([{"id": "d", "type": "maybe", "instructions": "yes?"}])


@pytest.mark.parametrize("raw", [[], {}, "x", None])
def test_anything_but_a_non_empty_list_is_refused(raw: object) -> None:
    with pytest.raises(InputError, match="non-empty JSON list"):
        parse_questions(raw)


def test_structured_instructions_and_noul_criteria_are_accepted() -> None:
    q = parse_questions(
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


def test_the_api_shape_omits_the_id() -> None:
    q = parse_questions([{"id": "bug", "type": "noul", "instructions": "Is it a bug?"}])[0]
    assert q.to_api() == {"type": "noul", "instructions": "Is it a bug?"}


def test_a_row_defaults_to_no_answers_and_no_cost() -> None:
    row = Row(id="a", ok=False, reason="boom")
    assert row.answers == {} and row.attempts == 0 and row.input_tokens == 0


def test_an_answer_keeps_its_type() -> None:
    assert Answer(type=QuestionType.CHOICE, value="a").type is QuestionType.CHOICE
