"""A minimal circuit breaker.

When a provider starts failing, continuing to send traffic to it turns one
broken dependency into a queue of stalled requests holding connections and
worker slots. The breaker fails fast instead, and lets the Model Gateway move
to the next candidate immediately.

In-process state is deliberate for M0: one API instance, no coordination cost.
Shared state across instances belongs with the distributed rate limiter (M6).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Fails fast after ``failure_threshold`` consecutive failures."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if reset_seconds <= 0:
            raise ValueError("reset_seconds must be > 0")
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock() - self._opened_at >= self._reset_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def allows_request(self) -> bool:
        """True when a call may be attempted."""
        return self.state is not CircuitState.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            # The probe failed: start the cool-down window again.
            self._opened_at = self._clock()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = self._clock()

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None
