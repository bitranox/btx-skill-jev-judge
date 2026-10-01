# btx-skill-jev

A Claude Code plugin with one skill, `jev-judge`. It lets Claude hand a judgment that repeats over
many items (label these 600 tickets, which of these 400 issues duplicate a known bug, match 250
supplier names to a catalog) to [TypeSafe's Jev](https://docs.typesafe.ai) through a tested script,
instead of reading every item into its own context or calling a large model once per item.

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

- [uv](https://docs.astral.sh/uv/). The script is a PEP 723 file, and `uv run` fetches Python and
  its two dependencies (httpx2, pydantic) on first use.
- A TypeSafe API key from https://console.typesafe.ai/keys. Put it in the `TYPESAFE_API_KEY`
  environment variable, or in `~/.credentials/typesafe.key` with mode 600. To create the file,
  run this, then paste the key in with an editor:

  ```bash
  mkdir -p -m 700 ~/.credentials && install -m 600 /dev/null ~/.credentials/typesafe.key
  ```

## What the script does

`skills/jev-judge/scripts/jev_judge.py` has three commands:

| Command     | Purpose                                                                                     |
|-------------|---------------------------------------------------------------------------------------------|
| `run`       | Asks the same questions about every item in a JSONL file and writes one result row per item |
| `summarize` | Shows each question's spread, flags questions whose answers never move, lists rows to check |
| `check-key` | Reports whether a usable key is configured, without printing it                             |

Before any item leaves the machine, every string in it is redacted: common secret formats (tokens,
private keys, `KEY=value` lines, passwords in URLs) and the API key itself. Requests go through
one shared rate limiter that stays under Jev's documented 40 requests per second. Rate limits,
overloads, 5xx errors, timeouts and dropped connections are retried with backoff, and the
`Retry-After` header is respected. Any other failure becomes a row that records the reason.
Run `uv run skills/jev-judge/scripts/jev_judge.py <command> --help` to see every option.

## Development

```bash
uv run --no-project --python 3.10 --with pytest --with httpx2 --with pydantic python -m pytest
uvx ruff check . && uvx ruff format --check .
uv run --no-project --python 3.10 --with pyright --with pytest --with httpx2 --with pydantic pyright
```

The tests send real HTTP requests to a local stub server that stands in for Jev. None of the
code's own internals are patched.

## License

MIT
