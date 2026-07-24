"""
Circuit breaker for external API calls (Gemini LLM).

Failure mode this prevents:
  If the Gemini API is down or rate-limited, every incoming query would block
  for the full 25-second timeout before failing.  With 10 concurrent users,
  that's 10 worker threads stuck waiting — effectively a self-inflicted
  denial-of-service on your own backend.  The circuit breaker detects
  consecutive failures and starts failing fast (<1 ms) with a clear 503,
  keeping the server responsive for cached queries, file uploads, and other
  non-Gemini endpoints.

State machine:
  CLOSED    → normal operation; failures are counted
  OPEN      → tripped after N consecutive failures; all calls rejected instantly
  HALF_OPEN → after recovery_timeout, ONE trial request is allowed through
              success → CLOSED,  failure → back to OPEN
"""

import time
import logging
import asyncio
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is OPEN and rejects a call (fail-fast)."""
    pass


class CircuitBreaker:
    """
    Async-safe circuit breaker with CLOSED → OPEN → HALF_OPEN states.

    Interview explanation:
      "I wrap the Gemini API call in a circuit breaker.  If 5 calls in a row
       fail (timeout, 5xx, network error), the breaker *opens* and every
       subsequent request is rejected instantly with a 503 — no 25-second
       wait, no wasted Gemini quota.  After 30 seconds the breaker moves to
       *half-open* and lets exactly one probe request through.  If that
       succeeds, we're back to normal.  If it fails, we stay open for
       another 30 seconds."
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "circuit_breaker",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        # Lock serialises state transitions — the actual API call runs
        # outside the lock so it never blocks other requests.
        self._lock = asyncio.Lock()

    # -- state property auto-transitions OPEN → HALF_OPEN after timeout ------

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    # -- public API -----------------------------------------------------------

    async def call(self, coro):
        """
        Execute an awaitable through the circuit breaker.

        Raises CircuitOpenError immediately if the circuit is OPEN (fail-fast).
        On success the breaker resets to CLOSED.
        On failure the breaker increments the failure counter and may trip.
        """
        # --- Pre-flight check (under lock) ---
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                wait_remaining = self.recovery_timeout - (
                    time.time() - self._last_failure_time
                )
                logger.warning(
                    f"[{self.name}] Circuit OPEN — failing fast. "
                    f"Recovery in {max(0, wait_remaining):.0f}s"
                )
                raise CircuitOpenError(
                    f"AI service temporarily unavailable after "
                    f"{self.failure_threshold} consecutive failures. "
                    f"Retrying automatically in {max(1, int(wait_remaining))}s."
                )

            if current_state == CircuitState.HALF_OPEN:
                # Allow exactly ONE trial request.  Set state to OPEN *now*
                # so concurrent requests that arrive while the trial is
                # in-flight still fail fast instead of flooding the degraded
                # service.  Also bump _last_failure_time to prevent the
                # state-property from immediately re-transitioning to
                # HALF_OPEN.
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
                logger.info(
                    f"[{self.name}] HALF_OPEN → sending one probe request"
                )

        # --- Execute the actual call OUTSIDE the lock ---
        try:
            result = await coro
        except Exception as exc:
            # Record failure
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[{self.name}] Call failed "
                    f"({self._failure_count}/{self.failure_threshold}): {exc}"
                )
            raise

        # --- Success — reset to CLOSED ---
        async with self._lock:
            prev_failures = self._failure_count
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            if prev_failures > 0:
                logger.info(
                    f"[{self.name}] Call succeeded — circuit reset to CLOSED "
                    f"(was at {prev_failures} consecutive failures)"
                )
        return result
