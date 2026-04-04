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


def _metric_fragment(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in name)
    cleaned = cleaned.strip("_")
    return cleaned or "default"


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
        self._half_open_probe_in_flight = False
        self._metric_name = _metric_fragment(name)
        self._emit_metrics()

    def _emit_metrics(self) -> None:
        try:
            from backend.observability.metrics import metrics_registry

            metrics_registry.set_gauge(
                f"circuit_breaker_state_{self._metric_name}",
                {
                    CircuitState.CLOSED: 0.0,
                    CircuitState.HALF_OPEN: 0.5,
                    CircuitState.OPEN: 1.0,
                }[self._state],
            )
            metrics_registry.set_gauge(
                f"circuit_breaker_failures_{self._metric_name}",
                float(self._failure_count),
            )
            metrics_registry.set_gauge(
                f"circuit_breaker_successes_{self._metric_name}",
                float(self._success_count),
            )
            metrics_registry.set_gauge(
                f"circuit_breaker_probe_in_flight_{self._metric_name}",
                1.0 if self._half_open_probe_in_flight else 0.0,
            )
        except Exception:
            logger.debug("Failed to emit circuit-breaker metrics", exc_info=True)

    def _transition_state(
        self,
        new_state: CircuitState,
        *,
        opened_at: Optional[float] = None,
        log_level: int = logging.INFO,
        reason: str = "",
    ) -> None:
        if self._state != new_state:
            self._state = new_state
            if new_state == CircuitState.OPEN:
                self._opened_at = opened_at if opened_at is not None else time.monotonic()
                self._half_open_probe_in_flight = False
            elif new_state == CircuitState.HALF_OPEN:
                self._success_count = 0
                self._half_open_probe_in_flight = False
            else:
                self._opened_at = 0.0
                self._half_open_probe_in_flight = False

            message = f"Circuit '{self.name}' → {new_state.value}"
            if reason:
                message = f"{message} ({reason})"
            logger.log(log_level, message)
            try:
                from backend.observability.metrics import metrics_registry

                metrics_registry.increment(
                    f"circuit_breaker_transitions_total_{self._metric_name}"
                )
            except Exception:
                logger.debug(
                    "Failed to emit circuit-breaker transition counter",
                    exc_info=True,
                )
        self._emit_metrics()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> CircuitState:
        """Determine effective state (may auto-transition OPEN → HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._transition_state(
                    CircuitState.HALF_OPEN,
                    log_level=logging.INFO,
                    reason=f"cooldown expired after {elapsed:.1f}s",
                )
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            state = self._current_state_unlocked()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    return False
                self._half_open_probe_in_flight = True
                self._emit_metrics()
                return True
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            state = self._current_state_unlocked()
            if state == CircuitState.HALF_OPEN:
                self._half_open_probe_in_flight = False
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._failure_count = 0
                    self._success_count = 0
                    self._transition_state(
                        CircuitState.CLOSED,
                        log_level=logging.INFO,
                        reason=f"recovered after {self.success_threshold} successes",
                    )
                else:
                    self._emit_metrics()
            elif state == CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count = 0
                self._emit_metrics()

    def record_failure(self) -> None:
        """Record a failed call."""
        now = time.monotonic()
        with self._lock:
            state = self._current_state_unlocked()
            if state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._failure_count += 1
                self._success_count = 0
                self._transition_state(
                    CircuitState.OPEN,
                    opened_at=now,
                    log_level=logging.WARNING,
                    reason=f"probe failed, re-opening for {self.recovery_timeout:.0f}s",
                )
            elif state == CircuitState.CLOSED:
                self._failure_count += 1
                self._success_count = 0
                self._last_failure_time = now
                if self._failure_count >= self.failure_threshold:
                    self._transition_state(
                        CircuitState.OPEN,
                        opened_at=now,
                        log_level=logging.WARNING,
                        reason=f"hit {self._failure_count} consecutive failures",
                    )
                else:
                    self._emit_metrics()

    def get_status(self) -> dict:
        """Return a JSON-serializable status snapshot."""
        with self._lock:
            state = self._current_state_unlocked()
            result = {
                "name": self.name,
                "state": state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout,
                "probe_in_flight": self._half_open_probe_in_flight,
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
                probe_allowed = False
                if circuit_breaker:
                    probe_allowed = circuit_breaker.allow_request()
                if circuit_breaker and not probe_allowed:
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
                except Exception:
                    if circuit_breaker and probe_allowed:
                        circuit_breaker.record_failure()
                    raise

            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
