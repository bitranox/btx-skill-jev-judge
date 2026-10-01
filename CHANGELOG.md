# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [Unreleased]

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
