"""What a real ``run`` leaves on stderr: a summary, never one line per request.

The skill hands ``run`` hundreds of items so they stay out of the agent's context, and the agent
reads the command's stderr. A log line per HTTP request would put every item back in. Logging is
process-global, so the real entry point runs in a subprocess against the loopback Jev stub.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import JevStub

KEY = "tk_" + "d" * 40
QUESTION = {"id": "dup", "type": "noul", "instructions": "Is `title` a duplicate?"}
ITEMS = 5

pytestmark = pytest.mark.os_agnostic


def _answer(_body: dict[str, Any], _n: int) -> tuple[int, dict[str, Any], dict[str, str]]:
    return (
        200,
        {"model": "jev-1.13.0", "usage": {"input_tokens": 100}, "answers": {"dup": {"type": "noul", "noul": 0.5}}},
        {},
    )


def _run(jev: JevStub, tmp_path: Path, *extra_env: tuple[str, str]) -> subprocess.CompletedProcess[str]:
    (tmp_path / "items.jsonl").write_text(
        "".join(json.dumps({"id": i, "state": {"title": f"t{i}"}}) + "\n" for i in range(ITEMS)), encoding="utf-8"
    )
    (tmp_path / "q.json").write_text(json.dumps([QUESTION]), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY" and not k.startswith("LIB_LOG_RICH")}
    env.update(
        {
            "TYPESAFE_API_KEY": KEY,
            "JEV_JUDGE_BASE_URL": jev.url,
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            **dict(extra_env),
        }
    )
    args = ["run", "--items", "items.jsonl", "--questions", "q.json", "--out", "rows.jsonl"]
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "btx_skill_jev_judge", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_a_run_prints_no_line_per_http_request(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = _answer
    done = _run(jev, tmp_path)
    assert done.returncode == 0, done.stderr
    assert len(jev.seen) == ITEMS
    assert f"answered {ITEMS} of {ITEMS}" in done.stdout + done.stderr
    assert "HTTP Request" not in done.stderr


def test_debug_logging_still_shows_each_request(jev: JevStub, tmp_path: Path) -> None:
    jev.reply = _answer
    done = _run(jev, tmp_path, ("BTX_SKILL_JEV_JUDGE___LIB_LOG_RICH__CONSOLE_LEVEL", "DEBUG"))
    assert done.returncode == 0, done.stderr
    assert done.stderr.count("HTTP Request") == ITEMS
