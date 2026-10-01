"""A ``.env`` file supplies the API key, read through the real process start-up.

The logging setup loads a ``.env`` from the working directory or a parent into ``os.environ`` at
start-up, and the key lookup reads that environment. The dotenv state is process-global, so each case
runs the real entry point in its own subprocess instead of through ``CliRunner``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

FAKE_KEY = "fakekeyvalue123"
OTHER_KEY = "exportedkeyvalue456"


@dataclass(frozen=True)
class CheckKeyRun:
    """What one ``check-key --json`` subprocess reported."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def data(self) -> dict[str, object]:
        """The ``data`` member of the JSON envelope."""
        envelope = json.loads(self.stdout)
        data: dict[str, object] = envelope["data"]
        return data


def run_check_key(
    cwd: Path, home: Path, *, extra_env: dict[str, str] | None = None, args: tuple[str, ...] = ()
) -> CheckKeyRun:
    """Run ``check-key --json`` from ``cwd`` with an empty home and no inherited key."""
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env.update({"HOME": str(home), "USERPROFILE": str(home), **(extra_env or {})})
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "btx_skill_jev_judge", *args, "check-key", "--json"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CheckKeyRun(completed.returncode, completed.stdout, completed.stderr)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """An empty home directory, so no keyfile exists."""
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A directory whose ``.env`` sets the key."""
    path = tmp_path / "project"
    path.mkdir()
    (path / ".env").write_text(f"TYPESAFE_API_KEY={FAKE_KEY}\n", encoding="utf-8", newline="\n")
    return path


def assert_key_found_from_env(run: CheckKeyRun) -> None:
    """The key is present, comes from ``env`` and is never printed."""
    assert run.returncode == 0, run.stderr
    assert run.data == {"present": True, "source": "env"}
    assert FAKE_KEY not in run.stdout + run.stderr


def test_env_file_in_the_current_directory_supplies_the_key(project: Path, home: Path) -> None:
    """A ``.env`` in the working directory is a key source."""
    assert_key_found_from_env(run_check_key(project, home))


def test_env_file_in_a_parent_directory_supplies_the_key(project: Path, home: Path) -> None:
    """The ``.env`` search climbs to parent directories."""
    child = project / "deeper" / "still"
    child.mkdir(parents=True)
    assert_key_found_from_env(run_check_key(child, home))


def test_no_env_file_and_no_keyfile_means_no_key(tmp_path: Path, home: Path) -> None:
    """Control: the same run without a ``.env`` finds no key, so the cases above test the file."""
    empty = tmp_path / "empty"
    empty.mkdir()
    run = run_check_key(empty, home)
    assert run.returncode == 1
    assert run.data["present"] is False


def test_an_exported_variable_wins_over_the_env_file(project: Path, home: Path) -> None:
    """The ``.env`` never overrides a variable that is already exported."""
    run = run_check_key(project, home, extra_env={"TYPESAFE_API_KEY": OTHER_KEY})
    assert run.returncode == 0, run.stderr
    assert run.data == {"present": True, "source": "env"}
    assert OTHER_KEY not in run.stdout + run.stderr


def test_a_key_only_in_the_explicit_env_file_is_not_found(tmp_path: Path, home: Path) -> None:
    """``--env-file`` feeds the configuration, not the key lookup."""
    empty = tmp_path / "empty"
    empty.mkdir()
    explicit = tmp_path / "explicit.env"
    explicit.write_text(f"TYPESAFE_API_KEY={FAKE_KEY}\n", encoding="utf-8", newline="\n")
    run = run_check_key(empty, home, args=("--env-file", str(explicit)))
    assert run.returncode == 1
    assert run.data["present"] is False


def test_the_explicit_env_file_does_not_stop_the_search_for_the_key(project: Path, home: Path, tmp_path: Path) -> None:
    """With ``--env-file`` given, a ``.env`` in the working directory still supplies the key."""
    explicit = tmp_path / "explicit.env"
    explicit.write_text("JUDGE__WORKERS=3\n", encoding="utf-8", newline="\n")
    assert_key_found_from_env(run_check_key(project, home, args=("--env-file", str(explicit))))
