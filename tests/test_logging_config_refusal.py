"""A logging setting lib_log_rich refuses is a configuration failure, not a crash of every command.

An invalid ``[lib_log_rich]`` section is a configuration failure like a broken file: the commands
that read the configuration refuse with exit 78 and one ``Error:`` line per problem naming the key,
the others still run. A refused ``LOG_*`` variable, from the environment or the ``.env`` logging
loads, is the same failure: logging still starts, with its defaults and without any ``LOG_*``
variable.

The end-to-end tests run the real CLI in a subprocess with every configuration location under
``tmp_path``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import lib_log_rich.runtime
import pytest
from lib_layered_config import Config

from btx_skill_jev_judge import __init__conf__
from btx_skill_jev_judge.adapters.logging.setup import InvalidLoggingConfigError, init_logging

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


# ------------------------------------------------------------------ a refused setting still leaves logging running


@pytest.mark.os_agnostic
def test_a_refused_logging_section_still_leaves_logging_running() -> None:
    with pytest.raises(InvalidLoggingConfigError):
        init_logging(Config({"lib_log_rich": {"rate_limit": "100:60"}}, {}))

    assert lib_log_rich.runtime.is_initialised()


@pytest.mark.os_agnostic
def test_a_refused_log_variable_still_leaves_logging_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """lib_log_rich reads every ``LOG_*`` variable on each init, so the fallback must start without them."""
    monkeypatch.setenv("LOG_CONSOLE_LEVEL", "bogus")

    with pytest.raises(InvalidLoggingConfigError):
        init_logging(Config({}, {}))

    assert lib_log_rich.runtime.is_initialised()
    assert os.environ["LOG_CONSOLE_LEVEL"] == "bogus"


@pytest.mark.os_agnostic
def test_a_refused_log_variable_in_the_dotenv_leaves_info_running(tmp_path: Path) -> None:
    """The ``.env`` in the working directory reaches the environment before logging starts."""
    (tmp_path / ".env").write_text("LOG_CONSOLE_LEVEL=bogus\n", encoding="utf-8")

    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "info"],
            cwd=tmp_path,
            env=_environment(tmp_path, {}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 0, err


@pytest.mark.os_agnostic
def test_a_refused_log_variable_in_the_dotenv_leaves_the_deploy_running(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LOG_CONSOLE_LEVEL=bogus\n", encoding="utf-8")

    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config-deploy", "--target", "user", "--force"],
            cwd=tmp_path,
            env=_environment(tmp_path, {}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 0, err


@pytest.mark.os_agnostic
def test_a_refused_log_variable_in_the_dotenv_is_a_configuration_error(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LOG_CONSOLE_LEVEL=bogus\n", encoding="utf-8")

    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "config"],
            cwd=tmp_path,
            env=_environment(tmp_path, {}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 78, err
    errors = [line for line in err.splitlines() if line.startswith("Error:")]
    assert len(errors) == 1, err
    assert errors[0].startswith("Error: lib_log_rich")


@pytest.mark.os_agnostic
def test_a_refused_log_variable_in_the_environment_leaves_info_running(tmp_path: Path) -> None:
    code, _out, err = _finished(
        subprocess.run(
            [sys.executable, "-m", "btx_skill_jev_judge", "info"],
            cwd=tmp_path,
            env=_environment(tmp_path, {"LOG_CONSOLE_LEVEL": "bogus"}),
            capture_output=True,
            check=False,
        )
    )

    assert code == 0, err


@pytest.mark.os_agnostic
def test_every_log_variable_comes_back_even_when_the_default_start_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback start hides the ``LOG_*`` variables; a failure there must not lose them.

    ``lib_log_rich.runtime.init`` is the third-party edge: the first call refuses like a bad
    level, the second (the defaults) fails for a reason of its own.
    """
    monkeypatch.setenv("LOG_CONSOLE_LEVEL", "bogus")
    seen_by_default_start: list[bool] = []

    def refuse(_config: object) -> None:
        if not seen_by_default_start and "LOG_CONSOLE_LEVEL" in os.environ:
            seen_by_default_start.append(True)
            raise ValueError("Unknown log level: 'bogus'")
        seen_by_default_start.append("LOG_CONSOLE_LEVEL" in os.environ)
        raise RuntimeError("the default start failed too")

    monkeypatch.setattr(lib_log_rich.runtime, "init", refuse)

    with pytest.raises(RuntimeError, match="the default start failed too"):
        init_logging(Config({}, {}))

    assert seen_by_default_start == [True, False]
    assert os.environ["LOG_CONSOLE_LEVEL"] == "bogus"
