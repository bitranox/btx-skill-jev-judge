# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |

## Reporting a Vulnerability

If you find a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for it.
2. Email the maintainer directly or use
   [GitHub's private vulnerability reporting](https://github.com/bitranox/btx-skill-jev-judge/security/advisories/new).
3. Include a description, steps to reproduce, and any relevant logs.

You can expect an initial response within 72 hours.

## How the tool handles secrets

- **The API key** is looked up in this order: an exported `TYPESAFE_API_KEY` variable, then a `.env`
  file in the current directory or any parent (loaded at startup; it never overrides a variable
  that is already exported), then `~/.credentials/typesafe.key`. `--env-file` does not feed this
  lookup. It is never a configuration value: a `judge.api_key` entry in any configuration layer
  makes `run` and `config` exit 78 (`config` shows it masked as `***REDACTED***` first).
- **The key file** is refused when its group or other permission bits are set (POSIX; the check is
  skipped on Windows), when it is empty, and when its content is not printable ASCII. The refusal
  names the reason, never the key.
- **The key is never printed, logged or put on a command line.** `check-key` reports only whether a
  key exists and where it came from (`env`, which includes a key supplied by a `.env` file, or
  `keyfile`).
- **Caution: a `.env` in the working tree is trusted.** Running `jev-judge` inside someone else's
  checkout whose `.env` sets `TYPESAFE_API_KEY` sends your items under that key, not yours. Run
  `jev-judge check-key` first to see which source is in use. `JEV_JUDGE_BASE_URL` arrives the same
  way and is still honoured only for a loopback host.
- **Redaction before sending.** Every string in an item's state is scrubbed before it leaves the
  machine: the key literal, private-key blocks, GitHub, Slack, AWS, Google and `sk-` style tokens,
  JWTs, `KEY=`, `TOKEN=`, `SECRET=`, `PASSWORD=` style assignments, `Authorization` headers and
  passwords inside URLs. Matches become `[REDACTED]` and each row records how many were replaced.
  Redaction is pattern based, so it is a safety net, not a licence to send data that is not cleared
  for a third party.
- **Loopback-only base URL.** `JEV_JUDGE_BASE_URL` redirects the client only to a loopback host
  (`localhost`, any `127.x` address, `::1`), so a hostile environment cannot send the bearer token
  to another server. Any other value is ignored.
- **Error messages** for a refused `[judge]` or `[summary]` value or a `[lib_log_rich]` type or
  range check (`Error: <section>.<key>: <reason>`), and for a flag outside its range
  (`jev-judge: --<flag>: <reason>`), name the key and the reason and never echo the offending
  value. Other errors quote what they refuse: click's type errors (`--rate abc` gives
  `Invalid value for '--rate': 'abc' is not a valid float.`), an invalid profile name, a log level
  lib_log_rich does not know (from `[lib_log_rich]` or a `LOG_*` variable) and a `config-deploy`
  permission mode lib_layered_config refuses.

## Security tooling

CI runs:

- **Bandit**: static analysis for common Python security issues
- **CodeQL**: GitHub code scanning (weekly schedule)
- **pip-audit**: dependency vulnerability scanning against the OSV database
- **Ruff security rules**: the S (flake8-bandit) and B (flake8-bugbear) rule sets

The `.snyk` file in the repository is a Snyk policy file (it excludes `scripts/` and `tests/`); no
CI workflow runs Snyk.

## Dependency policy

- Runtime dependencies use minimum-version constraints (`>=`) and are audited on every CI run.
- Known CVEs in transitive dependencies are pinned in `pyproject.toml` with an inline comment that
  names the CVE.
