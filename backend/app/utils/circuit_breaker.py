"""
Circuit breaker for external API calls (Gemini LLM).

States: CLOSED (normal) → OPEN (fail-fast after N failures) → HALF_OPEN (one trial) → CLOSED
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
    """Raised when the circuit breaker is OPEN (fail-fast)."""
    pass


class CircuitBreaker:
    """Async-safe circuit breaker with CLOSED → OPEN → HALF_OPEN states."""

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
        # Lock serialises state transitions; actual API call runs outside the lock.
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, coro):
        """
        Execute an awaitable through the circuit breaker.

        Raises CircuitOpenError immediately if the circuit is OPEN.
        Resets to CLOSED on success; increments failure count and may trip on failure.
        """
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
                # Allow one trial; set OPEN now so concurrent requests still fail fast.
                # Bump _last_failure_time so the state property doesn't re-transition immediately.
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
                logger.info(
                    f"[{self.name}] HALF_OPEN → sending one probe request"
                )

        try:
            result = await coro
        except Exception as exc:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[{self.name}] Call failed "
                    f"({self._failure_count}/{self.failure_threshold}): {exc}"
                )
            raise

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
