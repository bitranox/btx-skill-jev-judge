"""The judge commands - run, summarize, check-key: exit codes, envelopes, and what reaches stdout.

Every test drives the real root group through click's runner. The services come from
``build_testing`` with an environment pointing the real Jev client at the loopback stub, so the
whole path - options, configuration, key lookup, HTTP, rows on disk - is the production one.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import ConfigError

from btx_jev_judge.adapters.cli.root import cli
from btx_jev_judge.adapters.config.judge_settings import RunConfig
from btx_jev_judge.composition import AppServices, build_testing
from btx_jev_judge.domain.enums import QuestionType
from btx_jev_judge.domain.models import Answer, Row

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from contextlib import AbstractContextManager

    from conftest import JevStub
    from pydantic import JsonValue

    from btx_jev_judge.application.ports import JudgeClient
    from btx_jev_judge.domain.models import Outcome, Question

KEY = "tk_" + "c" * 40
QUESTION = {"id": "dup", "type": "noul", "instructions": "Is `title` a duplicate?"}

pytestmark = pytest.mark.os_agnostic


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


def _stub_env(stub: JevStub) -> dict[str, str]:
    return {"TYPESAFE_API_KEY": KEY, "JEV_JUDGE_BASE_URL": stub.url}


def _invoke(
    args: list[str],
    *,
    env: dict[str, str],
    home: Path,
    services: Callable[[], AppServices] | None = None,
) -> Result:
    factory = services or (lambda: build_testing(env=env, home=home, sleep=lambda _s: None))
    return CliRunner().invoke(cli, args, obj=factory)


def _run_args(items: Path, questions: Path, out: Path, *extra: str) -> list[str]:
    return ["run", "--items", str(items), "--questions", str(questions), "--out", str(out), *extra]


def _one_item(tmp_path: Path) -> tuple[Path, Path]:
    return _files(tmp_path, [{"id": 1, "state": {"title": "x"}}])


def _run(
    stub: JevStub, tmp_path: Path, items: list[dict[str, Any]], *extra: str
) -> tuple[Result, dict[str, Any], Path]:
    items_path, questions_path = _files(tmp_path, items)
    out = tmp_path / "rows.jsonl"
    result = _invoke(
        _run_args(items_path, questions_path, out, "--rate", "1000", "--json", *extra),
        env=_stub_env(stub),
        home=tmp_path,
    )
    return result, json.loads(result.stdout), out


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _broken_get_config(**_kwargs: object) -> Any:
    raise ConfigError("config.toml: unreadable")


# --- run -----------------------------------------------------------------------------------------


def test_run_writes_one_row_per_item_and_exits_0(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.9 if "dup" in body["state"]["title"] else 0.1), {})
    result, envelope, out = _run(
        jev, tmp_path, [{"id": 1, "state": {"title": "dup"}}, {"id": 2, "state": {"title": "new"}}]
    )
    assert result.exit_code == 0 and envelope["ok"] is True and envelope["command"] == "run"
    assert envelope["data"]["answered"] == 2 and envelope["data"]["input_tokens"] == 200
    assert envelope["skipped"] == []
    assert [r["answers"]["dup"]["value"] for r in _rows(out)] == [0.9, 0.1]


def test_run_exits_1_and_names_the_failed_row(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (
        (422, {"detail": "no"}, {}) if "bad" in body["state"]["title"] else (200, _noul(0.3), {})
    )
    result, envelope, out = _run(
        jev, tmp_path, [{"id": "fine", "state": {"title": "ok"}}, {"id": "broken", "state": {"title": "bad"}}]
    )
    assert result.exit_code == 1 and envelope["ok"] is False
    assert envelope["data"]["failed"] == ["broken"]
    assert [r["ok"] for r in _rows(out)] == [True, False]


def test_pilot_judges_the_first_n_and_lists_the_rest_as_skipped(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    result, envelope, out = _run(
        jev, tmp_path, [{"id": i, "state": {"title": f"t{i}"}} for i in range(5)], "--pilot", "2"
    )
    assert result.exit_code == 0 and envelope["data"]["rows"] == 2
    assert envelope["skipped"] == ["2", "3", "4"] and len(jev.seen) == 2
    assert len(_rows(out)) == 2


def test_run_without_a_key_exits_2_and_json_bare_still_prints_json(tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(_run_args(items_path, questions_path, tmp_path / "r.jsonl", "--json-bare"), env={}, home=tmp_path)
    assert result.exit_code == 2 and "TYPESAFE_API_KEY" in json.loads(result.stdout)["error"]
    assert "jev-judge: no usable Jev key" in result.stderr


def test_run_without_a_key_under_json_wraps_the_error_in_the_envelope(tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(_run_args(items_path, questions_path, tmp_path / "r.jsonl", "--json"), env={}, home=tmp_path)
    envelope = json.loads(result.stdout)
    assert result.exit_code == 2 and envelope["ok"] is False and envelope["command"] == "run"
    assert "error" in envelope["data"] and envelope["skipped"] == []


def test_a_bad_question_file_exits_2_with_the_reason_on_stderr(tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    questions_path.write_text('[{"id": "k", "type": "choice", "instructions": "x"}]', encoding="utf-8")
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl"), env={"TYPESAFE_API_KEY": KEY}, home=tmp_path
    )
    assert result.exit_code == 2 and result.stdout == ""
    assert "criteria" in result.stderr and "jev-judge:" in result.stderr


def test_a_missing_items_file_exits_2_with_the_reason_on_stderr(tmp_path: Path) -> None:
    _items, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(tmp_path / "nope.jsonl", questions_path, tmp_path / "r.jsonl"),
        env={"TYPESAFE_API_KEY": KEY},
        home=tmp_path,
    )
    assert result.exit_code == 2 and result.stdout == "" and "nope.jsonl" in result.stderr


def test_a_rate_of_zero_is_a_usage_error_not_a_traceback(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--rate", "0"),
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 2 and "rate" in result.stderr and "Traceback" not in result.stderr


def test_a_bad_run_flag_is_reported_by_its_flag_name(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--workers", "0"),
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 2 and "jev-judge: --workers: " in result.stderr
    assert "workers:" not in result.stderr.replace("--workers:", "")


def test_human_output_reports_coverage_and_cost(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--rate", "1000"),
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 0 and "answered 1 of 1" in result.stdout and "$" in result.stdout


def test_human_output_lists_failed_ids_and_the_pilot_remainder(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (422, {"detail": "no"}, {})
    items_path, questions_path = _files(tmp_path, [{"id": i, "state": {"title": "x"}} for i in range(3)])
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--rate", "1000", "--pilot", "1"),
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 1 and "failed: 0" in result.stdout and "pilot: 2 items not judged" in result.stdout


def test_json_and_json_bare_together_are_a_usage_error(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--json", "--json-bare"),
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 2 and jev.seen == []
    assert not (tmp_path / "r.jsonl").exists()


# --- run: configuration and flags ----------------------------------------------------------------


def test_a_config_error_exits_78_and_names_the_key(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        ["--set", "judge.rate=0", *_run_args(items_path, questions_path, tmp_path / "r.jsonl")],
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 78 and result.stdout == "" and "judge.rate" in result.stderr
    assert jev.seen == []


def test_a_config_error_under_json_bare_still_prints_json(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        ["--set", "judge.rate=0", *_run_args(items_path, questions_path, tmp_path / "r.jsonl", "--json-bare")],
        env=_stub_env(jev),
        home=tmp_path,
    )
    assert result.exit_code == 78 and "judge.rate" in json.loads(result.stdout)["error"]


def test_a_configuration_that_cannot_be_loaded_exits_78(jev: JevStub, tmp_path: Path) -> None:
    items_path, questions_path = _one_item(tmp_path)
    services = dataclasses.replace(build_testing(env=_stub_env(jev), home=tmp_path), get_config=_broken_get_config)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--json-bare"),
        env={},
        home=tmp_path,
        services=lambda: services,
    )
    assert result.exit_code == 78 and "unreadable" in json.loads(result.stdout)["error"]


class _Recording:
    """Stands in for ``make_client``: remembers each run's settings, then builds the real client."""

    def __init__(self, services: AppServices) -> None:
        self.seen: list[RunConfig] = []
        self._real = services.make_client
        self.services = dataclasses.replace(services, make_client=self)

    def __call__(self, key: str, settings: RunConfig) -> AbstractContextManager[JudgeClient]:
        self.seen.append(settings)
        return self._real(key, settings)


def _recorded_run(jev: JevStub, tmp_path: Path, *, pre: list[str], flags: list[str]) -> RunConfig:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    items_path, questions_path = _one_item(tmp_path)
    recording = _Recording(build_testing(env=_stub_env(jev), home=tmp_path, sleep=lambda _s: None))
    result = _invoke(
        [*pre, *_run_args(items_path, questions_path, tmp_path / "r.jsonl", *flags)],
        env={},
        home=tmp_path,
        services=lambda: recording.services,
    )
    assert result.exit_code == 0, result.stderr
    (settings,) = recording.seen
    return settings


def test_a_flag_beats_the_configuration(jev: JevStub, tmp_path: Path) -> None:
    settings = _recorded_run(
        jev,
        tmp_path,
        pre=["--set", "judge.workers=8"],
        flags=["--workers", "1", "--rate", "900", "--model", "jev-pin"],
    )
    assert settings.workers == 1 and settings.rate == 900.0 and settings.model == "jev-pin"


def test_the_configuration_beats_the_defaults_when_no_flag_is_given(jev: JevStub, tmp_path: Path) -> None:
    settings = _recorded_run(jev, tmp_path, pre=["--set", "judge.workers=3", "--set", "judge.rate=800"], flags=[])
    assert settings.workers == 3 and settings.rate == 800.0
    assert settings.attempts == RunConfig().attempts and settings.cap == RunConfig().cap


class _Closing:
    """Wraps a client context manager and notes that it was exited."""

    def __init__(self, inner: AbstractContextManager[JudgeClient], closed: list[bool]) -> None:
        self._inner, self._closed = inner, closed

    def __enter__(self) -> JudgeClient:
        return self._inner.__enter__()

    def __exit__(self, *exc: Any) -> bool | None:
        self._closed.append(True)
        return self._inner.__exit__(*exc)


def test_the_client_is_closed_when_the_run_ends(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = lambda body, n: (200, _noul(0.5), {})
    closed: list[bool] = []
    base = build_testing(env=_stub_env(jev), home=tmp_path, sleep=lambda _s: None)

    def make(key: str, settings: RunConfig) -> AbstractContextManager[JudgeClient]:
        return _Closing(base.make_client(key, settings), closed)

    services = dataclasses.replace(base, make_client=make)
    items_path, questions_path = _one_item(tmp_path)
    result = _invoke(
        _run_args(items_path, questions_path, tmp_path / "r.jsonl", "--rate", "1000"),
        env={},
        home=tmp_path,
        services=lambda: services,
    )
    assert result.exit_code == 0 and closed == [True]


class _Observed:
    """A client context manager that notes how many ``ask`` calls were still running when it exited."""

    def __init__(self, inner: AbstractContextManager[JudgeClient], in_flight_at_exit: list[int]) -> None:
        self._inner, self._log = inner, in_flight_at_exit
        self.in_flight = 0

    def __enter__(self) -> JudgeClient:
        return _Spy(self._inner.__enter__(), self)

    def __exit__(self, *exc: Any) -> bool | None:
        self._log.append(self.in_flight)
        return self._inner.__exit__(*exc)


class _Spy:
    """Forwards ``ask`` to the real client while counting the calls in progress."""

    def __init__(self, client: JudgeClient, observed: _Observed) -> None:
        self._client, self._observed = client, observed

    def ask(self, state: Mapping[str, JsonValue], questions: Sequence[Question]) -> Outcome:
        self._observed.in_flight += 1
        try:
            return self._client.ask(state, questions)
        finally:
            self._observed.in_flight -= 1


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="needs /dev/full, a sink whose every write fails")
def test_a_write_failure_mid_run_leaves_no_judging_in_flight_when_the_client_closes(
    jev: JevStub, tmp_path: Path
) -> None:
    def slow(body: dict[str, Any], n: int) -> tuple[int, dict[str, Any], dict[str, str]]:
        time.sleep(0.05)
        return 200, _noul(0.5), {}

    jev.reply = slow
    in_flight_at_exit: list[int] = []
    base = build_testing(env=_stub_env(jev), home=tmp_path, sleep=lambda _s: None)

    def make(key: str, settings: RunConfig) -> AbstractContextManager[JudgeClient]:
        return _Observed(base.make_client(key, settings), in_flight_at_exit)

    items_path, questions_path = _files(tmp_path, [{"id": i, "state": {"title": f"t{i}"}} for i in range(6)])
    result = _invoke(
        _run_args(items_path, questions_path, Path("/dev/full"), "--workers", "1", "--rate", "1000"),
        env={},
        home=tmp_path,
        services=lambda: dataclasses.replace(base, make_client=make),
    )
    assert result.exit_code == 2 and "cannot write" in result.stderr
    assert in_flight_at_exit == [0]


# --- check-key -----------------------------------------------------------------------------------


def test_check_key_reports_presence_and_never_prints_the_key(tmp_path: Path) -> None:
    result = _invoke(["check-key", "--json"], env={"TYPESAFE_API_KEY": KEY}, home=tmp_path)
    assert result.exit_code == 0 and KEY not in result.stdout + result.stderr
    assert json.loads(result.stdout)["data"] == {"present": True, "source": "env"}


def test_check_key_exits_1_when_there_is_none(tmp_path: Path) -> None:
    result = _invoke(["check-key", "--json"], env={}, home=tmp_path)
    assert result.exit_code == 1 and json.loads(result.stdout)["data"]["present"] is False


def test_check_key_names_the_keyfile_as_the_source_and_prints_a_human_line(tmp_path: Path) -> None:
    keyfile = tmp_path / ".credentials" / "typesafe.key"
    keyfile.parent.mkdir()
    keyfile.write_text(KEY + "\n", encoding="utf-8")
    keyfile.chmod(0o600)
    result = _invoke(["check-key"], env={}, home=tmp_path)
    assert result.exit_code == 0 and result.stdout.strip() == "key: present (keyfile)"
    assert KEY not in result.stdout + result.stderr


def test_check_key_json_bare_prints_the_data_alone(tmp_path: Path) -> None:
    result = _invoke(["check-key", "--json-bare"], env={}, home=tmp_path)
    assert result.exit_code == 1 and set(json.loads(result.stdout)) == {"present", "reason"}


def test_check_key_ignores_a_broken_configuration(tmp_path: Path) -> None:
    services = dataclasses.replace(
        build_testing(env={"TYPESAFE_API_KEY": KEY}, home=tmp_path), get_config=_broken_get_config
    )
    result = _invoke(["check-key", "--json"], env={}, home=tmp_path, services=lambda: services)
    assert result.exit_code == 0


# --- summarize -----------------------------------------------------------------------------------


def _row(item_id: str, value: float | str, qtype: str = "noul", confidence: float | None = None) -> Row:
    return Row(
        id=item_id,
        ok=True,
        answers={"q": Answer(type=QuestionType(qtype), value=value, confidence=confidence)},
    )


def _write(path: Path, rows: list[Row]) -> Path:
    path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    return path


def _summarize(tmp_path: Path, rows: list[Row], *flags: str) -> tuple[Result, dict[str, Any]]:
    path = _write(tmp_path / "rows.jsonl", rows)
    result = _invoke(["summarize", "--rows", str(path), "--json", *flags], env={}, home=tmp_path)
    return result, json.loads(result.stdout)


def test_summarize_cli_exits_1_on_a_flat_choice(tmp_path: Path) -> None:
    result, envelope = _summarize(tmp_path, [_row(str(i), "same", "choice", 0.9) for i in range(10)])
    assert result.exit_code == 1 and envelope["data"]["flat"] == ["q"] and envelope["ok"] is False


def test_summarize_cli_counts_failed_rows(tmp_path: Path) -> None:
    rows = [_row("a", 0.1), Row(id="b", ok=False, reason="http 401")]
    result, envelope = _summarize(tmp_path, rows)
    data = envelope["data"]
    assert result.exit_code == 0 and data["failed"] == ["b"] and data["answered"] == 1
    assert envelope["command"] == "summarize" and envelope["skipped"] == []


def test_summarize_band_flag_decides_which_noul_is_uncertain(tmp_path: Path) -> None:
    rows = [_row("mid", 0.5)]
    _result, default = _summarize(tmp_path, rows)
    _result, away = _summarize(tmp_path, rows, "--band", "0.6", "0.9")
    assert default["data"]["questions"]["q"]["uncertain"] == ["mid"]
    assert away["data"]["questions"]["q"]["uncertain"] == []


def test_summarize_min_confidence_flag_flags_a_weak_choice(tmp_path: Path) -> None:
    rows = [_row("a", "x", "choice", 0.7)]
    _result, default = _summarize(tmp_path, rows)
    _result, strict = _summarize(tmp_path, rows, "--min-confidence", "0.9")
    assert default["data"]["questions"]["q"]["uncertain"] == []
    assert strict["data"]["questions"]["q"]["uncertain"] == ["a"]


def test_summarize_reads_the_band_from_configuration_and_a_flag_beats_it(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("mid", 0.5)])
    base = ["--set", "summary.band_low=0.1", "--set", "summary.band_high=0.4", "summarize", "--rows", str(path)]
    configured = _invoke([*base, "--json"], env={}, home=tmp_path)
    flagged = _invoke([*base, "--json", "--band", "0.2", "0.8"], env={}, home=tmp_path)
    assert json.loads(configured.stdout)["data"]["questions"]["q"]["uncertain"] == []
    assert json.loads(flagged.stdout)["data"]["questions"]["q"]["uncertain"] == ["mid"]


def test_summarize_with_a_bad_summary_config_exits_78(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("a", 0.1)])
    result = _invoke(
        ["--set", "summary.band_low=0.9", "--set", "summary.band_high=0.1", "summarize", "--rows", str(path)],
        env={},
        home=tmp_path,
    )
    assert result.exit_code == 78 and "summary" in result.stderr and result.stdout == ""


def test_summarize_an_unordered_band_flag_exits_2_naming_the_flag(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("a", 0.1)])
    result = _invoke(["summarize", "--rows", str(path), "--band", "0.9", "0.1"], env={}, home=tmp_path)
    assert result.exit_code == 2 and result.stdout == "" and "jev-judge: --band: " in result.stderr


def test_summarize_an_out_of_range_min_confidence_exits_2_naming_the_flag(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("a", 0.1)])
    result = _invoke(["summarize", "--rows", str(path), "--min-confidence", "5"], env={}, home=tmp_path)
    assert result.exit_code == 2 and result.stdout == "" and "jev-judge: --min-confidence: " in result.stderr
    assert "min_confidence" not in result.stderr


def test_summarize_a_bad_flag_under_json_bare_still_prints_json(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("a", 0.1)])
    result = _invoke(["summarize", "--rows", str(path), "--band", "0.9", "0.1", "--json-bare"], env={}, home=tmp_path)
    assert result.exit_code == 2 and "--band" in json.loads(result.stdout)["error"]


def test_summarize_a_malformed_rows_file_exits_2_with_the_line(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"id": "a", "ok": true}\nnot json\n', encoding="utf-8")
    result = _invoke(["summarize", "--rows", str(path)], env={}, home=tmp_path)
    assert result.exit_code == 2 and "line 2" in result.stderr and result.stdout == ""


def test_summarize_human_output_lists_each_question(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row(str(i), 0.5) for i in range(12)])
    result = _invoke(["summarize", "--rows", str(path)], env={}, home=tmp_path)
    assert result.exit_code == 1
    assert "12 rows, 12 answered, 0 failed" in result.stdout and "FLAT - check the question" in result.stdout


def test_summarize_json_and_json_bare_together_are_a_usage_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "rows.jsonl", [_row("a", 0.1)])
    result = _invoke(["summarize", "--rows", str(path), "--json", "--json-bare"], env={}, home=tmp_path)
    assert result.exit_code == 2
