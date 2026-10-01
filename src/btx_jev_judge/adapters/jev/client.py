"""The Jev HTTP client: one pooled, rate-limited, retrying request per judged state."""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ...domain.enums import QuestionType
from ...domain.models import Answer, Outcome, Question, describe_validation_error
from ...domain.redaction import redact
from .limiter import RateLimiter

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

DEFAULT_BASE_URL = "https://api.typesafe.ai"
ENDPOINT = "/v1/systemone"
DEFAULT_MODEL = "jev-latest"
BASE_URL_ENV = "JEV_JUDGE_BASE_URL"
# Jev's documented limit is 40 requests/s (what RateLimiter exists to respect); stay well under it
# unless the caller says otherwise.
DEFAULT_RATE = 20.0
# Throttling and transient server or network trouble: worth asking again, since a judgment is a
# read-only request and re-sending it costs a fraction of a cent. Anything else (401, 422) would
# fail identically on every attempt.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
# Never sleep longer than this on one Retry-After; a server asking for more is better reported.
MAX_RETRY_WAIT = 60.0
# Most tries per judgment a caller may configure; beyond it a run is better stopped than retried.
MAX_ATTEMPTS = 10
# 2**7 already exceeds MAX_RETRY_WAIT; capping the exponent keeps the power from overflowing.
MAX_BACKOFF_EXPONENT = 7
HTTP_OK = 200
# Longest slice of an error body quoted in a failure reason.
REASON_DETAIL_CHARS = 200
# Longest "bad response" reason, so a huge validation report cannot flood a row.
BAD_RESPONSE_CHARS = 300


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


def resolve_base_url(env: Mapping[str, str]) -> str:
    """Return the API base URL.

    An override is honoured only for a loopback host (the test seam), so a hostile environment
    cannot send the bearer token somewhere else.

    Args:
        env: The environment to read ``JEV_JUDGE_BASE_URL`` from.

    Returns:
        The loopback override when valid, else the default API URL.

    Example:
        >>> resolve_base_url({"JEV_JUDGE_BASE_URL": "https://evil.example"})
        'https://api.typesafe.ai'
        >>> resolve_base_url({"JEV_JUDGE_BASE_URL": "http://127.0.0.1:8123/"})
        'http://127.0.0.1:8123'
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


@dataclass(frozen=True)
class JevSettings:
    """The per-batch knobs of a :class:`JevClient`.

    Args:
        model: Model name sent with every request.
        timeout: httpx's per-phase timeout in seconds (connect, read, write and pool wait each).
        attempts: Tries per judgment; values below one are treated as one.
        workers: Connection pool size; match the batch's worker count.
    """

    model: str = DEFAULT_MODEL
    timeout: float = 30.0
    attempts: int = 4
    workers: int = 8


class JevClient:
    """A pooled, rate-limited Jev client whose failures are reasons, never exceptions.

    Use it as a context manager so the connection pool is closed. One instance is safe to share
    across the worker threads of a batch.

    Args:
        key: The API key, sent as a bearer token.
        base_url: API root; the default is the public endpoint.
        settings: Model, timeout, attempts and pool size.
        limiter: Shared request spacing; one at ``DEFAULT_RATE`` when omitted.
        sleep: Blocking sleep between retries (injectable for tests).
    """

    def __init__(
        self,
        *,
        key: str,
        base_url: str = DEFAULT_BASE_URL,
        settings: JevSettings,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self._key = key
        self._model = settings.model
        self._attempts = max(1, settings.attempts)
        self._limiter = limiter or RateLimiter(DEFAULT_RATE)
        self._sleep = sleep
        self._http = httpx2.Client(
            base_url=base_url,
            timeout=httpx2.Timeout(settings.timeout),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            limits=httpx2.Limits(max_connections=settings.workers, max_keepalive_connections=settings.workers),
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
        for attempt in range(1, self._attempts):
            self._limiter.acquire()
            outcome, wait = self._attempt(body, questions, attempt)
            if wait is None:
                return outcome
            self._sleep(wait)
        # The last attempt is outside the loop: its wait would never be slept, and every path of
        # the function returns an Outcome.
        self._limiter.acquire()
        return self._attempt(body, questions, self._attempts)[0]

    def _attempt(
        self, body: dict[str, Any], questions: Sequence[Question], attempt: int
    ) -> tuple[Outcome, float | None]:
        """One request. Returns the outcome and, when it is worth retrying, how long to wait."""
        backoff = _backoff(attempt)
        started = time.monotonic()
        try:
            response = self._http.post(ENDPOINT, json=body)
        except httpx2.TimeoutException:
            return Outcome(None, "timeout", attempt), backoff
        except httpx2.TransportError as exc:
            return Outcome(None, f"connection error: {type(exc).__name__}", attempt), backoff
        except httpx2.RequestError as exc:
            # A bad Content-Encoding or a redirect loop fails the same way on every attempt.
            return Outcome(None, f"request error: {type(exc).__name__}", attempt), None
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code != HTTP_OK:
            reason = _http_reason(response, self._key)
            if response.status_code in RETRY_STATUSES:
                return Outcome(None, reason, attempt), _retry_after(response) or backoff
            return Outcome(None, reason, attempt), None
        return _parse_answers(response, questions, attempt=attempt, latency=latency), None


def _backoff(attempt: int) -> float:
    """Seconds to wait after a failed try: 2, 4, 8, ... never above ``MAX_RETRY_WAIT``."""
    exponent = min(attempt, MAX_BACKOFF_EXPONENT)
    return min(2.0**exponent, MAX_RETRY_WAIT)


def _http_reason(response: httpx2.Response, key: str) -> str:
    # The server may echo the request back, so what is quoted passes the same scrubber as the state.
    # Redact before cutting: a secret straddling the cut no longer matches its pattern, so its head
    # would be quoted verbatim.
    detail = redact(response.text.strip().replace("\n", " "), key)[0][:REASON_DETAIL_CHARS]
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


def _parse_answers(response: httpx2.Response, questions: Sequence[Question], *, attempt: int, latency: int) -> Outcome:
    try:
        parsed = _ResponseIn.model_validate_json(response.content)
    except ValidationError as exc:
        return Outcome(None, f"bad response: {describe_validation_error(exc)}"[:BAD_RESPONSE_CHARS], attempt)
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
    return Answer(type=QuestionType.SCORE, value=raw.score, probabilities=raw.probabilities, confidence=raw.confidence)


__all__ = [
    "BASE_URL_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_RATE",
    "ENDPOINT",
    "MAX_ATTEMPTS",
    "MAX_RETRY_WAIT",
    "RETRY_STATUSES",
    "JevClient",
    "JevSettings",
    "resolve_base_url",
]
