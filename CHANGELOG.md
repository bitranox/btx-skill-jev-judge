# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [Unreleased]

## [0.3.2] 2026-10-22 12:10:35

### Changed
- SKILL.md, Question design: a question naming a state field an item lacks does not fail, Jev
  hedges toward the middle; send that field in every item with an explicit empty marker, or ask a
  variant that does not name it. The Pilot step includes the item with the fewest state fields.
- SKILL.md's version floors name 0.3.2.

## [0.3.1] 2026-10-21 00:04:23

### Changed
- SKILL.md, Pilot step: before piloting, name the fact the judgment must decide and the state
  field that carries it; a flat pilot can mean the state lacks the deciding signal, not that the
  wording is wrong.
- SKILL.md's version floors name 0.3.1.

### Security
- The dev environment requires `certifi>=2026.10.19` (GHSA-6q48-6c7w-9gw2).

## [0.3.0] 2026-10-16 23:42:10

### Changed
- The project is named `btx-skill-jev-judge` everywhere the name is not a Python import: the
  distribution name in `pyproject.toml`, the `info` output, the default logging service name, and the
  install commands in the README. PyPI treats both spellings as one project, so installs are
  unaffected. The import package stays `btx_skill_jev_judge`.
- The macOS and Windows configuration folder is now `bitranox/btx-skill-jev-judge`, matching the
  Linux folder. A config file in the old `bitranox/btx_skill_jev_judge` folder is no longer read;
  move it to the new folder.

### Removed
- The `btx_skill_jev_judge` command. The package installs `jev-judge` and `btx-skill-jev-judge`,
  which run the same program; use either instead.

## [0.2.6] 2026-10-13 15:42:05

### Added
- Python 3.15 is a supported version: declared in the classifiers, so CI and `make test-all` run it.
- `uv.lock` is committed, and `[tool.uv] exclude-newer` sets a cooldown that keeps releases younger
  than it out of the lock. CI installs exactly the locked tree on push and pull request; the nightly
  scheduled run still resolves afresh to catch upstream breakage early.

### Changed
- The install section explains why installing with uv protects against supply-chain attacks and why
  a plain `pip install` from PyPI does not.

## [0.2.5] 2026-10-12 18:59:45

### Fixed
- **A digit-only `.env` value no longer stops the program.** lib_layered_config 7.1 reads an
  unquoted `.env` or environment value that spells a number losslessly as an int, so
  `LIB_LOG_RICH__SERVICE=2026` or `JUDGE__MODEL=4` reached a text setting as a number and failed
  with `Input should be a valid string`. The logging model and `[judge]` settings now turn such a
  number back into the text the operator wrote. Numeric settings still read as numbers and
  out-of-range values are still refused.

### Changed
- **Requires lib_layered_config 7.1.6.** An unquoted `.env` value now converts like the
  environment layer, so `ENABLED=false` arrives as the boolean `false`; the permission-defaults
  test reads it that way. A `.env` setting still never reaches a deploy.

## [0.2.4] 2026-10-01

### Changed
- The `jev-judge` skill documents the `summarize` data (`rows`, `answered`, `failed`, `flat`,
  `questions`, where each question's `uncertain` list holds its read-by-hand ids) and that
  `--json-bare` prints that data without the `{ok, command, data, skipped}` envelope, on exit 1
  too.

## [0.2.3] 2026-10-01

### Changed
- The `jev-judge` skill's `uvx --from 'btx-skill-jev-judge>=X.Y.Z'` floor is now the release
  version itself, so the skill and the package it runs are released as one version. uvx keeps a
  cached install that still satisfies the floor, so with the old `>=0.2.0` a user who had run the
  skill before stayed on 0.2.1 and never got the 0.2.2 fix. A test now fails when a floor in a
  shipped `SKILL.md` or the plugin version differs from the package version.

## [0.2.2] 2026-10-01

### Fixed
- `run` no longer prints one `HTTP Request: POST ...` line per item on stderr. The `httpx2`
  request loggers now sit at WARNING unless the console level is DEBUG, so a run of hundreds of
  items leaves a summary on stderr rather than a line per item in the agent's context.

### Changed
- Every "no usable key" message names the `.env` source as well as the environment variable and
  the keyfile.

## [0.2.1] 2026-10-01

### Changed
- The `jev-judge` skill now runs the published CLI through
  `uvx --from 'btx-skill-jev-judge>=0.2.0' jev-judge` instead of a script bundled with the
  plugin. The skill text documents exit code 78, the `.env` key source, where a configuration
  value came from (`config --section judge`), per-machine defaults (`config-deploy --target user`),
  what `value` holds for each question type, and a separate `--out` for the pilot, since `run`
  overwrites its output file. The latency figure is the measured one (about 300 ms per request).

### Removed
- The bundled script `skills/jev-judge/scripts/jev_judge.py`; the package replaces it.

## [0.2.0] 2026-10-01

### Added
- The Python package `btx-skill-jev-judge` (import `btx_skill_jev_judge`) with the console scripts
  `jev-judge`, `btx-skill-jev-judge` and `btx_skill_jev_judge`. It carries the batch-judging logic
  of the `jev-judge` skill as a tested command-line tool.
- `jev-judge run`: asks the same questions about every item of a JSONL file and writes one result
  row per item as it arrives. `--pilot N` judges only the first N items; `--rate`, `--workers`,
  `--attempts`, `--timeout`, `--cap` and `--model` tune pacing, retries and batch size.
- `jev-judge summarize`: per-question distribution, rows worth reading by hand (`--band`,
  `--min-confidence`) and flat questions, which make the command exit 1.
- `jev-judge check-key`: says whether a usable key is configured and where it came from, without
  printing it.
- `--json` (an `{ok, command, data, skipped}` envelope) and `--json-bare` (the data alone, also on
  failure) on all three commands; diagnostics go to stderr.
- Exit codes: 0 yes, 1 no (a failed row, a flat question, no key), 2 usage or input/IO error,
  78 broken configuration.
- `[judge]` and `[summary]` configuration sections, overridable through configuration files, `.env`,
  `BTX_SKILL_JEV_JUDGE___JUDGE__RATE`-style environment variables, `--set` and command-line flags.
- Key lookup from `TYPESAFE_API_KEY`, else `~/.credentials/typesafe.key`. The key file must have
  mode 600 on POSIX, be non-empty and be printable ASCII. A `judge.api_key` configuration entry is
  refused.
- Redaction of secret patterns and the key literal in every string of an item's state before it is
  sent, and a cap on string length that keeps the head and tail.
- A shared request rate limiter, retries with backoff for rate limits, overloads, 5xx errors,
  timeouts and dropped connections, and `Retry-After` support.
- `JEV_JUDGE_BASE_URL`, honoured only for a loopback host, as the seam for tests against a local
  stub of the API.
- The `info`, `config`, `config-deploy`, `config-generate-examples` and `logdemo` commands of the
  CLI framework.

### Notes
- The Claude Code plugin shipped as 0.1.0 with the skill running a bundled PEP 723 script; this
  release adds the package alongside it.
