"""The CLI: run, summarize, check-key - exit codes, envelopes, and what reaches stdout."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import jev_judge as jj
import pytest
from conftest import JevStub

KEY = "tk_" + "c" * 40
QUESTION = {"id": "dup", "type": "noul", "instructions": "Is `title` a duplicate?"}


def _noul(value: float) -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 100},
        "answers": {"dup": {"type": "noul", "noul": value}},
    }


def _files(tmp_path: Path, items: list[dict[str, Any]]) -> tuple[Path, Path]:
    items_path, questions_path = tmp_path / "items.jsonl", tmp_path / "q.json"
    items_path.write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    questions_path.write_text(json.dumps([QUESTION]), encoding="utf-8")
    return items_path, questions_path


def _env(stub: JevStub) -> dict[str, str]:
    return {"TYPESAFE_API_KEY": KEY, "JEV_JUDGE_BASE_URL": stub.url}


def _main(argv: list[str], env: dict[str, str], home: Path) -> tuple[int, str]:
    out = io.StringIO()
    code = jj.main(argv, env=env, home=home, stdout=out, sleep=lambda _s: None)
    return code, out.getvalue()


def _run(stub: JevStub, tmp_path: Path, items: list[dict[str, Any]], *extra: str) -> tuple[int, dict[str, Any], Path]:
    items_path, questions_path = _files(tmp_path, items)
    out = tmp_path / "rows.jsonl"
    code, text = _main(
        [
            "run",
            "--items",
            str(items_path),
            "--questions",
            str(questions_path),
            "--out",
            str(out),
            "--rate",
            "1000",
            "--json",
            *extra,
        ],
        _env(stub),
        tmp_path,
    )
    return code, json.loads(text), out


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- run -----------------------------------------------------------------------------------------


def test_run_writes_one_row_per_item_and_exits_0(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.9 if "dup" in body["state"]["title"] else 0.1), {})
    code, envelope, out = _run(
        jev, tmp_path, [{"id": 1, "state": {"title": "dup"}}, {"id": 2, "state": {"title": "new"}}]
    )
    assert code == 0 and envelope["ok"] is True and envelope["command"] == "run"
    assert envelope["data"]["answered"] == 2 and envelope["data"]["input_tokens"] == 200
    assert [r["answers"]["dup"]["value"] for r in _rows(out)] == [0.9, 0.1]


def test_run_exits_1_and_names_the_failed_row(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (
        (422, {"detail": "no"}, {}) if "bad" in body["state"]["title"] else (200, _noul(0.3), {})
    )
    code, envelope, out = _run(
        jev, tmp_path, [{"id": "fine", "state": {"title": "ok"}}, {"id": "broken", "state": {"title": "bad"}}]
    )
    assert code == 1 and envelope["ok"] is False
    assert envelope["data"]["failed"] == ["broken"]
    assert [r["ok"] for r in _rows(out)] == [True, False]


def test_pilot_judges_the_first_n_and_lists_the_rest_as_skipped(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    code, envelope, out = _run(
        jev, tmp_path, [{"id": i, "state": {"title": f"t{i}"}} for i in range(5)], "--pilot", "2"
    )
    assert code == 0 and envelope["data"]["rows"] == 2
    assert envelope["skipped"] == ["2", "3", "4"] and len(jev.seen) == 2
    assert len(_rows(out)) == 2


def test_run_without_a_key_exits_2_and_json_bare_still_prints_json(tmp_path: Path) -> None:
    items_path, questions_path = _files(tmp_path, [{"id": 1, "state": {"title": "x"}}])
    code, text = _main(
        [
            "run",
            "--items",
            str(items_path),
            "--questions",
            str(questions_path),
            "--out",
            str(tmp_path / "r.jsonl"),
            "--json-bare",
        ],
        {},
        tmp_path,
    )
    assert code == 2 and "TYPESAFE_API_KEY" in json.loads(text)["error"]


def test_a_bad_question_file_exits_2_with_the_reason_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    items_path, questions_path = _files(tmp_path, [{"id": 1, "state": {"title": "x"}}])
    questions_path.write_text('[{"id": "k", "type": "choice", "instructions": "x"}]', encoding="utf-8")
    code, text = _main(
        [
            "run",
            "--items",
            str(items_path),
            "--questions",
            str(questions_path),
            "--out",
            str(tmp_path / "r.jsonl"),
        ],
        {"TYPESAFE_API_KEY": KEY},
        tmp_path,
    )
    assert code == 2 and text == ""
    assert "criteria" in capsys.readouterr().err


def test_human_output_reports_coverage_and_cost(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    items_path, questions_path = _files(tmp_path, [{"id": 1, "state": {"title": "x"}}])
    code, text = _main(
        [
            "run",
            "--items",
            str(items_path),
            "--questions",
            str(questions_path),
            "--out",
            str(tmp_path / "r.jsonl"),
            "--rate",
            "1000",
        ],
        _env(jev),
        tmp_path,
    )
    assert code == 0 and "answered 1 of 1" in text and "$" in text


# --- check-key -----------------------------------------------------------------------------------


def test_check_key_reports_presence_and_never_prints_the_key(tmp_path: Path) -> None:
    code, text = _main(["check-key", "--json"], {"TYPESAFE_API_KEY": KEY}, tmp_path)
    assert code == 0 and KEY not in text
    assert json.loads(text)["data"] == {"present": True, "source": "env"}


def test_check_key_exits_1_when_there_is_none(tmp_path: Path) -> None:
    code, text = _main(["check-key", "--json"], {}, tmp_path)
    assert code == 1 and json.loads(text)["data"]["present"] is False


# --- summarize -----------------------------------------------------------------------------------


def _row(item_id: str, value: float | str, qtype: str = "noul", confidence: float | None = None) -> jj.Row:
    return jj.Row(
        id=item_id,
        ok=True,
        answers={"q": jj.Answer(type=jj.QuestionType(qtype), value=value, confidence=confidence)},
    )


def test_summarize_flags_a_noul_that_never_moves() -> None:
    summary = jj.summarize([_row(str(i), 0.5) for i in range(12)])
    assert summary["flat"] == ["q"]


def test_summarize_passes_a_noul_that_separates_and_lists_the_middle_band() -> None:
    rows = [_row(f"lo{i}", 0.05) for i in range(6)] + [_row(f"hi{i}", 0.95) for i in range(6)] + [_row("mid", 0.5)]
    summary = jj.summarize(rows)
    assert summary["flat"] == []
    assert summary["questions"]["q"]["uncertain"] == ["mid"]


def test_summarize_lists_low_confidence_choices_as_uncertain() -> None:
    rows = [_row(str(i), "a" if i % 2 else "b", "choice", 0.9) for i in range(10)]
    rows.append(_row("unsure", "a", "choice", 0.3))
    summary = jj.summarize(rows)
    assert summary["flat"] == [] and summary["questions"]["q"]["uncertain"] == ["unsure"]
    assert summary["questions"]["q"]["counts"] == {"a": 6, "b": 5}


def test_summarize_does_not_call_a_handful_of_rows_flat() -> None:
    assert jj.summarize([_row(str(i), 0.5) for i in range(3)])["flat"] == []


def test_summarize_cli_exits_1_on_a_flat_choice(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text(
        "".join(_row(str(i), "same", "choice", 0.9).model_dump_json() + "\n" for i in range(10)),
        encoding="utf-8",
    )
    code, text = _main(["summarize", "--rows", str(path), "--json"], {}, tmp_path)
    assert code == 1 and json.loads(text)["data"]["flat"] == ["q"]


def test_summarize_cli_counts_failed_rows(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [_row("a", 0.1), jj.Row(id="b", ok=False, reason="http 401")]
    path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    code, text = _main(["summarize", "--rows", str(path), "--json"], {}, tmp_path)
    data = json.loads(text)["data"]
    assert code == 0 and data["failed"] == ["b"] and data["answered"] == 1
