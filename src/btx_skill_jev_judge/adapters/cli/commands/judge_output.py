"""What the judge commands print: the JSON envelope, the bare data, or a human line.

The shapes are the contract the ``jev-judge`` skill reads, so they do not change with the CLI
framework: ``--json`` prints ``{ok, command, data, skipped}``, ``--json-bare`` prints the data
alone (also on failure, as ``{"error": ...}``), and neither prints a human summary. Diagnostics
never go through here; they go to stderr.

Contents:
    * :class:`CommandResult` - exit code, data and skipped ids of one command
    * :func:`failed` - a result that carries only a failure message
    * :class:`Output` - which of the three renderings was asked for
    * :func:`emit` - print a result in the chosen rendering
    * :func:`human` - the human rendering of each command's data
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from .. import safe_console

#: Exit code of a usage or input/output error, as the skill documents it (0 yes, 1 no, 2 error).
USAGE_EXIT: Final = 2

#: How many ids a human line names before it says "... (+N)".
LISTED_IDS: Final = 20


@dataclass(frozen=True)
class CommandResult:
    """What a command produced.

    Attributes:
        code: The exit code.
        data: The command's data; ``{"error": message}`` when ``error`` is set.
        skipped: Item ids a pilot run did not judge.
        error: The failure message, None when the command ran.
    """

    code: int
    data: dict[str, Any]
    skipped: list[str] = field(default_factory=list[str])
    error: str | None = None


def failed(code: int, message: str) -> CommandResult:
    """A result that carries only a failure message.

    Args:
        code: The exit code.
        message: Why the command could not run.

    Returns:
        A result whose data is ``{"error": message}``.

    Example:
        >>> failed(2, "no such file").data
        {'error': 'no such file'}
    """
    return CommandResult(code=code, data={"error": message}, error=message)


@dataclass(frozen=True)
class Output:
    """The rendering a command was asked for; neither flag means human text."""

    as_json: bool = False
    as_json_bare: bool = False


def emit(command: str, result: CommandResult, output: Output) -> None:
    """Print a result on stdout in the requested rendering.

    A failure prints nothing in human mode: its reason is already on stderr.

    Args:
        command: The command name, echoed in the envelope.
        result: What the command produced.
        output: The requested rendering.
    """
    if output.as_json:
        envelope = {"ok": result.code == 0, "command": command, "data": result.data, "skipped": result.skipped}
        safe_console.echo(json.dumps(envelope))
    elif output.as_json_bare:
        safe_console.echo(json.dumps(result.data))
    elif result.error is None:
        safe_console.echo(human(command, result.data, result.skipped))


def listing(ids: list[str]) -> str:
    """Name the first :data:`LISTED_IDS` ids and count the rest.

    Args:
        ids: The ids to name.

    Returns:
        A comma-separated line.

    Example:
        >>> listing(["a", "b"])
        'a, b'
    """
    shown = ", ".join(ids[:LISTED_IDS])
    return shown + (f" ... (+{len(ids) - LISTED_IDS})" if len(ids) > LISTED_IDS else "")


def human(command: str, data: dict[str, Any], skipped: list[str]) -> str:
    """Render one command's data as text.

    Args:
        command: ``run``, ``summarize`` or ``check-key``.
        data: The command's data.
        skipped: Item ids a pilot run did not judge.

    Returns:
        The text, without a trailing newline.
    """
    if command == "check-key":
        return f"key: present ({data['source']})" if data["present"] else f"key: none ({data['reason']})"
    if command == "run":
        return _human_run(data, skipped)
    return _human_summary(data)


def _human_run(data: dict[str, Any], skipped: list[str]) -> str:
    line = (
        f"answered {data['answered']} of {data['rows']} in {data['seconds']}s; "
        f"{data['input_tokens']} input tokens (~${data['cost_usd']:.6f}); "
        f"rows in {data['out']}"
    )
    if data["failed"]:
        line += f"\nfailed: {listing(data['failed'])}"
    if skipped:
        line += f"\npilot: {len(skipped)} items not judged"
    return line


def _human_summary(data: dict[str, Any]) -> str:
    lines = [f"{data['rows']} rows, {data['answered']} answered, {len(data['failed'])} failed"]
    for qid, s in data["questions"].items():
        shape = s["counts"] if s["type"] == "choice" else f"mean {s['mean']} stdev {s['stdev']}"
        flag = "  FLAT - check the question" if s["flat"] else ""
        lines.append(f"  {qid} ({s['type']}, n={s['n']}): {shape}; {len(s['uncertain'])} uncertain{flag}")
        if s["uncertain"]:
            lines.append(f"    read by hand: {listing(s['uncertain'])}")
    return "\n".join(lines)


__all__ = ["LISTED_IDS", "USAGE_EXIT", "CommandResult", "Output", "emit", "failed", "human", "listing"]
