"""Module entry stories ensuring `python -m` mirrors the CLI."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from btx_jev_judge import __init__conf__, entry
from btx_jev_judge.adapters import cli as cli_mod

# Ensure subprocess can find the package even without editable install.
_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")


def _subprocess_env() -> dict[str, str]:
    """Build env dict with src/ on PYTHONPATH for subprocess tests."""
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = f"{_SRC_DIR}{os.pathsep}{existing}" if existing else _SRC_DIR
    return {**os.environ, "PYTHONPATH": pythonpath}


@pytest.mark.os_agnostic
def test_module_entry_executes_cli_and_shows_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """python -m invocation with no args shows help and exits 0."""
    monkeypatch.setattr(sys, "argv", ["btx_jev_judge"], raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("btx_jev_judge.__main__", run_name="__main__")

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "Usage:" in captured.out
    assert __init__conf__.shell_command in captured.out


@pytest.mark.os_agnostic
def test_module_entry_cli_exports_all_registered_commands() -> None:
    """CLI facade exports all registered commands."""
    expected_commands = {
        "cli_config",
        "cli_config_deploy",
        "cli_config_generate_examples",
        "cli_info",
        "cli_logdemo",
    }
    exported = {name for name in dir(cli_mod) if name.startswith("cli_")}
    assert expected_commands.issubset(exported)


@pytest.mark.os_agnostic
def test_module_entry_subprocess_help() -> None:
    """Verify `python -m btx_jev_judge --help` works via subprocess.

    This tests the true CLI invocation path that end-users would experience,
    complementing the runpy-based tests that run in-process.
    """
    result = subprocess.run(
        [sys.executable, "-m", "btx_jev_judge", "--help"],
        capture_output=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert __init__conf__.shell_command in result.stdout


@pytest.mark.os_agnostic
def test_module_entry_subprocess_version() -> None:
    """Verify `python -m btx_jev_judge --version` outputs version."""
    result = subprocess.run(
        [sys.executable, "-m", "btx_jev_judge", "--version"],
        capture_output=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert __init__conf__.version in result.stdout


@pytest.mark.os_agnostic
def test_entry_main_invokes_cli_with_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """entry.main() wires production services and invokes CLI.

    This tests the console script entry point used by pip-installed commands
    (btx_jev_judge, btx-jev-judge).
    """
    monkeypatch.setattr(sys, "argv", ["btx_jev_judge", "--help"])

    exit_code = entry.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage:" in captured.out
    assert __init__conf__.shell_command in captured.out
