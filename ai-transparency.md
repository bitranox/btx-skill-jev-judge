# AI transparency

The author and owner of this project is the human, [@bitranox](https://github.com/bitranox).
Every design and engineering decision is theirs, and they answer for everything published here.
An AI assistant (Claude, run through the Claude Code CLI) was used as a tool along the way,
mostly for typing and legwork under that direction. This page says where, so you can weigh the
work on its merits. The reasoning behind working this way is in [ai-stance.md](ai-stance.md).

## The human's work

- The problem is theirs: a judgment that repeats over hundreds of items should not be read into an
  agent's context or looped through a large model, when a small typed model can answer it
  per item.
- The shape is theirs: a skill that tells an agent when not to use Jev, a tested command-line tool
  behind it instead of a throwaway script, redaction of secrets before anything is sent, a request
  rate limiter, a pilot mode, and a check that flags a question whose answers never move.
- The key handling is theirs: the key is never a configuration value, never printed, and read only
  from the environment or a mode-600 file.
- The repository doubles as its own plugin marketplace and as a PyPI package; that packaging and the
  release order are the human's decisions.
- The human reviewed and corrected the work at each step. Commits go out under the human's name
  and authority, with no AI co-author line, and the human is responsible for what is published.

## Where the AI was used

As a tool, under that direction, it typed the code, the tests (including the loopback stub of the
API), these documents and the plugin manifests to the human's design, and laid out options at each
fork for the human to choose from. It also ran the live check against the real API recorded in
[docs/measurements.md](docs/measurements.md) with a key the human supplied, and it played the part
of the throwaway agents in [docs/skill-review.md](docs/skill-review.md), which tested whether an
agent following the skill behaves correctly. None of the decisions, and none of the
accountability, were the AI's.

## What has been checked, and what has not

Checked: the test suite runs against a local HTTP stub that stands in for Jev, never against the
real API, and the gate (ruff, pyright in strict mode, import-linter, pytest with coverage) runs on
every push in CI on Linux, macOS and Windows. One live run against the real API (20 short items)
agreed with hand labels; it is a smoke test of the client, not an accuracy figure.

Not checked: how well Jev judges your items. Run `--pilot`, read the rows against their items, and
treat a probability as a hint, never as permission to do anything destructive.

## Checking it yourself

The source, history and tests are in this repository. `jev-judge run --pilot 10` shows what a run
does on ten items, and [SECURITY.md](SECURITY.md) lists exactly what is redacted before an item is
sent.

## What this isn't

It is not a TypeSafe product, and TypeSafe has not reviewed or endorsed it. It is a small tool for
people who want an agent to hand repetitive judgments to Jev, and it does not remove the need to
look at the uncertain rows yourself.

## License and attribution

The text and code here are under the MIT License (see [`LICENSE`](LICENSE)). Anthropic's terms put
ownership of model output with the user, so the human owns this and answers for it.
