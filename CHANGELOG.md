# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [0.2.0] 2026-10-01

### Added
- The Python package `btx-jev-judge` (import `btx_jev_judge`) with the console scripts
  `jev-judge` and `btx-jev-judge`. It carries the batch-judging logic of the `jev-judge` skill as
  a tested command-line tool.
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
  `BTX_JEV_JUDGE___JUDGE__RATE`-style environment variables, `--set` and command-line flags.
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
