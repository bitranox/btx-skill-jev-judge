"""The judge commands: ``run``, ``summarize`` and ``check-key``.

The commands are thin: each reads its options, asks the use case or a file adapter for the work,
and hands one :class:`~.judge_output.CommandResult` to the renderer. Failures are mapped here and
nowhere else: :class:`InputError` is exit 2 with one ``jev-judge: <reason>`` line on stderr,
:class:`ConfigurationError` is exit 78 with one ``Error: <reason>`` line (the line every other
configuration failure of this CLI prints), and ``--json-bare`` still prints JSON.

A setting comes from the command line when the flag is given, else from the layered
configuration, else from the model's default.

Contents:
    * :func:`cli_run` - judge items and write one row per item
    * :func:`cli_summarize` - distribution, uncertain rows and flat questions of a run
    * :func:`cli_check_key` - is a usable key configured (never prints it)
"""

from __future__ import annotations

import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import rich_click as click
from pydantic import ValidationError

from btx_jev_judge.adapters.config.judge_settings import RunConfig, SummaryConfig, run_config, summary_config
from btx_jev_judge.adapters.files import load_items, load_questions, read_rows, write_rows
from btx_jev_judge.application.judge import JudgeSettings, iter_judged
from btx_jev_judge.domain.errors import ConfigurationError, InputError
from btx_jev_judge.domain.summary import PRICE_PER_MTOK, summarize

from .. import safe_console
from ..config_load import echo_load_traceback
from ..constants import CLICK_CONTEXT_SETTINGS
from ..context import CLIContext, get_cli_context
from ..exit_codes import ExitCode
from ..typed_click import option
from .judge_output import USAGE_EXIT, CommandResult, Output, emit, failed

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from lib_layered_config import Config

    from btx_jev_judge.domain.models import Row

#: Where the key is looked for, named in the "no usable key" message.
_KEY_HINT = "set TYPESAFE_API_KEY, or put the key in ~/.credentials/typesafe.key with mode 600"


def _output(as_json: bool, as_json_bare: bool) -> Output:
    """Combine the two output flags, refusing both at once.

    Args:
        as_json: ``--json`` was given.
        as_json_bare: ``--json-bare`` was given.

    Returns:
        The requested rendering.

    Raises:
        click.UsageError: Both flags were given.
    """
    if as_json and as_json_bare:
        raise click.UsageError("--json and --json-bare cannot be combined")
    return Output(as_json=as_json, as_json_bare=as_json_bare)


def _report(code: int, error: Exception, *, prefix: str) -> CommandResult:
    """Put one diagnostic line on stderr and describe the failure as a result."""
    message = str(error)
    safe_console.echo(f"{prefix}: {message}", err=True)
    return failed(code, message)


def _finish(ctx: click.Context, *, command: str, output: Output, work: Callable[[], CommandResult]) -> None:
    """Run a command's work, map its failures to exit codes, print the result and exit.

    Args:
        ctx: The command's click context; the exit goes through it.
        command: The command name, echoed in the envelope.
        output: The requested rendering.
        work: The command body.

    Raises:
        click.exceptions.Exit: Always, carrying the result's exit code.
    """
    try:
        result = work()
    except InputError as exc:
        result = _report(USAGE_EXIT, exc, prefix="jev-judge")
    except ConfigurationError as exc:
        # "Error:" is the line every other configuration failure of this CLI prints.
        result = _report(ExitCode.CONFIG_ERROR, exc, prefix="Error")
    emit(command, result, output)
    ctx.exit(result.code)


def _loaded_config(cli_ctx: CLIContext) -> Config:
    """The configuration the root loaded.

    Args:
        cli_ctx: The state the root group stored.

    Returns:
        The loaded configuration.

    Raises:
        ConfigurationError: The root could not load it; the loader's reason is the message.
    """
    if cli_ctx.config_error is not None:
        echo_load_traceback(cli_ctx.config_error, show_traceback=cli_ctx.traceback)
        raise ConfigurationError(str(cli_ctx.config_error)) from cli_ctx.config_error
    return cli_ctx.config


def _key(cli_ctx: CLIContext) -> str:
    """The API key, or an :class:`InputError` saying where to put one.

    Args:
        cli_ctx: The state the root group stored.

    Returns:
        The key. It is never printed, logged or put on a command line.

    Raises:
        InputError: No usable key; the message names the reason, never the key.
    """
    key, why = cli_ctx.services.load_key()
    if key is None:
        raise InputError(f"no usable Jev key ({why}): {_KEY_HINT}")
    return key


@dataclass(frozen=True)
class _RunOptions:
    """The ``run`` command's options; ``overrides`` holds only the flags that were given."""

    items: Path
    questions: Path
    out: Path
    pilot: int
    overrides: Mapping[str, float | int | str]


def _flag_error(error: ValidationError, flags: Mapping[str, str], *, otherwise: str) -> InputError:
    """One ``<flag>: <reason>`` per problem, so the message names what the user typed.

    Args:
        error: The validation error of the merged settings.
        flags: Flag name by model field name.
        otherwise: The flag blamed for a problem that belongs to no single field (a band whose
            edges are out of order).

    Returns:
        The error to raise; the offending value is never part of the message.
    """
    parts: list[str] = []
    for problem in error.errors(include_input=False):
        field = str(problem["loc"][0]) if problem["loc"] else ""
        parts.append(f"{flags.get(field, otherwise)}: {problem['msg']}")
    return InputError("; ".join(parts))


_RUN_FLAGS = {name: f"--{name}" for name in RunConfig.model_fields}
_SUMMARY_FLAGS = {"band_low": "--band", "band_high": "--band", "min_confidence": "--min-confidence"}


def _effective_settings(base: RunConfig, overrides: Mapping[str, float | int | str]) -> RunConfig:
    """Apply the flags that were given on top of the configured settings, validated.

    Args:
        base: Settings from the configuration (or its defaults).
        overrides: Flag values by field name.

    Returns:
        The settings the run uses.

    Raises:
        InputError: A flag is out of range; the message names the flag.
    """
    try:
        return RunConfig.model_validate({**base.model_dump(), **overrides})
    except ValidationError as exc:
        raise _flag_error(exc, _RUN_FLAGS, otherwise="value") from exc


def _run_data(rows_out: Path, rows: list[Row], seconds: float) -> dict[str, Any]:
    """The ``run`` data: coverage, failures, cost and timing.

    Args:
        rows_out: Where the rows were written.
        rows: The rows written.
        seconds: How long the run took.

    Returns:
        The data of the envelope.
    """
    failed_ids = [r.id for r in rows if not r.ok]
    tokens = sum(r.input_tokens for r in rows)
    return {
        "rows": len(rows),
        "answered": len(rows) - len(failed_ids),
        "failed": failed_ids,
        "out": str(rows_out),
        "input_tokens": tokens,
        "cost_usd": round(tokens * PRICE_PER_MTOK / 1_000_000, 6),
        "redactions": sum(r.redactions for r in rows),
        "models": sorted({r.model for r in rows if r.model}),
        "seconds": round(seconds, 2),
    }


def _run(cli_ctx: CLIContext, opts: _RunOptions) -> CommandResult:
    """Judge the items and write the rows as they arrive.

    Args:
        cli_ctx: The state the root group stored.
        opts: The command's options.

    Returns:
        Exit 1 when any row failed, else 0; the ids a pilot did not judge are ``skipped``.
    """
    settings = _effective_settings(run_config(_loaded_config(cli_ctx)), opts.overrides)
    key = _key(cli_ctx)
    items, questions = load_items(opts.items), load_questions(opts.questions)
    pilot = opts.pilot if opts.pilot > 0 else len(items)
    judge = JudgeSettings(workers=settings.workers, cap=settings.cap)
    started = time.monotonic()
    # The generator is the second context so it closes first: a write failure must not leave queued
    # judging running against a client whose connection pool is already gone.
    with (
        cli_ctx.services.make_client(key, settings) as client,
        closing(iter_judged(items[:pilot], questions, client=client, key=key, settings=judge)) as judged,
    ):
        rows = write_rows(opts.out, judged)
    data = _run_data(opts.out, rows, time.monotonic() - started)
    return CommandResult(code=1 if data["failed"] else 0, data=data, skipped=[item.id for item in items[pilot:]])


@click.command("run", context_settings=CLICK_CONTEXT_SETTINGS)
@option("--items", required=True, type=click.Path(path_type=Path), help='JSONL: {"id": ..., "state": {...}}')
@option("--questions", required=True, type=click.Path(path_type=Path), help="JSON list of questions")
@option("--out", required=True, type=click.Path(path_type=Path), help="JSONL rows, written as they arrive")
@option("--pilot", type=int, default=0, help="judge only the first N items")
@option("--rate", type=float, default=None, help="requests per second (config: judge.rate)")
@option("--workers", type=int, default=None, help="items judged concurrently (config: judge.workers)")
@option("--attempts", type=int, default=None, help="tries per judgment (config: judge.attempts)")
@option("--cap", type=int, default=None, help="max characters per string (config: judge.cap)")
@option("--timeout", type=float, default=None, help="seconds per request (config: judge.timeout)")
@option("--model", default=None, help="jev-latest, or a pinned jev-x.y.z (config: judge.model)")
@option("--json", "as_json", is_flag=True, help="{ok, command, data, skipped}")
@option("--json-bare", "as_json_bare", is_flag=True, help="data only, also on failure")
@click.pass_context
def cli_run(
    ctx: click.Context,
    *,
    items: Path,
    questions: Path,
    out: Path,
    pilot: int,
    rate: float | None,
    workers: int | None,
    attempts: int | None,
    cap: int | None,
    timeout: float | None,
    model: str | None,
    as_json: bool,
    as_json_bare: bool,
) -> None:
    """Judge every item; one row per item is written to --out.

    A flag left out falls back to the configuration (the judge section), then to the default.

    Exit 0 when every item was answered, 1 when some failed, 2 on a usage or input error,
    78 on a configuration error.
    """
    output = _output(as_json, as_json_bare)
    given = {
        "rate": rate,
        "workers": workers,
        "attempts": attempts,
        "cap": cap,
        "timeout": timeout,
        "model": model,
    }
    opts = _RunOptions(
        items=items,
        questions=questions,
        out=out,
        pilot=pilot,
        overrides=MappingProxyType({name: value for name, value in given.items() if value is not None}),
    )
    cli_ctx = get_cli_context(ctx)
    _finish(ctx, command="run", output=output, work=lambda: _run(cli_ctx, opts))


def _effective_summary(
    base: SummaryConfig, *, band: tuple[float, float] | None, min_confidence: float | None
) -> SummaryConfig:
    """Apply the summarize flags that were given on top of the configured settings, validated.

    Args:
        base: Settings from the configuration (or its defaults).
        band: ``--band`` low and high, or None.
        min_confidence: ``--min-confidence``, or None.

    Returns:
        The settings the summary uses.

    Raises:
        InputError: A flag is out of range or the band is not ordered; the message names the flag.
    """
    overrides: dict[str, float] = {}
    if band is not None:
        overrides["band_low"], overrides["band_high"] = band
    if min_confidence is not None:
        overrides["min_confidence"] = min_confidence
    try:
        return SummaryConfig.model_validate({**base.model_dump(), **overrides})
    except ValidationError as exc:
        raise _flag_error(exc, _SUMMARY_FLAGS, otherwise="--band") from exc


def _summarize(
    cli_ctx: CLIContext, *, rows_path: Path, band: tuple[float, float] | None, min_confidence: float | None
) -> CommandResult:
    """Summarize a rows file with the flags that were given, else the configured settings.

    Args:
        cli_ctx: The state the root group stored.
        rows_path: The JSONL rows written by ``run``.
        band: ``--band`` low and high, or None to use the configuration.
        min_confidence: ``--min-confidence``, or None to use the configuration.

    Returns:
        Exit 1 when any question looks flat, else 0.

    Raises:
        InputError: A flag is out of range, or the rows file is unreadable.
    """
    settings = _effective_summary(summary_config(_loaded_config(cli_ctx)), band=band, min_confidence=min_confidence)
    summary = summarize(
        read_rows(rows_path),
        band=(settings.band_low, settings.band_high),
        min_confidence=settings.min_confidence,
    )
    return CommandResult(code=1 if summary["flat"] else 0, data=summary)


@click.command("summarize", context_settings=CLICK_CONTEXT_SETTINGS)
@option("--rows", required=True, type=click.Path(path_type=Path), help="JSONL rows written by run")
@option(
    "--band",
    type=float,
    nargs=2,
    default=None,
    metavar="LOW HIGH",
    help="a noul strictly between is uncertain (config: summary.band_low, summary.band_high)",
)
@option(
    "--min-confidence",
    "min_confidence",
    type=float,
    default=None,
    help="a choice or score below this is uncertain (config: summary.min_confidence)",
)
@option("--json", "as_json", is_flag=True, help="{ok, command, data, skipped}")
@option("--json-bare", "as_json_bare", is_flag=True, help="data only, also on failure")
@click.pass_context
def cli_summarize(
    ctx: click.Context,
    *,
    rows: Path,
    band: tuple[float, float] | None,
    min_confidence: float | None,
    as_json: bool,
    as_json_bare: bool,
) -> None:
    """Distribution, uncertain rows and flat questions of a run.

    Exit 0 when no question looks flat, 1 when one does, 2 on an unreadable or malformed rows
    file, 78 on a configuration error.
    """
    output = _output(as_json, as_json_bare)
    cli_ctx = get_cli_context(ctx)
    _finish(
        ctx,
        command="summarize",
        output=output,
        work=lambda: _summarize(cli_ctx, rows_path=rows, band=band, min_confidence=min_confidence),
    )


def _check_key(cli_ctx: CLIContext) -> CommandResult:
    """Say whether a usable key is configured, and where it came from; never the key itself."""
    key, why = cli_ctx.services.load_key()
    if key is None:
        return CommandResult(code=1, data={"present": False, "reason": why})
    return CommandResult(code=0, data={"present": True, "source": why})


@click.command("check-key", context_settings=CLICK_CONTEXT_SETTINGS)
@option("--json", "as_json", is_flag=True, help="{ok, command, data, skipped}")
@option("--json-bare", "as_json_bare", is_flag=True, help="data only, also on failure")
@click.pass_context
def cli_check_key(ctx: click.Context, as_json: bool, as_json_bare: bool) -> None:
    """Is a usable key configured? Prints where it was found, never the key.

    Exit 0 when a key is present, 1 when none is. It does not read the configuration, so it
    works while a configuration file is broken.
    """
    output = _output(as_json, as_json_bare)
    cli_ctx = get_cli_context(ctx)
    _finish(ctx, command="check-key", output=output, work=lambda: _check_key(cli_ctx))


__all__ = ["cli_check_key", "cli_run", "cli_summarize"]
