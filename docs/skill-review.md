# jev-judge skill review (2026-10-01)

Method: bitranox meta-skill-writer RED -> GREEN -> REFACTOR. Every probe is a text-only subagent
(no file or shell tools) on the sonnet tier, one scenario per agent.

## Scenarios

1. 400 GitHub issues (title, body) in a JSONL file; mark duplicates of 30 known bugs.
2. A 12,000-line application log; which lines are real user-visible errors, not noisy retries.
3. 250 supplier product names to match against a 900-item catalog.

## Contamination check

`redcheck --corpus-cascade` over the inherited CLAUDE.md cascade and memory store: scenario 1
matched only generic words (issues, jsonl, title); scenarios 2 and 3 were clean. No inherited
document mentions Jev or TypeSafe. The TypeSafe plugin's own skill (`typesafe:typesafe-ai`) is
installed in the test environment and appears in every agent's skill listing; it is kept, because
a user of this skill will usually have it too.

## RED (no skill text)

| # | Behaviour                                                                                                                                                                                                       |
|---|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | Reached for Jev through typesafe-ai; planned to read the live API docs first (15-25k tokens) and write its own client. No redaction, no rate-limit handling, key location unknown, no check for a flat question |
| 2 | Did not use Jev: collapsed lines to distinct shapes and judged them itself. Correct for this case                                                                                                               |
| 3 | Reached for Jev: shortlist in code, then "250 questions in one request" (wrong: each item is its own state). Docs unread, no redaction, no rate-limit handling                                                  |

Every RED run included a control (a known positive and negative, or a "no target claimed by too
many items" check).

## GREEN 1 (first draft)

All three used the bundled script, piloted, summarized and read the uncertain band; scenario 2
collapsed to shapes first and kept Jev only for hundreds of shapes. Gaps reported, all closed in
the text:

| Gap                                                                                         | Fix                                                                                                                   |
|---------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Shortlist "in the item's state" conflicts with `choice` options shared by every item (1, 3) | `choice` for a fixed target set; one item per (source, candidate) pair with a 3-level `score` for a large target list |
| The example referred to a `known` field no state has (1)                                    | Example rewritten; target descriptions go in `criteria`                                                               |
| `score` criteria syntax not shown; agent guessed a `levels` key (3)                         | Example includes a 3-level `score` with an ordered `criteria` list                                                    |
| No default when the user cannot be asked about confidential data (1, 2, 3)                  | "If you cannot ask, do not send: judge by hand and say why"                                                           |
| "A few dozen distinct items" had no number (2)                                              | "Under ~50 distinct items"                                                                                            |
| Band defaults not stated (1, 3)                                                             | Defaults stated: noul 0.2-0.8, confidence below 0.6                                                                   |
| No fallback when the pilot cannot be fixed (3)                                              | "If two rewrites still fail the pilot, Jev is the wrong tool"                                                         |
| Evidence that depends on neighbouring lines is lost when collapsing (2)                     | "Anything that depends on OTHER items or lines is computed in code and passed as a field"                             |

Lost against RED: all three GREEN runs dropped the control the RED runs had. Restored as a
required part of the pilot (a known yes and a known no among the first ten) and a totals check.

## Quote-back (second draft)

Ten contested questions, each answered with a direct quote of the governing text: 10 of 10
quoted. One answer (where the 30 bug descriptions go) leaned on the example rather than the
prose; the `choice` bullet now says it.

## Retrieval

Listing with this skill, `typesafe:typesafe-ai` and four unrelated skills: "tag 600 tickets by
product area", "match 300 vendor names with typos", and "which of 2,000 search hits are about our
product" chose `jev-judge`; "write a FastAPI endpoint that routes tickets using Jev" chose
`typesafe-ai`. 4 of 4.

## Script verification

- 51 tests drive the real httpx2 client over HTTP against a loopback stub; ruff and pyright strict
  clean on Python 3.10.
- Redaction tests mutation-checked: disabling redaction turns both RED.
- The `questions.json` example in SKILL.md is executed through the real parser.
- A real `uv run <skill-dir>/scripts/jev_judge.py check-key --json` from an unrelated directory
  finds the keyfile and does not print the key.

## GREEN 2 (scenario 3 rerun, the matching case)

The agent shortlisted the top 8 targets per source in code with exact SKU/EAN keys first, built
one item per (source, candidate) pair with a 3-level `score`, ordered the file so the pilot held
known yes and no pairs, picked the best pair per source in code, flagged any target claimed by
more than 3 sources, and estimated about 2,000 requests at about $0.013.

| Gap reported                                                              | Decision                                                                                                                        |
|---------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| No way to check that the true target made the shortlist                   | Closed. RED scenario 3 had a recall check and GREEN 1 lost it; the matching bullet now requires it                              |
| `--pilot` takes the first lines, so the known yes/no must be placed there | Closed in step 4                                                                                                                |
| Best-pair rule beyond "pick the best"                                     | Closed: two "same" pairs, or none, go to the read-by-hand list                                                                  |
| Whether a product catalog counts as confidential                          | Declined: a judgment about the user's data that the skill leaves to the agent; "if you cannot ask, do not send" is the fallback |
| File formats, shortlist size, exact tie-break                             | Declined: task-specific choices, not skill guidance                                                                             |

## Executed setup instructions

The keyfile setup command was run in an empty home directory. `install -m 600 /dev/null
~/.credentials/typesafe.key` alone fails with "No such file or directory" when `~/.credentials`
does not exist; the shipped command creates the directory first (mode 700, file mode 600). The
freshly created empty keyfile then produced the unhelpful reason "keyfile"; `check-key` now says
"keyfile is empty: paste the key into it" (test added, seen failing first).

## Length

The body is about 960 words, over the 500-word target for a technique skill. Each section closes a
gap a probe reported, and the body loads only when the skill is invoked; the always-loaded
description is 425 characters.

## Re-check for the switch to uvx (0.2.1)

The skill stops bundling `scripts/jev_judge.py` and calls the published CLI through
`uvx --from 'btx-skill-jev-judge>=0.2.0' jev-judge`. The floor is 0.2.0 because PyPI already
served it when the skill text changed, and 0.2.0 has every command and option the text names.
Same method as above: text-only sonnet probes, each ending with a "Skill gaps" section.

Contamination: every probe inherits this repository's CLAUDE.md, which names the `uvx` form and
the `.env` key source. The RED therefore shows what the OLD text gets wrong despite that help.

### RED (old text, scenario on the changed lines)

The situation: the key is only in the project `.env`, the base directory holds only `SKILL.md`,
`run` exits 78, the user asks for timing and for a per-machine rate default.

| Behaviour on the old text                                                                                                                |
|------------------------------------------------------------------------------------------------------------------------------------------|
| Noticed the missing script, switched to `uvx` from the inherited CLAUDE.md, guessed a floor of `>=0.2.1` (not on PyPI at the time)       |
| Stored the command as `J='uvx --from "btx-skill-jev-judge>=0.2.1" jev-judge'`; executed, that form fails: uvx receives the double quotes |
| Did not know a `.env` supplies the key; planned to move the key into the keyfile                                                         |
| Exit 78 undocumented; inferred "config error" from sysexits                                                                              |
| Quoted "about 100 ms" per request (measured p50 is 281 ms)                                                                               |
| Could not set a per-machine rate default; "would not guess a flag name"                                                                  |
| Unsure whether the full run overwrites the pilot's rows                                                                                  |

### GREEN (new text)

| Probe                               | Result                                                                                                                         |
|-------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| Changed lines, five questions       | All five answered from the text with a direct quote: full prefix per line, `.env` honoured, 78 read correctly, rate via config |
| Scenario 1 (400 issues, 30 bugs)    | Same flow as before: one `choice` with `none`, known yes/no first, pilot to `pilot.jsonl`, band, totals check per bug          |
| Scenario 2 (12,000 log lines)       | Collapsed to shapes, computed retry-success per shape in code, Jev only above ~50 shapes                                       |
| Scenario 3 (250 names, 900 catalog) | Shortlist of 8 in code, one pair per item with a 3-level `score`, recall check, two-"same" to hand list                        |
| Quote-back on the REFACTOR fixes    | 5 of 5 quoted                                                                                                                  |

Nothing the RED or the earlier GREEN runs produced went missing.

| Gap reported                                                                        | Decision                                                                                     |
|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| How to find which source set the setting behind exit 78                             | Closed: `config --section judge` shows each value's layer and file, and redacts secrets      |
| `config-deploy` shown without the `uvx` prefix                                      | Closed: written in full                                                                      |
| `noul` never defined; what `value` holds per type                                   | Closed: one line per type in Question design                                                 |
| Where the cost comes from                                                           | Closed: `run` reports answered, failed ids and cost                                          |
| Very long issue bodies; `labels` in or out; best-pair threshold; shortlist method   | Declined: task-specific choices, not skill guidance                                          |
| Repo CLAUDE.md says the `uvx` form applies "from 0.2.1 on" while the floor is 0.2.0 | Declined: 0.2.1 is the plugin release that switches; the floor is the package version needed |

### Executed

- The quoted-prefix form, `uvx --from 'btx-skill-jev-judge>=0.2.0' jev-judge --version`, prints
  `0.2.0`; the variable form the RED wrote fails with `Failed to parse` (exit 2).
- The `check-key` and `summarize` lines, extracted from SKILL.md with grep and run unchanged:
  exit 0.
- A key only in a parent directory's `.env`: `check-key` finds it; with none, exit 1.
- `BTX_SKILL_JEV_JUDGE___JUDGE__RATE=5` shows as `rate = 5` from layer `env` in
  `config --section judge`; a `judge.api_key` setting makes `run` exit 78.
- `config-deploy --target user` in an empty home writes `config.d/60-judge.toml` with `[judge]`
  and `[summary]`.
