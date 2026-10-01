"""File adapters: items, questions and rows read from and written to disk."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from btx_jev_judge.adapters.files import load_items, load_questions, read_rows, write_rows
from btx_jev_judge.domain import Answer, InputError, QuestionType, Row

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _row(row_id: str, *, ok: bool = True) -> Row:
    if ok:
        return Row(id=row_id, ok=True, answers={"q": Answer(type=QuestionType.NOUL, value=0.5)})
    return Row(id=row_id, ok=False, reason="x")


def test_load_items_accepts_int_and_string_ids_and_skips_blank_lines(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n\n{"id": "x", "state": {"t": "b"}}\n')
    assert [(i.id, i.state) for i in load_items(p)] == [("1", {"t": "a"}), ("x", {"t": "b"})]


def test_load_items_refuses_a_duplicate_id_naming_the_line(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n{"id": "1", "state": {"t": "b"}}\n')
    with pytest.raises(InputError, match="line 2: duplicate id '1'"):
        load_items(p)


def test_load_items_refuses_an_empty_state_naming_the_field(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {}}\n')
    with pytest.raises(InputError, match=r"line 1: state: "):
        load_items(p)


def test_load_items_refuses_invalid_json_naming_the_line(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}}\n{oops\n')
    with pytest.raises(InputError, match="line 2: not JSON"):
        load_items(p)


def test_load_items_refuses_a_file_without_items(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", "\n\n")
    with pytest.raises(InputError, match="no items"):
        load_items(p)


def test_load_items_refuses_an_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="cannot read"):
        load_items(tmp_path / "missing.jsonl")


def test_load_items_refuses_an_unknown_field(tmp_path: Path) -> None:
    p = _write(tmp_path, "i.jsonl", '{"id": 1, "state": {"t": "a"}, "extra": 1}\n')
    with pytest.raises(InputError, match="line 1: extra"):
        load_items(p)


def test_load_questions_reads_a_valid_file(tmp_path: Path) -> None:
    p = _write(tmp_path, "q.json", json.dumps([{"id": "d", "type": "noul", "instructions": "yes?"}]))
    assert [q.id for q in load_questions(p)] == ["d"]


def test_load_questions_refuses_a_one_option_choice(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "q.json",
        json.dumps([{"id": "k", "type": "choice", "instructions": "pick", "criteria": {"one": "x"}}]),
    )
    with pytest.raises(InputError, match="criteria"):
        load_questions(p)


def test_load_questions_names_the_file_in_a_refusal(tmp_path: Path) -> None:
    p = _write(tmp_path, "q.json", "[]")
    with pytest.raises(InputError, match=r"q\.json: questions: need a non-empty JSON list"):
        load_questions(p)


def test_load_questions_refuses_invalid_json(tmp_path: Path) -> None:
    p = _write(tmp_path, "q.json", "{oops")
    with pytest.raises(InputError, match=r"q\.json: not JSON"):
        load_questions(p)


def test_load_questions_refuses_an_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="cannot read"):
        load_questions(tmp_path / "missing.json")


def test_write_rows_then_read_rows_round_trips_in_order(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [_row("a"), _row("b", ok=False)]
    assert write_rows(path, iter(rows)) == rows
    assert read_rows(path) == rows


def test_write_rows_streams_each_row_before_the_next_is_drawn(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    lines_seen: list[int] = []

    def rows() -> Iterator[Row]:
        yield _row("a")
        # Only a flushed first row is visible here, which is what keeps paid work after an interrupt.
        lines_seen.append(path.read_text(encoding="utf-8").count("\n"))
        yield _row("b")

    assert [r.id for r in write_rows(path, rows())] == ["a", "b"]
    assert lines_seen == [1]


def test_write_rows_reports_progress_every_hundred_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_rows(tmp_path / "rows.jsonl", (_row(str(n)) for n in range(250)))
    assert capsys.readouterr().err.splitlines() == [
        "jev-judge: 100 rows written",
        "jev-judge: 200 rows written",
    ]


def test_write_rows_refuses_an_unwritable_path(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="cannot write"):
        write_rows(tmp_path / "no-such-dir" / "rows.jsonl", [_row("a")])


def test_read_rows_skips_blank_lines(tmp_path: Path) -> None:
    p = _write(tmp_path, "r.jsonl", _row("a").model_dump_json() + "\n\n" + _row("b").model_dump_json() + "\n")
    assert [r.id for r in read_rows(p)] == ["a", "b"]


def test_read_rows_names_the_line_of_a_bad_row(tmp_path: Path) -> None:
    p = _write(tmp_path, "r.jsonl", _row("a").model_dump_json() + '\n{"id": 1}\n')
    with pytest.raises(InputError, match=r"r\.jsonl line 2: "):
        read_rows(p)


def test_read_rows_refuses_an_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="cannot read"):
        read_rows(tmp_path / "missing.jsonl")
