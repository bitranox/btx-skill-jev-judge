# btx-skill-jev

A Claude Code plugin with one skill, `jev-judge`. It lets Claude hand a judgment that repeats over
many items (label these 600 tickets, which of these 400 issues duplicate a known bug, match 250
supplier names to a catalog) to [TypeSafe's Jev](https://docs.typesafe.ai) through a tested script,
instead of reading every item into its own context or calling a large model once per item.

Jev returns typed answers with probabilities (yes/no, one of a set of options, or a position on a
scale) in about 100 ms. Input costs $0.042 per million tokens and output is free, so a run over a
few hundred items usually costs less than a cent.

## Install

```text
/plugin marketplace add bitranox/btx-skill-jev
/plugin install btx-skill-jev@btx-skill-jev
```

Claude Code then loads the skill whenever the task fits. You can also invoke it as
`/btx-skill-jev:jev-judge`.

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
