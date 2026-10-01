# Measurements

## Live check against the real API (2026-10-01, model `jev-1.13.0`)

Twenty synthetic one-line changelog entries, labelled by hand (bug fix or not) and written to a
file before the run; one noul question with `true`/`false` criteria; one entry carried a fake
GitHub token. Run through `uv run skills/jev-judge/scripts/jev_judge.py run` with default settings
(8 workers, 20 requests/s).

| Measured                   | Value                                                          |
|----------------------------|----------------------------------------------------------------|
| answered                   | 20 of 20, every row on its first attempt                       |
| agreement with hand labels | 20 of 20 at a 0.5 cut                                          |
| in the 0.2-0.8 band        | 1 (0.47, "Clarify the error message for an invalid API key")   |
| clear answers              | yes rows 0.90-0.98; no rows 0.02-0.18                          |
| latency per request        | p50 281 ms, max 337 ms (measured from this host, warm pool)    |
| wall time                  | 1.26 s for 20 items                                            |
| input tokens               | 358 per row, 7,171 total, about $0.0003                        |
| redaction                  | the planted token was replaced (1 redaction, on that row only) |

What this does and does not show: the client, the request and response shapes, auth, keep-alive
and redaction work against the live service. Twenty short English lines with an unambiguous rubric
are an easy case; it is not an accuracy figure for real, longer or non-English items. The one
middle-band row was also the entry the labeller considered borderline, which is the band doing its
job rather than an error.
