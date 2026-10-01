# btx-skill-jev

A Claude Code plugin with one skill, `jev-judge`, and the Python package behind it,
`btx-jev-judge`. It lets Claude hand a judgment that repeats over many items (label these 600
tickets, which of these 400 issues duplicate a known bug, match 250 supplier names to a catalog)
to [TypeSafe's Jev](https://docs.typesafe.ai) through a tested command-line tool, instead of
reading every item into its own context or calling a large model once per item.

Jev returns typed answers with probabilities (yes/no, one of a set of options, or a position on a
scale) in about 100 ms. Input costs $0.042 per million tokens and output is free, so a run over a
few hundred items usually costs less than a cent.

## Install in Claude Code

The repository is its own plugin marketplace, so installing takes two steps: register the
marketplace once, then install the plugin from it. Set up the [prerequisites](#prerequisites)
(uv and a TypeSafe key) first; the plugin installs without them, but the skill cannot run.

### In a Claude Code session

```text
/plugin marketplace add bitranox/btx-skill-jev
/plugin install btx-skill-jev@btx-skill-jev
```

`/plugin install` opens the plugin panel, where you choose the scope:

| Scope   | Who gets it                   | Recorded in                         |
|---------|-------------------------------|-------------------------------------|
| user    | you, in every project         | `~/.claude/settings.json`           |
| project | everyone working in this repo | `.claude/settings.json` (commit it) |
| local   | you, in this repo only        | `.claude/settings.local.json`       |

With project scope, committing the settings file turns the plugin on for your collaborators but
does not download it: each of them runs the install command once.

Closing the panel loads the plugin into the open session. If it does not appear, run
`/reload-plugins`.

### From your shell

Useful in a setup script:

```bash
claude plugin marketplace add bitranox/btx-skill-jev
claude plugin install btx-skill-jev@btx-skill-jev                  # user scope
claude plugin install btx-skill-jev@btx-skill-jev --scope project  # or project scope
```

Plugins installed this way load in the next session, or after `/reload-plugins` in an open one.

### Check that it works

`claude plugin list` shows `btx-skill-jev@btx-skill-jev`. In a session, describe a matching task
("tag these 600 support tickets by product area") and Claude loads the skill, or invoke it
directly with `/btx-skill-jev:jev-judge`. Its first step runs `check-key`,
which tells you whether the TypeSafe key is usable without printing it.

### Updates

Auto-update is off by default for marketplaces other than Anthropic's own. Update by hand:

```bash
claude plugin marketplace update btx-skill-jev
claude plugin update btx-skill-jev@btx-skill-jev
```

or turn auto-update on in `/plugin`, on the **Marketplaces** tab. An open session keeps the version
it loaded until you run `/reload-plugins`.

### Uninstall

```bash
claude plugin uninstall btx-skill-jev@btx-skill-jev  # add --scope project for a project install
claude plugin marketplace remove btx-skill-jev       # also uninstalls its plugins
```

### From a local clone

To try a change before it is pushed, register the directory instead of the GitHub repository.
Start a relative path with `./`, or Claude Code reads it as `owner/repo`:

```text
/plugin marketplace add ./btx-skill-jev
/plugin install btx-skill-jev@btx-skill-jev
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/). It fetches Python and the CLI's dependencies on first use.
- A TypeSafe API key from https://console.typesafe.ai/keys. Put it in the `TYPESAFE_API_KEY`
  environment variable, or in `~/.credentials/typesafe.key` with mode 600. To create the file,
  run this, then paste the key in with an editor:

  ```bash
  mkdir -p -m 700 ~/.credentials && install -m 600 /dev/null ~/.credentials/typesafe.key
  ```

## Installation

The command-line tool is the PyPI package `btx-jev-judge`. It installs two commands, `jev-judge`
and `btx-jev-judge`, which are the same program.

```bash
uvx --from btx-jev-judge jev-judge --help   # run once, nothing installed
uv tool install btx-jev-judge               # or install it on your PATH
jev-judge --version
```

pip, pipx and other methods are in [INSTALL.md](INSTALL.md). Python 3.10 or newer is required.

## Quick Start

Write one JSON object per item, with an `id` and a `state` of named fields:

```json
{"id": "t-1", "state": {"title": "Login loops after SSO", "body": "I sign in and land on the login page again."}}
{"id": "t-2", "state": {"title": "Add dark mode", "body": "Please add a dark theme."}}
```

Write the questions once. `noul` is Jev's yes/no type and answers with the probability of yes:

```json
[{"id": "is_bug", "type": "noul", "instructions": "Does `body` describe something that is broken?"}]
```

Then check the key, try ten items, run all of them and summarize:

```bash
jev-judge check-key
jev-judge run --items items.jsonl --questions questions.json --out rows.jsonl --pilot 10
jev-judge run --items items.jsonl --questions questions.json --out rows.jsonl
jev-judge summarize --rows rows.jsonl
```

| Command     | Purpose                                                                                     |
|-------------|---------------------------------------------------------------------------------------------|
| `run`       | Asks the same questions about every item and writes one result row per item                 |
| `summarize` | Shows each question's spread, flags questions whose answers never move, lists rows to check |
| `check-key` | Reports whether a usable key is configured and where it came from, without printing the key |

`run` and `summarize` take `--json` for an `{ok, command, data, skipped}` envelope on stdout, or
`--json-bare` for the data alone (also on failure). Diagnostics always go to stderr.

| Exit code | Meaning                                                                                 |
|-----------|-----------------------------------------------------------------------------------------|
| 0         | Yes: every item answered, no flat question, a key is present                            |
| 1         | No: some row failed, a question looks flat, or `check-key` found no key                 |
| 2         | Usage, input or IO error (also an out-of-range flag); stderr says `jev-judge: <reason>` |
| 78        | Broken configuration; stderr says `Error: <reason>`                                     |

A click usage error (a bad option type, an unknown option, `--json` together with `--json-bare`)
exits 2 and prints no JSON, even under `--json-bare`.

Before any item leaves the machine, every string in its state is redacted: common secret formats
(tokens, private keys, `KEY=value` lines, passwords in URLs) and the API key itself. Requests share
one rate limiter that stays under Jev's documented 40 requests per second. Rate limits, overloads,
5xx errors, timeouts and dropped connections are retried with backoff and the `Retry-After`
header is respected. Any other failure becomes a row that records the reason. `<command> --help`
lists every option.

## Configuration

Defaults for `run` and `summarize` live in the `[judge]` and `[summary]` sections of a layered
configuration (files, `.env`, environment variables). A command-line flag always wins. The API key
is never a configuration value: a `judge.api_key` entry is refused with exit 78. Environment
variables look like `BTX_JEV_JUDGE___JUDGE__RATE=5`. Every key, default and layer is in
[CONFIG.md](CONFIG.md).

## Architecture

The package follows a layered ports-and-adapters layout, and `import-linter` enforces it in the
test run:

| Layer       | Package        | Holds                                                           |
|-------------|----------------|-----------------------------------------------------------------|
| Composition | `composition/` | Wires adapters to ports                                         |
| Adapters    | `adapters/`    | CLI, Jev HTTP client, key lookup, files, configuration, logging |
| Application | `application/` | The judge use case and the port protocols                       |
| Domain      | `domain/`      | Questions, items, rows, redaction, summary; no I/O              |

Two contracts in `pyproject.toml` hold it together. "Clean Architecture layers" lets each layer
import only the layers below it (composition, then adapters, then application, then domain).
"Domain is pure" forbids the domain from importing adapters or composition. Tests drive real
seams: a loopback HTTP stub stands in for Jev, `CliRunner` drives the CLI, and a fake client
drives the use case. See [docs/systemdesign/module_reference.md](docs/systemdesign/module_reference.md).

## Further Documentation

- [INSTALL.md](INSTALL.md): every way to install the CLI
- [CONFIG.md](CONFIG.md): configuration sections, layers and environment variables
- [DEVELOPMENT.md](DEVELOPMENT.md): the dev loop, gates and releasing
- [CONTRIBUTING.md](CONTRIBUTING.md): how to send a change
- [SECURITY.md](SECURITY.md): key handling, redaction and reporting a vulnerability
- [docs/systemdesign/module_reference.md](docs/systemdesign/module_reference.md): module map
- [docs/measurements.md](docs/measurements.md): one live check against the real API
- [CHANGELOG.md](CHANGELOG.md)
- [ai-stance.md](ai-stance.md) and [ai-transparency.md](ai-transparency.md): how AI was used here

## License

MIT
