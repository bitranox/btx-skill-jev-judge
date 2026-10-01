# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx2>=2.13", "pydantic>=2.13"]
# ///
"""Ask TypeSafe's Jev the same typed questions about every item in a JSONL file.

For a judgment repeated over many items - label, match, triage, score, yes/no - this sends each
item's state to Jev (a "System One" model: typed answers with probabilities, ~100 ms warm, input
billed at $0.042 per million tokens, output free) and writes one result row per item.

Every string in a state is redacted (common secret shapes plus the API key itself) before it
leaves the machine. Requests are spaced by a shared rate limiter, because Jev's documented limit
is 40 requests/s and a thread pool alone would exceed it. A 429, 529, 5xx, timeout or dropped
connection is retried with backoff (honouring ``Retry-After``); any other failure becomes a row
with its reason, never an exception, so one bad item cannot lose the other 999.

Run it with uv, which provisions Python and the dependencies::

    uv run jev_judge.py run --items items.jsonl --questions questions.json --out rows.jsonl
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import re
import stat
import statistics
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import IO, Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

__all__ = [
    "DEFAULT_BASE_URL",
    "Answer",
    "ChoiceQuestion",
    "Item",
    "JevClient",
    "NoulQuestion",
    "Outcome",
    "Question",
    "RateLimiter",
    "Row",
    "ScoreQuestion",
    "Settings",
    "UsageError",
    "judge_all",
    "load_items",
    "load_key",
    "load_questions",
    "main",
    "parse_questions",
    "prepare_state",
    "redact",
    "resolve_base_url",
    "summarize",
]

DEFAULT_BASE_URL = "https://api.typesafe.ai"
ENDPOINT = "/v1/systemone"
DEFAULT_MODEL = "jev-latest"
KEY_ENV = "TYPESAFE_API_KEY"
BASE_URL_ENV = "JEV_JUDGE_BASE_URL"
KEYFILE = Path(".credentials") / "typesafe.key"
KEYFILE_FORBIDDEN_BITS = stat.S_IRWXG | stat.S_IRWXO
# Throttling and transient server or network trouble: worth asking again, since a judgment is a
# read-only request and re-sending it costs a fraction of a cent. Anything else (401, 422) would
# fail identically on every attempt.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
# Never sleep longer than this on one Retry-After; a server asking for more is better reported.
MAX_RETRY_WAIT = 60.0
# Characters per string. Jev reads at most 32k tokens of state plus the longest question, so a
# string this long is already most of the budget; the cap keeps its head and tail.
DEFAULT_CAP = 60_000
REDACTED = "[REDACTED]"
HTTP_OK = 200
EXIT_USAGE = 2
# Human output lists at most this many ids per line; --json carries them all.
LISTED_IDS = 20


class UsageError(Exception):
    """Input the caller must fix. The CLI maps it to exit code 2."""


# --- models: questions ---------------------------------------------------------------------------


class QuestionType(str, Enum):
    """The three Jev primitives."""

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"


NonEmptyStr = Annotated[str, Field(min_length=1)]
# A rubric or instruction may be prose, or structured data the prose refers to by `name`.
Text = NonEmptyStr | dict[str, JsonValue] | list[JsonValue]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NoulCriteria(_Strict):
    """What a yes and a no mean; both optional."""

    true: Text | None = None
    false: Text | None = None


class _QuestionBase(_Strict):
    id: NonEmptyStr
    instructions: Text

    def to_api(self) -> dict[str, JsonValue]:
        """Render the question as the API expects it inside the ``questions`` map.

        Returns:
            ``{"type", "instructions"}`` plus ``"criteria"`` when the question has any.

        """
        return self.model_dump(mode="json", exclude={"id"}, exclude_none=True)


class NoulQuestion(_QuestionBase):
    """A yes/no question; the answer is the probability of yes."""

    type: Literal[QuestionType.NOUL]
    criteria: NoulCriteria | None = None


class ChoiceQuestion(_QuestionBase):
    """Pick one of 2-255 options; a None description means the key says it all."""

    type: Literal[QuestionType.CHOICE]
    criteria: Annotated[dict[str, Text | None], Field(min_length=2, max_length=255)]


class ScoreQuestion(_QuestionBase):
    """A position on 2-10 ordered levels."""

    type: Literal[QuestionType.SCORE]
    criteria: Annotated[list[Text], Field(min_length=2, max_length=10)]


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]
_QUESTIONS = TypeAdapter(list[Question])


class Item(_Strict):
    """One thing to judge: an id unique in its file, and the named fields Jev reads."""

    id: str
    state: Annotated[dict[str, JsonValue], Field(min_length=1)]


class _ItemIn(_Strict):
    id: str | int
    state: Annotated[dict[str, JsonValue], Field(min_length=1)]


# --- models: answers and rows --------------------------------------------------------------------


class _Lenient(BaseModel):
    # The API may add fields; only the ones read here are part of the contract.
    model_config = ConfigDict(frozen=True, extra="ignore")


class _NoulIn(_Lenient):
    type: Literal[QuestionType.NOUL]
    noul: float


class _ChoiceIn(_Lenient):
    type: Literal[QuestionType.CHOICE]
    choice: str
    probabilities: dict[str, float]
    confidence: float


class _ScoreIn(_Lenient):
    type: Literal[QuestionType.SCORE]
    score: float
    probabilities: dict[str, float]
    confidence: float
    legend: dict[str, str] = Field(default_factory=dict)


class _Usage(_Lenient):
    input_tokens: int = 0


class _ResponseIn(_Lenient):
    model: str
    answers: dict[str, Annotated[_NoulIn | _ChoiceIn | _ScoreIn, Field(discriminator="type")]]
    usage: _Usage = Field(default_factory=_Usage)


class Answer(_Strict):
    """One answer in one shape: noul and score carry a number, choice the chosen option."""

    type: QuestionType
    value: float | str
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


class Row(_Strict):
    """The result for one item. A failure is a row with ``ok`` False and a ``reason``."""

    id: str
    ok: bool
    answers: dict[str, Answer] = Field(default_factory=dict)
    reason: str | None = None
    redactions: int = 0
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class Outcome:
    """What one judgment produced: answers and accounting, or the reason there are none."""

    answers: dict[str, Answer] | None
    reason: str | None
    attempts: int
    latency_ms: int = 0
    input_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class Settings:
    """Batch knobs. ``rate`` is requests per second across all workers."""

    workers: int = 8
    rate: float = 20.0
    attempts: int = 4
    cap: int = DEFAULT_CAP
    timeout: float = 30.0
    model: str = DEFAULT_MODEL


DEFAULT_SETTINGS = Settings()


# --- input files ---------------------------------------------------------------------------------


def _describe(error: ValidationError) -> str:
    """One ``<field>: <reason>`` per problem, instead of pydantic's internal type names."""
    parts: list[str] = []
    for problem in error.errors():
        where = ".".join(str(p) for p in problem["loc"]) or "value"
        parts.append(f"{where}: {problem['msg']}")
    return "; ".join(parts)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc.strerror or exc}") from exc


def load_items(path: Path) -> list[Item]:
    """Items from a JSONL file, one ``{"id": ..., "state": {...}}`` per line.

    Args:
        path: The JSONL file. Blank lines are skipped.

    Returns:
        The items in file order, ids normalised to strings.

    Raises:
        UsageError: A line is not JSON or not the item shape, an id repeats, or there are none.

    """
    items: list[Item] = []
    seen: set[str] = set()
    for number, line in enumerate(_read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        item = _parse_item(line, where=f"{path} line {number}")
        if item.id in seen:
            raise UsageError(f"{path} line {number}: duplicate id {item.id!r}")
        seen.add(item.id)
        items.append(item)
    if not items:
        raise UsageError(f"{path}: no items")
    return items


def _parse_item(line: str, *, where: str) -> Item:
    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise UsageError(f"{where}: not JSON ({exc})") from exc
    try:
        parsed = _ItemIn.model_validate(raw)
    except ValidationError as exc:
        raise UsageError(f"{where}: {_describe(exc)}") from exc
    return Item(id=str(parsed.id), state=parsed.state)


def parse_questions(raw: object) -> list[Question]:
    """Validate a decoded question list against the shapes Jev accepts.

    Args:
        raw: The decoded JSON: a non-empty list of question objects.

    Returns:
        The typed questions, in order.

    Raises:
        UsageError: The list is empty, a question is malformed, or an id repeats.

    Examples:
        >>> parse_questions([{"id": "bug", "type": "noul", "instructions": "Is `x` a bug?"}])[0].id
        'bug'

    """
    if not isinstance(raw, list) or not raw:
        raise UsageError("questions: need a non-empty JSON list")
    try:
        questions = _QUESTIONS.validate_python(raw)
    except ValidationError as exc:
        raise UsageError(f"questions: {_describe(exc)}") from exc
    ids = Counter(q.id for q in questions)
    repeated = sorted(qid for qid, n in ids.items() if n > 1)
    if repeated:
        raise UsageError(f"questions: duplicate question id {repeated[0]!r}")
    return questions


def load_questions(path: Path) -> list[Question]:
    """Questions from a JSON file holding a list; see ``parse_questions``.

    Raises:
        UsageError: The file is unreadable, not JSON, or not a valid question list.

    """
    try:
        raw = json.loads(_read_text(path))
    except ValueError as exc:
        raise UsageError(f"{path}: not JSON ({exc})") from exc
    try:
        return parse_questions(raw)
    except UsageError as exc:
        raise UsageError(f"{path}: {exc}") from exc


# --- key, endpoint, egress -----------------------------------------------------------------------


def load_key(env: Mapping[str, str], home: Path) -> tuple[str | None, str]:
    """Find the API key and say where it came from, or why there is none. Never logs the key.

    Args:
        env: The environment; ``TYPESAFE_API_KEY`` wins when set.
        home: The home directory holding ``.credentials/typesafe.key``.

    Returns:
        ``(key, "env" | "keyfile")``, or ``(None, reason)``.

    """
    value = env.get(KEY_ENV, "").strip()
    source = "env"
    if not value:
        value, source = _read_keyfile(home / KEYFILE)
        if not value:
            return None, source
    if not (value.isascii() and value.isprintable()):
        return None, f"{source}: api key is not printable ascii"
    return value, source


def _read_keyfile(path: Path) -> tuple[str, str]:
    try:
        info = path.stat()
    except FileNotFoundError:
        return "", f"no {KEY_ENV} and no keyfile"
    except OSError as exc:
        return "", f"keyfile unreadable: {exc.strerror or exc}"
    if os.name != "nt" and info.st_mode & KEYFILE_FORBIDDEN_BITS:
        return "", f"keyfile permissions: {path} must be mode 600"
    try:
        return path.read_text(encoding="utf-8-sig").strip(), "keyfile"
    except (OSError, UnicodeDecodeError):
        return "", "keyfile unreadable: save it as UTF-8 text"


def resolve_base_url(env: Mapping[str, str]) -> str:
    """Return the API base URL.

    An override is honoured only for a loopback host (the test seam), so a hostile environment
    cannot send the bearer token somewhere else.
    """
    override = env.get(BASE_URL_ENV, "").strip().rstrip("/")
    if override and _is_loopback(override):
        return override
    return DEFAULT_BASE_URL


def _is_loopback(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        return False


_SECRET_PATTERNS = tuple(
    re.compile(p, re.DOTALL)
    for p in (
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}",
        r"\bgithub_pat_[A-Za-z0-9_]{30,}",
        r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bAIza[0-9A-Za-z_-]{35}\b",
        r"\bsk-[A-Za-z0-9_-]{20,}",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    )
)
# Keep the label so a reader still sees what was there: "API_KEY=[REDACTED]".
_LABELLED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL)[A-Z0-9_]*\s*[=:]\s*)"
        r"[\"']?[^\s\"']{6,}",
        r"(\bauthorization:\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]{8,}",
        r"(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)[^/\s@]+(?=@)",
    )
)


def redact(text: str, key: str | None) -> tuple[str, int]:
    """Replace secrets in ``text`` with ``[REDACTED]``.

    Args:
        text: Any string about to leave the machine.
        key: The API key, redacted as a literal wherever it appears; None to skip.

    Returns:
        The redacted text and how many spans were replaced.

    Examples:
        >>> redact("token ghp_" + "x" * 36, key=None)
        ('token [REDACTED]', 1)

    """
    count = 0
    if key and key in text:
        count += text.count(key)
        text = text.replace(key, REDACTED)
    for pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        count += n
    for pattern in _LABELLED_PATTERNS:
        text, n = pattern.subn(lambda m: m.group(1) + REDACTED, text)
        count += n
    return text, count


def _cap(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    marker = f" [... {len(text) - cap} chars cut ...] "
    keep = max(0, cap - len(marker))
    head = keep // 2
    return text[:head] + marker + text[len(text) - (keep - head) :]


def prepare_state(
    state: Mapping[str, JsonValue], *, key: str | None, cap: int
) -> tuple[dict[str, JsonValue], int]:
    """Redact and cap every string in a state, keeping its structure.

    Args:
        state: The item's named fields; nested objects and lists are walked.
        key: The API key, redacted as a literal.
        cap: The longest a single string may be; longer ones keep their head and tail.

    Returns:
        The state to send, and the number of redacted spans.

    """
    counter = [0]

    def walk(value: JsonValue) -> JsonValue:
        if isinstance(value, str):
            text, n = redact(value, key)
            counter[0] += n
            return _cap(text, cap)
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return {k: walk(v) for k, v in state.items()}, counter[0]


# --- transport -----------------------------------------------------------------------------------


class RateLimiter:
    """Spaces request starts at most ``rate`` per second across every thread that shares it."""

    def __init__(
        self,
        rate: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise UsageError("rate must be positive")
        self._interval = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._next = -math.inf
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until this caller may start a request."""
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self._interval
        if start > now:
            self._sleep(start - now)


class JevClient:
    """A pooled, rate-limited Jev client whose failures are reasons, never exceptions.

    Use it as a context manager so the connection pool is closed. One instance is safe to share
    across the worker threads of a batch.
    """

    def __init__(
        self,
        *,
        key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        attempts: int = 4,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], object] = time.sleep,
        workers: int = 8,
    ) -> None:
        self._model = model
        self._attempts = max(1, attempts)
        self._limiter = limiter or RateLimiter(Settings().rate)
        self._sleep = sleep
        self._http = httpx2.Client(
            base_url=base_url,
            timeout=httpx2.Timeout(timeout),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            limits=httpx2.Limits(max_connections=workers, max_keepalive_connections=workers),
            trust_env=False,
        )

    def __enter__(self) -> JevClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection pool."""
        self._http.close()

    def ask(self, state: Mapping[str, JsonValue], questions: Sequence[Question]) -> Outcome:
        """Ask every question about one state in a single request, retrying transient failures.

        Args:
            state: The (already redacted) named fields.
            questions: The questions; their ids key the answers.

        Returns:
            The answers with accounting, or None answers and the last reason.

        """
        body = {
            "model": self._model,
            "state": dict(state),
            "questions": {q.id: q.to_api() for q in questions},
        }
        reason = "no attempt made"
        for attempt in range(1, self._attempts + 1):
            self._limiter.acquire()
            outcome, wait = self._attempt(body, questions, attempt)
            if outcome.answers is not None or wait is None or attempt == self._attempts:
                return outcome
            reason = outcome.reason or reason
            self._sleep(wait)
        return Outcome(None, reason, self._attempts)

    def _attempt(
        self, body: dict[str, Any], questions: Sequence[Question], attempt: int
    ) -> tuple[Outcome, float | None]:
        """One request. Returns the outcome and, when it is worth retrying, how long to wait."""
        backoff = float(2**attempt)
        started = time.monotonic()
        try:
            response = self._http.post(ENDPOINT, json=body)
        except httpx2.TimeoutException:
            return Outcome(None, "timeout", attempt), backoff
        except httpx2.TransportError as exc:
            return Outcome(None, f"connection error: {type(exc).__name__}", attempt), backoff
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code != HTTP_OK:
            reason = _http_reason(response)
            if response.status_code in RETRY_STATUSES:
                return Outcome(None, reason, attempt), _retry_after(response) or backoff
            return Outcome(None, reason, attempt), None
        return _parse_answers(response, questions, attempt=attempt, latency=latency), None


def _http_reason(response: httpx2.Response) -> str:
    detail = response.text.strip().replace("\n", " ")[:200]
    return f"http {response.status_code}" + (
        f": {detail}" if detail and response.status_code not in RETRY_STATUSES else ""
    )


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("retry-after", "").strip()
    try:
        seconds = float(value)
    except ValueError:
        return None
    return min(max(seconds, 0.0), MAX_RETRY_WAIT)


def _parse_answers(
    response: httpx2.Response, questions: Sequence[Question], *, attempt: int, latency: int
) -> Outcome:
    try:
        parsed = _ResponseIn.model_validate_json(response.content)
    except ValidationError as exc:
        return Outcome(None, f"bad response: {_describe(exc)}"[:300], attempt)
    missing = [q.id for q in questions if q.id not in parsed.answers]
    if missing:
        return Outcome(None, f"bad response: no answer for {', '.join(missing)}", attempt)
    answers = {q.id: _normalise(parsed.answers[q.id]) for q in questions}
    return Outcome(answers, None, attempt, latency, parsed.usage.input_tokens, parsed.model)


def _normalise(raw: _NoulIn | _ChoiceIn | _ScoreIn) -> Answer:
    if isinstance(raw, _NoulIn):
        return Answer(type=QuestionType.NOUL, value=raw.noul)
    if isinstance(raw, _ChoiceIn):
        return Answer(
            type=QuestionType.CHOICE,
            value=raw.choice,
            probabilities=raw.probabilities,
            confidence=raw.confidence,
        )
    return Answer(
        type=QuestionType.SCORE, value=raw.score, probabilities=raw.probabilities, confidence=raw.confidence
    )


# --- batch ---------------------------------------------------------------------------------------


def iter_judged(
    items: Sequence[Item],
    questions: Sequence[Question],
    *,
    client: JevClient,
    key: str | None,
    settings: Settings = DEFAULT_SETTINGS,
) -> Iterator[Row]:
    """Rows in input order, yielded as soon as each is ready, so a caller can write as it goes."""

    def one(item: Item) -> Row:
        state, redactions = prepare_state(item.state, key=key, cap=settings.cap)
        out = client.ask(state, questions)
        return Row(
            id=item.id,
            ok=out.answers is not None,
            answers=out.answers or {},
            reason=out.reason,
            redactions=redactions,
            attempts=out.attempts,
            latency_ms=out.latency_ms,
            input_tokens=out.input_tokens,
            model=out.model,
        )

    with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
        yield from pool.map(one, items)


def judge_all(
    items: Sequence[Item],
    questions: Sequence[Question],
    *,
    client: JevClient,
    key: str | None,
    settings: Settings = DEFAULT_SETTINGS,
) -> list[Row]:
    """One row per item, in input order; a failed item is a row with its reason.

    Args:
        items: What to judge.
        questions: Asked about every item, in one request per item.
        client: A shared ``JevClient``.
        key: The API key, redacted from every state as a literal.
        settings: Worker count and per-string cap (rate and retries live in the client).

    Returns:
        The rows.

    """
    return list(iter_judged(items, questions, client=client, key=key, settings=settings))


# --- summary -------------------------------------------------------------------------------------

# A noul or score whose answers spread less than this over at least FLAT_MIN_ROWS rows is not
# telling the items apart. That is a broken question until shown otherwise, never a consensus.
FLAT_STDEV = 0.02
FLAT_MIN_ROWS = 10
DEFAULT_BAND = (0.2, 0.8)
DEFAULT_MIN_CONFIDENCE = 0.6
# USD per million input tokens for jev-1.13 (docs.typesafe.ai/models, read 2026-10-01); output
# is free. Only used for the cost line, so a stale price misreports cost, never a judgment.
PRICE_PER_MTOK = 0.042


def summarize(
    rows: Sequence[Row],
    *,
    band: tuple[float, float] = DEFAULT_BAND,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, Any]:
    """Per-question distribution, the rows worth reading by hand, and which questions look flat.

    Args:
        rows: Rows from a run; failed rows are counted, not described.
        band: A noul strictly inside ``(low, high)`` is uncertain.
        min_confidence: A choice or score below this confidence is uncertain.

    Returns:
        ``{"rows", "answered", "failed", "questions": {qid: {...}}, "flat": [qid, ...]}``.

    """
    answered = [r for r in rows if r.ok]
    per: dict[str, list[tuple[str, Answer]]] = {}
    for row in answered:
        for qid, answer in row.answers.items():
            per.setdefault(qid, []).append((row.id, answer))
    questions = {
        qid: _describe_question(pairs, band=band, min_confidence=min_confidence)
        for qid, pairs in sorted(per.items())
    }
    return {
        "rows": len(rows),
        "answered": len(answered),
        "failed": [r.id for r in rows if not r.ok],
        "questions": questions,
        "flat": [qid for qid, s in questions.items() if s["flat"]],
    }


def _describe_question(
    pairs: Sequence[tuple[str, Answer]], *, band: tuple[float, float], min_confidence: float
) -> dict[str, Any]:
    qtype = pairs[0][1].type
    if qtype is QuestionType.NOUL:
        uncertain = [i for i, a in pairs if band[0] < float(a.value) < band[1]]
    else:
        uncertain = [i for i, a in pairs if a.confidence is not None and a.confidence < min_confidence]
    stats = _choice_stats(pairs) if qtype is QuestionType.CHOICE else _numeric_stats(pairs)
    return {"type": qtype.value, "n": len(pairs), **stats, "uncertain": uncertain}


def _choice_stats(pairs: Sequence[tuple[str, Answer]]) -> dict[str, Any]:
    counts = dict(sorted(Counter(str(a.value) for _, a in pairs).items()))
    return {"counts": counts, "flat": len(pairs) >= FLAT_MIN_ROWS and len(counts) == 1}


def _numeric_stats(pairs: Sequence[tuple[str, Answer]]) -> dict[str, Any]:
    values = [float(a.value) for _, a in pairs]
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.fmean(values), 4),
        "stdev": round(stdev, 4),
        "flat": len(values) >= FLAT_MIN_ROWS and stdev < FLAT_STDEV,
    }


# --- CLI -----------------------------------------------------------------------------------------

CommandResult = tuple[int, dict[str, Any], list[str]]


@dataclass(frozen=True)
class _Context:
    env: Mapping[str, str]
    home: Path
    sleep: Callable[[float], object]


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    stdout: IO[str] | None = None,
    sleep: Callable[[float], object] = time.sleep,
) -> int:
    """Run the CLI.

    Args:
        argv: Arguments without the program name; None reads ``sys.argv``.
        env: The environment; None uses ``os.environ``.
        home: The home directory for the keyfile; None uses ``Path.home()``.
        stdout: Where results go; diagnostics always go to stderr.
        sleep: The wait used between retries and by the rate limiter.

    Returns:
        0 yes (all answered / nothing flat / key present), 1 no, 2 usage or IO error.

    """
    args = _parser().parse_args(argv)
    ctx = _Context(
        env=os.environ if env is None else env, home=Path.home() if home is None else home, sleep=sleep
    )
    try:
        code, data, skipped = _COMMANDS[args.command](args, ctx)
    except UsageError as exc:
        print(f"jev_judge: {exc}", file=sys.stderr)
        code, data, skipped = 2, {"error": str(exc)}, []
    _emit(stdout or sys.stdout, args, code=code, data=data, skipped=skipped)
    return code


def _cmd_run(args: argparse.Namespace, ctx: _Context) -> CommandResult:
    key, why = load_key(ctx.env, ctx.home)
    if key is None:
        raise UsageError(
            f"no usable Jev key ({why}): set {KEY_ENV}, or put the key in "
            f"~/{KEYFILE.as_posix()} with mode 600"
        )
    items, questions = load_items(args.items), load_questions(args.questions)
    pilot = args.pilot if args.pilot and args.pilot > 0 else len(items)
    skipped = [item.id for item in items[pilot:]]
    settings = Settings(
        workers=args.workers,
        rate=args.rate,
        attempts=args.attempts,
        cap=args.cap,
        timeout=args.timeout,
        model=args.model,
    )
    started = time.monotonic()
    with _client(key, settings, ctx) as client:
        rows = _write_rows(
            args.out, iter_judged(items[:pilot], questions, client=client, key=key, settings=settings)
        )
    failed = [r.id for r in rows if not r.ok]
    tokens = sum(r.input_tokens for r in rows)
    data = {
        "rows": len(rows),
        "answered": len(rows) - len(failed),
        "failed": failed,
        "out": str(args.out),
        "input_tokens": tokens,
        "cost_usd": round(tokens * PRICE_PER_MTOK / 1_000_000, 6),
        "redactions": sum(r.redactions for r in rows),
        "models": sorted({r.model for r in rows if r.model}),
        "seconds": round(time.monotonic() - started, 2),
    }
    return (1 if failed else 0), data, skipped


def _client(key: str, settings: Settings, ctx: _Context) -> JevClient:
    return JevClient(
        key=key,
        base_url=resolve_base_url(ctx.env),
        model=settings.model,
        timeout=settings.timeout,
        attempts=settings.attempts,
        workers=settings.workers,
        limiter=RateLimiter(settings.rate, sleep=ctx.sleep),
        sleep=ctx.sleep,
    )


def _write_rows(path: Path, rows: Iterable[Row]) -> list[Row]:
    """Write each row as it arrives, so an interrupted run keeps what it already paid for."""
    written: list[Row] = []
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
                handle.flush()
                written.append(row)
                if len(written) % 100 == 0:
                    print(f"jev_judge: {len(written)} rows written", file=sys.stderr)
    except OSError as exc:
        raise UsageError(f"cannot write {path}: {exc.strerror or exc}") from exc
    return written


def _cmd_summarize(args: argparse.Namespace, _ctx: _Context) -> CommandResult:
    rows: list[Row] = []
    for number, line in enumerate(_read_text(args.rows).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(Row.model_validate_json(line))
        except ValidationError as exc:
            raise UsageError(f"{args.rows} line {number}: {_describe(exc)}") from exc
    summary = summarize(rows, band=(args.band[0], args.band[1]), min_confidence=args.min_confidence)
    return (1 if summary["flat"] else 0), summary, []


def _cmd_check_key(_args: argparse.Namespace, ctx: _Context) -> CommandResult:
    key, why = load_key(ctx.env, ctx.home)
    if key is None:
        return 1, {"present": False, "reason": why}, []
    return 0, {"present": True, "source": why}, []


_COMMANDS: dict[str, Callable[[argparse.Namespace, _Context], CommandResult]] = {
    "run": _cmd_run,
    "summarize": _cmd_summarize,
    "check-key": _cmd_check_key,
}


def _emit(
    out: IO[str], args: argparse.Namespace, *, code: int, data: dict[str, Any], skipped: list[str]
) -> None:
    if args.json:
        out.write(
            json.dumps({"ok": code == 0, "command": args.command, "data": data, "skipped": skipped}) + "\n"
        )
    elif args.json_bare:
        out.write(json.dumps(data) + "\n")
    elif code != EXIT_USAGE:
        out.write(_human(args.command, data, skipped) + "\n")


def _listing(ids: Sequence[str]) -> str:
    shown = ", ".join(ids[:LISTED_IDS])
    return shown + (f" ... (+{len(ids) - LISTED_IDS})" if len(ids) > LISTED_IDS else "")


def _human(command: str, data: dict[str, Any], skipped: list[str]) -> str:
    if command == "check-key":
        return f"key: present ({data['source']})" if data["present"] else f"key: none ({data['reason']})"
    if command == "run":
        line = (
            f"answered {data['answered']} of {data['rows']} in {data['seconds']}s; "
            f"{data['input_tokens']} input tokens (~${data['cost_usd']:.6f}); "
            f"rows in {data['out']}"
        )
        if data["failed"]:
            line += f"\nfailed: {_listing(data['failed'])}"
        if skipped:
            line += f"\npilot: {len(skipped)} items not judged"
        return line
    return _human_summary(data)


def _human_summary(data: dict[str, Any]) -> str:
    lines = [f"{data['rows']} rows, {data['answered']} answered, {len(data['failed'])} failed"]
    for qid, s in data["questions"].items():
        shape = s["counts"] if s["type"] == "choice" else f"mean {s['mean']} stdev {s['stdev']}"
        flag = "  FLAT - check the question" if s["flat"] else ""
        lines.append(f"  {qid} ({s['type']}, n={s['n']}): {shape}; {len(s['uncertain'])} uncertain{flag}")
        if s["uncertain"]:
            lines.append(f"    read by hand: {_listing(s['uncertain'])}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev_judge.py", description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="judge every item; one row per item in --out")
    run.add_argument("--items", required=True, type=Path, help='JSONL: {"id": ..., "state": {...}}')
    run.add_argument("--questions", required=True, type=Path, help="JSON list of questions")
    run.add_argument("--out", required=True, type=Path, help="JSONL rows, written as they arrive")
    run.add_argument("--pilot", type=int, default=0, help="judge only the first N items")
    run.add_argument("--workers", type=int, default=Settings.workers)
    run.add_argument("--rate", type=float, default=Settings.rate, help="requests per second")
    run.add_argument("--attempts", type=int, default=Settings.attempts)
    run.add_argument("--cap", type=int, default=Settings.cap, help="max characters per string")
    run.add_argument("--timeout", type=float, default=Settings.timeout, help="seconds per request")
    run.add_argument("--model", default=Settings.model, help="jev-latest, or a pinned jev-x.y.z")
    summ = sub.add_parser("summarize", help="distribution, uncertain rows, flat questions")
    summ.add_argument("--rows", required=True, type=Path)
    summ.add_argument(
        "--band",
        type=float,
        nargs=2,
        default=list(DEFAULT_BAND),
        metavar=("LOW", "HIGH"),
        help="a noul strictly between is uncertain",
    )
    summ.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help="a choice or score below this is uncertain",
    )
    check = sub.add_parser("check-key", help="is a usable key configured (never prints it)")
    for command in (run, summ, check):
        mode = command.add_mutually_exclusive_group()
        mode.add_argument("--json", action="store_true", help="{ok, command, data, skipped}")
        mode.add_argument("--json-bare", action="store_true", help="data only, also on failure")
    return parser


if __name__ == "__main__":
    sys.exit(main())
