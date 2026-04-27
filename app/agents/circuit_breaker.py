"""
Circuit-breaker wrapper for LLM calls in SentinelFlow-AIOps.

Tracks consecutive failures against the OpenAI / LangChain layer and
opens the circuit (returns fallback immediately) when the failure count
exceeds the threshold.  After a configurable cooldown the circuit enters
half-open state and allows one probe request through.
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from threading import Lock
from typing import Any, Callable


logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing fast
    HALF_OPEN = "half_open"  # Probe allowed


class CircuitBreaker:
    """
    Simple thread-safe circuit breaker.

    Args:
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds to wait before probing again.
        name: Human-readable label (for logging).
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        name: str = "circuit",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._lock = Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._resolved_state()

    def _resolved_state(self) -> CircuitState:
        """Internal – must be called under self._lock."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("[%s] circuit entering half-open state", self.name)
        return self._state

    # ------------------------------------------------------------------
    # Call wrapping
    # ------------------------------------------------------------------
    def call(self, fn: Callable[[], Any], fallback: Any = None) -> Any:
        """
        Execute *fn* if the circuit is closed/half-open.
        Returns *fallback* immediately if the circuit is open.
        """
        with self._lock:
            current = self._resolved_state()
            if current == CircuitState.OPEN:
                logger.warning("[%s] circuit open – returning fallback", self.name)
                return fallback

        try:
            result = fn()
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            return fallback

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("[%s] probe succeeded – closing circuit", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            logger.warning(
                "[%s] failure %d/%d: %s",
                self.name,
                self._failure_count,
                self.failure_threshold,
                exc,
            )
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error("[%s] circuit OPENED after %d failures", self.name, self._failure_count)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._resolved_state().value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_seconds": self.recovery_timeout,
            }


# Singleton circuit breaker for the LLM layer
llm_circuit = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=30.0,
    name="llm_openai",
)
