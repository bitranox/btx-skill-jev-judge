---
name: jev-judge
description: Use when the same bounded judgment has to be made over many items during your own work - labelling, triage, duplicate or entity matching, relevance, a yes/no or a 1-5 rating across dozens to thousands of issues, tickets, log lines, records, search hits or names - and you are about to read them all into context, loop an LLM call per item, or hand-write a TypeSafe Jev client for it. Not for building Jev into an application.
---

# jev-judge

When the judgment is the SAME bounded question per item, write it once as a Jev question and let
the `jev-judge` command ask it per item, instead of reading every item into context. Jev
(TypeSafe) returns a typed answer - probability of yes, one option of a set, or a position on a
scale - in about 300 ms per request, 8 requests in parallel by default, at $0.042 per million
input tokens: hundreds of items take seconds and cost under one cent.

You keep the parts only you can do: the question, the evidence, the uncertain rows. Do not write
your own Jev client or re-read the TypeSafe API docs; `jev-judge` handles the API, Jev's rate
limit, retries and secret redaction.

## When not to use it

- **Under ~50 distinct items.** Collapse duplicates first (log lines to their shape, repeated
  names); if fewer than ~50 distinct cases remain, judge them yourself.
- **Arithmetic, counting, dates, versions, exact lookups**: do them in code; Jev is weak there.
- **Generation, summaries, reasoning across items**: Jev writes no text and sees one item.
- **Data not cleared for a third party.** Secrets are redacted automatically, but customer data,
  private repos and internal logs need the user's OK before the first `run` (the pilot sends data
  too). If you cannot ask, do not send: judge by hand and say why.

## Procedure

1. `check-key`. Exit 1: tell the user how to set up a key (Setup), and say so if you judge by
   hand instead. It only finds a key and never tests it: pilot rows that all fail with `http 401`
   mean a wrong key.
2. **Extract in code** to `items.jsonl`, one line per item: `{"id": ..., "state": {...}}`, ids
   unique. Rows carry the id as a string (`7` comes back as `"7"`): look them up by `str(id)`.
   One item, one state, one request; never pack many items into one state. Put each piece of
   evidence in its own named field, only what the question needs. A string over 60,000
   characters (`run --cap`) is cut to its head and tail with no flag on the row, so trim long text
   in code to what the question needs. Anything that depends on OTHER items or lines (a retry later
   succeeded, how often a value occurs) is computed in code and passed as a field.
3. **Write `questions.json`** (Question design). Several questions about the same item share one
   request.
4. **Pilot.** Before it, name the fact the judgment must decide and the state field that carries
   it. If no field carries it, for example whether an author MEASURED a claim (that lives in their
   session, not in the text), no wording can recover it: the pilot comes back flat or nearly so,
   every item scored alike whether it matters or not, and invites rewrite after rewrite. A proxy
   question that does spread the scores can still pass the very items that matter, so check it
   against known positives before trusting the spread. If the signal is absent, judge another way;
   for an existing gate, label what each of its past decisions changed and size it from that.
   `run --pilot 10 --out pilot.jsonl` judges the first ten lines, so put at least one
   item you KNOW is a yes and one you know is a no among them, plus the item with the fewest state
   fields any real item has: the first ten lines of an export may hold none, and that sparse item
   must still separate from a known no. Read the ten rows against their items. If you would have
   answered more than one differently, fix the question or the state, not the threshold. If two
   rewrites still fail the pilot, Jev is the wrong tool here: say so and judge another way.
   The pilot's reported cost times items / 10 roughly estimates the full run (cost grows with
   item length); every request carries every question's instructions and criteria, so a long
   `choice` raises the cost per item.
5. **Run everything, then `summarize`.** Exit 1 means a FLAT question (every item got about the
   same answer): a broken question until you have shown the items really are alike, or that the
   state lacks the deciding signal (step 4).
6. **Decide with a band, not one cut.** `summarize` lists as "read by hand" every noul between 0.2
   and 0.8 and every choice or score with confidence below 0.6 (`--band`, `--min-confidence`).
   Take the rest as decided and read those yourself, or hand them to the user. A probability is
   not permission to do anything destructive.
7. **Sanity-check the totals in code** (e.g. no target claimed by implausibly many items), then
   **report coverage**: items, answered, failed ids, read by hand, cost.

## Question design

- Three types: `noul` (yes/no; `value` is the probability of yes; `criteria` takes only the keys
  `true` and `false`), `choice` (`value` is the chosen `criteria` key) and `score` (2-10 ordered
  `criteria` levels; `value` is the expected level, counted from 0 and possibly between two:
  1.7 on three levels; `probabilities` is keyed by level as a string, `"0"`, `"1"`, ...).
- `instructions` carries the whole question; the question `id` is never shown to the model. Refer
  to state fields as backticked paths (`title`, `candidates[0]`), and only to fields every item has.
  A question naming a field an item lacks does not fail: Jev hedges toward the middle (measured:
  0.66-0.70 against a 0.7 threshold, where the same item scored 0.89-0.90 with the field present),
  so the defect never shows as an error or a non-zero exit. If extraction drops a key whose value
  is empty, either send that key in every item with an explicit empty marker, or ask a variant
  that does not name it for the items without it, and pilot one of those items (step 4).
- Jev reads literally: state the exact condition, put boundary cases in `criteria`.
- `choice` options are the SAME for every item, so use it for a fixed set of targets (2-255; e.g.
  30 known bugs, 8 product areas), each target's description in `criteria`, not in the state.
  ALWAYS include a no-match option such as `"none"`.
- **Matching against a large target list** (a 900-item catalog): shortlist the top 5-10 targets
  per item in code (exact keys like SKU or EAN first), then make one item per (source, candidate)
  PAIR, id `"<source>|<candidate>"`, asked a 3-level `score`; a pair is "same" when
  `probabilities["2"]` is its largest. Pick the best pair per source in code, and send a source
  with two "same" pairs, or none, to the read-by-hand list. Check on a few hand-matched sources
  that the true target made the shortlist: a target never shortlisted can never be chosen, so
  widen the shortlist rather than trust the answers.
- Several labels can apply at once: one `noul` per label, not one `choice`.

```json
[{"id": "bug", "type": "choice",
  "instructions": "Which of the listed bugs does the issue in `title` and `body` report? Choose none if it reports something else or only touches the same area.",
  "criteria": {"none": "something not listed", "b12": "login loop after SSO", "b31": "export drops the last row"}},
 {"id": "user_visible", "type": "noul", "instructions": "Does `body` describe a failure an end user would notice?",
  "criteria": {"true": "the user sees an error or wrong result", "false": "internal only, or recovered"}},
 {"id": "same", "type": "score", "instructions": "Are `source_name` and `catalog_name` the same sellable product (same brand, variant and pack size)?",
  "criteria": ["different product", "related, cannot tell", "same product"]}]
```

## Commands

`jev-judge` is the PyPI package `btx-skill-jev-judge`; `uvx` fetches it, Python and the
dependencies on first use and caches them. Type the prefix in full on every line, single quotes
included: unquoted, the shell reads `>=` as a redirection, and stored in a variable the quotes
reach `uvx` and it refuses the name.

```bash
uvx --from 'btx-skill-jev-judge>=0.3.6' jev-judge check-key
uvx --from 'btx-skill-jev-judge>=0.3.6' jev-judge run --items items.jsonl --questions questions.json --out pilot.jsonl --pilot 10
uvx --from 'btx-skill-jev-judge>=0.3.6' jev-judge run --items items.jsonl --questions questions.json --out rows.jsonl
uvx --from 'btx-skill-jev-judge>=0.3.6' jev-judge summarize --rows rows.jsonl
```

`run` sends and bills every non-blank line of `--items` (with `--pilot N`, the first N); nothing in
a line marks it to skip. A top-level key other than `id` and `state` refuses the whole run (exit 2)
before anything is sent, and an annotation of your own (an expected answer, a note) put inside
`state` is sent to Jev with the item. Keep your annotations in a separate file keyed by id, and
filter `items.jsonl` in code before `run` to cut what is sent and billed.

`run` reports answered, failed ids, cost and the `models` that answered. It overwrites `--out` and
never resumes: to retry failed rows, write their items to a new file, run that with a new `--out`
and merge the rows in code. The default model `jev-latest` moves when a release ships; to keep the
full run on the pilot's model, pass it `--model` with the version id the pilot reported in
`models` (`jev-x.y.z`). `<command> --help` lists every option (`--rate`, `--workers`, `--band`,
...); `--json` gives an `{ok, command, data, skipped}` envelope and `--json-bare` the `data` alone,
on every exit (on 2 and 78 it is `{"error": "<message>"}`).

Exit codes: 0 yes; 1 no (`run`: a row failed; `summarize`: a question is flat; `check-key`: no
key); 2 usage, input or IO error (`run` without a key included); 78 broken configuration, and
stderr names the setting. A `LOG_*` name is an environment variable or a `.env` line: unset or
correct it there (`config` exits 78 too while one is broken). For a `judge.*` or `summary.*` name,
`config --section judge` (or `summary`) shows the layer each value came from (`defaults`, `app`,
`host`, `user`, `dotenv`, `env`, with the file), then exits 78 naming the problem; fix it there,
not on the command line.

A row: `id`, `ok`, `answers` (`{qid: {type, value, probabilities, confidence}}`), `model`, and
`reason` when it failed. The `summarize` data: `rows`, `answered`, `failed` (ids), `flat`
(question ids) and `questions` (`{qid: {type, n, flat, uncertain, ...}}`); `uncertain` is that
question's read-by-hand ids.

## Setup

The key comes from an exported `TYPESAFE_API_KEY`, else a `TYPESAFE_API_KEY=` line in a `.env` in
the current directory or a parent, else `~/.credentials/typesafe.key` (mode 600). It is never a
configuration setting. Keys: https://console.typesafe.ai/keys. If none is set up, have the user
run this, then paste the key in with an editor; never ask for it in chat and never read it out:

```bash
mkdir -p -m 700 ~/.credentials && install -m 600 /dev/null ~/.credentials/typesafe.key
```

Per-machine defaults (e.g. a lower `rate`): this prints the files it writes; edit `[judge]` /
`[summary]` in the one named `60-judge.toml`.

```bash
uvx --from 'btx-skill-jev-judge>=0.3.6' jev-judge config-deploy --target user
```

Or set `BTX_SKILL_JEV_JUDGE___JUDGE__RATE=5` in the environment. A flag always wins.

## Related

`typesafe:typesafe-ai` covers building Jev INTO an application. Jev's known weak spots, as
documented for `jev-1.13.0`: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
