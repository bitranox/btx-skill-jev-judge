"""Request spacing shared by every worker thread of a batch."""

from __future__ import annotations

import math
import threading
import time
from typing import TYPE_CHECKING

from ...domain.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Callable


class RateLimiter:
    """Spaces request starts at most ``rate`` per second across every thread that shares it.

    A thread pool alone would exceed Jev's documented limit (see ``DEFAULT_RATE``), so one limiter
    is shared by all workers.

    Args:
        rate: Request starts allowed per second; must be positive.
        clock: Monotonic clock in seconds (injectable for tests).
        sleep: Blocking sleep (injectable for tests).

    Raises:
        InputError: ``rate`` is not positive.

    Example:
        >>> waits: list[float] = []
        >>> limiter = RateLimiter(10.0, clock=lambda: 0.0, sleep=waits.append)
        >>> limiter.acquire()
        >>> limiter.acquire()
        >>> [round(w, 3) for w in waits]
        [0.1]
    """

    def __init__(
        self,
        rate: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise InputError("rate must be positive")
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


__all__ = ["RateLimiter"]
