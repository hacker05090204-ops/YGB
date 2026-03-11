"""
Circuit Breaker + Retry with Exponential Backoff

Thread-safe circuit breaker that prevents cascading failures from slow
or unavailable dependencies. Integrates with the observability module
to emit state-change metrics.

States:
    CLOSED   → normal operation, requests pass through
    OPEN     → dependency failing, requests fail-fast
    HALF_OPEN → cooldown expired, allow one probe request
"""

import logging
import random
import threading
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("ygb.reliability.circuit_breaker")

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised when the circuit is OPEN and refusing requests."""

    def __init__(self, name: str, state: CircuitState, until: float):
        remaining = max(0.0, until - time.monotonic())
        super().__init__(
            f"Circuit '{name}' is {state.value} — "
            f"retry in {remaining:.1f}s"
        )
        self.name = name
        self.state = state
        self.retry_after_s = remaining


class CircuitBreaker:
    """Thread-safe circuit breaker.

    Args:
        name:             Human-readable name for logging/metrics.
        failure_threshold: Consecutive failures before opening. Default 5.
        recovery_timeout:  Seconds to wait before probing. Default 30.
        success_threshold: Successes in HALF_OPEN before closing. Default 2.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> CircuitState:
        """Determine effective state (may auto-transition OPEN → HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(
                    "Circuit '%s' → HALF_OPEN (cooldown expired after %.1fs)",
                    self.name, elapsed,
                )
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            state = self._current_state_unlocked()
            return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            state = self._current_state_unlocked()
            if state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        "Circuit '%s' → CLOSED (recovered after %d successes)",
                        self.name, self.success_threshold,
                    )
            elif state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        now = time.monotonic()
        with self._lock:
            state = self._current_state_unlocked()
            if state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                self._opened_at = now
                self._failure_count += 1
                logger.warning(
                    "Circuit '%s' → OPEN (probe failed, re-opening for %.0fs)",
                    self.name, self.recovery_timeout,
                )
            elif state == CircuitState.CLOSED:
                self._failure_count += 1
                self._last_failure_time = now
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = now
                    logger.warning(
                        "Circuit '%s' → OPEN (hit %d consecutive failures)",
                        self.name, self._failure_count,
                    )

    def get_status(self) -> dict:
        """Return a JSON-serializable status snapshot."""
        with self._lock:
            state = self._current_state_unlocked()
            result = {
                "name": self.name,
                "state": state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout,
            }
            if state == CircuitState.OPEN:
                result["retry_after_s"] = round(
                    max(0.0, self.recovery_timeout - (time.monotonic() - self._opened_at)),
                    1,
                )
            return result


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    jitter: bool = True,
    circuit_breaker: Optional[CircuitBreaker] = None,
    retryable_exceptions: tuple = (Exception,),
):
    """Decorator: retry a function with exponential backoff.

    Args:
        max_retries:          Maximum number of retry attempts.
        base_delay:           Initial delay in seconds.
        max_delay:            Maximum delay cap in seconds.
        jitter:               Add random jitter to prevent thundering herd.
        circuit_breaker:      Optional CircuitBreaker to check before each attempt.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                # Check circuit breaker
                if circuit_breaker and not circuit_breaker.allow_request():
                    raise CircuitBreakerError(
                        circuit_breaker.name,
                        circuit_breaker.state,
                        circuit_breaker._opened_at + circuit_breaker.recovery_timeout,
                    )

                try:
                    result = func(*args, **kwargs)
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    return result
                except retryable_exceptions as exc:
                    last_exc = exc
                    if circuit_breaker:
                        circuit_breaker.record_failure()

                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        if jitter:
                            delay *= 0.5 + random.random()
                        logger.warning(
                            "Retry %d/%d for %s after %.2fs: %s",
                            attempt + 1, max_retries,
                            func.__name__, delay, exc,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries, func.__name__, exc,
                        )

            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
