# Contributing Guide

Thanks for helping improve **btx-skill-jev-judge**. This page covers the day-to-day workflow and the
checks a change must pass. The development loop itself is in [DEVELOPMENT.md](DEVELOPMENT.md).

## Workflow

1. Fork and branch with a short, imperative name (`fix/keyfile-mode`, `feature/new-flag`).
2. Make focused commits; keep unrelated refactors out of the same change.
3. Run `make test` before pushing.
4. Update the documentation and `CHANGELOG.md` entries the change affects.
5. Open a pull request that references the issues it closes.

## Commits

- Write imperative messages (`Add a --timeout flag`, `Fix the keyfile mode check`).
- `make test` runs the whole gate and leaves your commits alone; create them yourself.

## Coding standards

- Keep the layering: `domain` has no I/O, `application` imports only `domain`, `adapters` import
  both, `composition` wires them. `import-linter` fails the build on a violation.
- Small, single-purpose functions and modules; type hints everywhere (pyright strict).
- Free functions and modules use `snake_case`, classes `PascalCase`.
- Keep runtime dependencies minimal and prefer the standard library.
- Every tracked text file is ASCII. Write a character that needs it in a test as a `\u` escape.

## Tests

- `make test` runs ruff (lint and format check), pyright, import-linter and pytest with coverage.
- Tests drive real seams: the loopback HTTP stub for Jev, `CliRunner` for the CLI, a fake client
  for the use case. Do not monkeypatch the package's own internals.
- Name tests `test_when_<condition>_<outcome>` and mark OS constraints (`@pytest.mark.os_agnostic`,
  `@pytest.mark.os_windows`, ...).
- A change to CLI behaviour or to configuration needs a test in the matching `tests/test_cli_*.py`
  or `tests/test_judge_config.py`.

## Checklist before a pull request

- [ ] `make test` passes locally.
- [ ] `README.md`, `CONFIG.md` and `docs/systemdesign/module_reference.md` match the change.
- [ ] No generated artefacts or virtual environments are committed.
- [ ] Version bumps happen through `make bump-*`, not by hand.

## Security

- Never commit secrets. The TypeSafe key stays in the environment or `~/.credentials/typesafe.key`;
  tokens for coverage and PyPI belong in an ignored `.env` or in CI secrets.
- Report a vulnerability as described in [SECURITY.md](SECURITY.md), not in a public issue.
