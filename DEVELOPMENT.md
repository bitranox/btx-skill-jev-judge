# Development

The repository is two things at once: the Python package `btx_jev_judge` (PyPI `btx-jev-judge`)
and a Claude Code plugin marketplace (`.claude-plugin/`, `skills/jev-judge/`). Its build, test and
release tasks are run by [bmk](https://pypi.org/project/bmk/) through a generated `Makefile`.

## Everyday targets

`make help` is the authoritative list; it is generated from the Makefile itself. The ones you
use most:

| Target                 | What it does                                                           |
|------------------------|------------------------------------------------------------------------|
| `make test`            | The whole gate: format, lint, types, import contracts, tests, coverage |
| `make test-all`        | Tests and types on every supported Python version                      |
| `make testintegration` | Only the tests marked `integration`                                    |
| `make push`            | Run the gate, commit, push                                             |
| `make bump-patch`      | Bump the version (`bump-minor`, `bump-major` likewise)                 |
| `make release`         | Tag the current version and create the release                         |
| `make run`             | Run the CLI                                                            |

The Makefile is rewritten by bmk on every run, so do not edit it. `bmk --help` documents the CLI
behind it.

## The gate

`make test` runs ruff (lint and format check, Markdown included), pyright in strict mode,
`import-linter`, and pytest with branch coverage. It must pass before every push. Unset a stray
`VIRTUAL_ENV` first (`env -u VIRTUAL_ENV make test`) so bmk uses the project `.venv`.

Pytest markers: `os_agnostic`, `os_windows`, `os_macos`, `os_posix`, `os_linux` say where a test
runs; `local_only` tests are skipped in CI; `integration` tests need external resources and run
through `make testintegration`.

## Layout and layering

```text
src/btx_jev_judge/
  domain/        questions, items, answers, rows, redaction, summary (no I/O)
  application/   the judge use case and the port protocols
  adapters/      cli, jev (HTTP client), key, files, config, logging, memory
  composition/   wires adapters to ports
  entry.py       console-script entry point
```

`import-linter` enforces two contracts from `pyproject.toml`: the layers
(composition, then adapters, then application, then domain, each importing only downward) and a
pure domain. `docs/systemdesign/module_reference.md` maps every module.

## Testing approach

Tests drive real seams instead of patching internals:

- The Jev client talks to a loopback HTTP stub server. `JEV_JUDGE_BASE_URL` is honoured only for a
  loopback host, which is what makes this possible without touching the real API.
- The CLI is driven with `click.testing.CliRunner`.
- The judge use case receives a fake `JudgeClient`.
- `composition.build_testing(env=..., home=...)` wires the in-memory configuration and logging
  adapters (`adapters/memory/`) with the real key lookup and Jev client, bound to the environment
  and home directory the test supplies. A test never sees the developer's own key or home.

## Metadata

`pyproject.toml` is the source of truth. `src/btx_jev_judge/__init__conf__.py` holds static copies
that a test keeps in sync, so runtime code never queries packaging metadata. Bump versions with
`make bump-*`; it also updates `.claude-plugin/plugin.json`.

## Dependency auditing

`make test` runs `pip-audit`. Fix a finding by raising the dependency floor in `pyproject.toml`
with an inline comment that names the CVE.

## Releasing

1. `make test`, then `make bump-patch` (or `-minor`) and commit.
2. `make push`, and wait for CI on that commit to finish green.
3. `make release` tags the version in `pyproject.toml` and creates the GitHub release; the release
   workflow publishes to PyPI. It tags the version that is already committed and does not bump.

`.github/` is managed by an external CI template; never edit it in this repository.
`main` is public and append-only: no force-push, no history rewriting.
