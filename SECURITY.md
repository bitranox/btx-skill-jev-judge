# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |

## Reporting a Vulnerability

If you find a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for it.
2. Email the maintainer directly or use
   [GitHub's private vulnerability reporting](https://github.com/bitranox/btx-skill-jev/security/advisories/new).
3. Include a description, steps to reproduce, and any relevant logs.

You can expect an initial response within 72 hours.

## How the tool handles secrets

- **The API key** is looked up in this order: an exported `TYPESAFE_API_KEY` variable, then a `.env`
  file in the current directory or any parent (loaded at startup; it never overrides a variable
  that is already exported), then `~/.credentials/typesafe.key`. `--env-file` does not feed this
  lookup. It is never a configuration value: a `judge.api_key` entry in any
  configuration layer is refused with exit 78.
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
  (`localhost`, `127.0.0.1`, `::1`), so a hostile environment cannot send the bearer token to
  another server. Any other value is ignored.
- **Error messages** about configuration and flags name the key and the reason and never echo the
  offending value.

## Security tooling

CI runs:

- **Bandit**: static analysis for common Python security issues
- **CodeQL**: GitHub code scanning (weekly schedule)
- **pip-audit**: dependency vulnerability scanning against the OSV database
- **Snyk**: continuous dependency monitoring
- **Ruff security rules**: the S (flake8-bandit) and B (flake8-bugbear) rule sets

## Dependency policy

- Runtime dependencies use minimum-version constraints (`>=`) and are audited on every CI run.
- Known CVEs in transitive dependencies are pinned in `pyproject.toml` with an inline comment that
  names the CVE.
