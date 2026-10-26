"""A logging setting lib_log_rich refuses is a configuration failure, not a crash of every command.

An invalid ``[lib_log_rich]`` section is a configuration failure like a broken file: the commands
that read the configuration refuse with exit 78 and one ``Error:`` line per problem naming the key,
the others still run.

The end-to-end tests run the real CLI in a subprocess with every configuration location under
``tmp_path``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from btx_skill_jev_judge import __init__conf__

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = __init__conf__.LAYEREDCONF_SLUG.upper().replace("-", "_")
_HOMES = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")


def _environment(cwd: Path, env: dict[str, str]) -> dict[str, str]:
    """This process's environment without the app's, logging's and the layer variables, homes in ``cwd``."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith((PREFIX, "LOG_", "LIB_LAYERED_CONFIG"))}
    clean.update(dict.fromkeys(_HOMES, str(cwd)))
    clean.update(env)
    return clean


def _finished(completed: subprocess.CompletedProcess[bytes]) -> tuple[int, str, str]:
    """Exit code, stdout and stderr of a run, decoded as UTF-8."""
    return (
        completed.returncode,
        completed.stdout.decode("utf-8", "replace"),
        completed.stderr.decode("utf-8", "replace"),
    )


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_leaves_commands_that_do_not_read_the_config_running(tmp_path: Path) -> None:
    code, out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "info"],
            cwd=tmp_path,
            env=_environment(tmp_path, {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 0, err
    assert "Info for" in out


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_is_a_configuration_error_naming_the_key(tmp_path: Path) -> None:
    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config"],
            cwd=tmp_path,
            env=_environment(tmp_path, {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 78
    errors = [line for line in err.splitlines() if line.startswith("Error:")]
    assert len(errors) == 1, err
    assert "lib_log_rich.rate_limit" in errors[0]
    assert "pydantic.dev" not in err
    assert "100:60" not in err


@pytest.mark.os_agnostic
def test_each_refused_logging_setting_gets_its_own_line(tmp_path: Path) -> None:
    env = {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60", f"{PREFIX}___LIB_LOG_RICH__RING_BUFFER_SIZE": "abc"}

    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config"],
            cwd=tmp_path,
            env=_environment(tmp_path, env),
            capture_output=True,
            check=False,
        )
    )

    errors = [line for line in err.splitlines() if line.startswith("Error:")]
    assert code == 78
    assert sorted(e.split(":", 2)[1].strip() for e in errors) == [
        "lib_log_rich.rate_limit",
        "lib_log_rich.ring_buffer_size",
    ]


@pytest.mark.os_agnostic
def test_a_value_only_lib_log_rich_itself_refuses_is_a_configuration_error_too(tmp_path: Path) -> None:
    """``queue_maxsize = 0`` passes the type check and is refused by lib_log_rich's own range check."""
    env = {f"{PREFIX}___LIB_LOG_RICH__QUEUE_MAXSIZE": "0"}

    refused_code, _out, refused_err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config"],
            cwd=tmp_path,
            env=_environment(tmp_path, env),
            capture_output=True,
            check=False,
        )
    )
    running_code, _out, running_err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "info"],
            cwd=tmp_path,
            env=_environment(tmp_path, env),
            capture_output=True,
            check=False,
        )
    )

    assert refused_code == 78
    assert "lib_log_rich.queue_maxsize" in refused_err
    assert "pydantic.dev" not in refused_err
    assert running_code == 0, running_err


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_does_not_block_the_deploy_that_replaces_it(tmp_path: Path) -> None:
    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config-deploy", "--target", "user", "--force"],
            cwd=tmp_path,
            env=_environment(tmp_path, {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 0, err
