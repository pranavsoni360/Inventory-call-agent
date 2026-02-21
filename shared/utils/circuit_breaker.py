# shared/utils/circuit_breaker.py
# Protects external API calls from cascading failures.
# States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
#
# Usage:
#   breaker = CircuitBreaker(name="gemini", failure_threshold=3, recovery_timeout=60)
#
#   @breaker
#   def call_gemini(prompt):
#       ...

import time
from functools import wraps
from shared.logging.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitOpenError(Exception):
    """Raised when circuit is OPEN and call is blocked."""
    pass


class CircuitBreaker:
    """
    Three-state circuit breaker.

    CLOSED    — normal operation, calls go through
    OPEN      — too many failures, calls blocked immediately
    HALF_OPEN — testing if service recovered, one call allowed through
    """

    def __init__(
        self,
        name:              str,
        failure_threshold: int   = 3,    # failures before opening
        recovery_timeout:  int   = 60,   # seconds before trying again
        success_threshold: int   = 2,    # successes in HALF_OPEN to close
    ):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.success_threshold = success_threshold

        self._state            = "CLOSED"
        self._failure_count    = 0
        self._success_count    = 0
        self._last_failure_ts  = None

    # ── State checks ──────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        if self._state == "OPEN":
            # Check if recovery timeout has passed
            if time.time() - self._last_failure_ts >= self.recovery_timeout:
                self._state         = "HALF_OPEN"
                self._success_count = 0
                logger.info(f"Circuit [{self.name}] → HALF_OPEN (testing recovery)")
        return self._state

    def is_available(self) -> bool:
        return self.state != "OPEN"

    # ── Call tracking ─────────────────────────────────────────────────────────

    def record_success(self):
        if self._state == "HALF_OPEN":
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state         = "CLOSED"
                self._failure_count = 0
                logger.info(f"Circuit [{self.name}] → CLOSED (recovered)")
        elif self._state == "CLOSED":
            self._failure_count = 0  # reset on success

    def record_failure(self):
        self._failure_count   += 1
        self._last_failure_ts  = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                f"Circuit [{self.name}] → OPEN "
                f"({self._failure_count} failures, "
                f"blocking for {self.recovery_timeout}s)"
            )

    # ── Decorator interface ───────────────────────────────────────────────────

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.is_available():
                raise CircuitOpenError(
                    f"Circuit [{self.name}] is OPEN — "
                    f"service unavailable, try again later."
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception as e:
                self.record_failure()
                raise
        return wrapper

    def call(self, func, *args, **kwargs):
        """Alternative to decorator — call directly."""
        if not self.is_available():
            raise CircuitOpenError(
                f"Circuit [{self.name}] is OPEN — service unavailable."
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            self.record_failure()
            raise

    def __repr__(self):
        return (
            f"CircuitBreaker(name={self.name!r}, "
            f"state={self._state}, "
            f"failures={self._failure_count})"
        )


# ── Pre-built breakers for your external APIs ─────────────────────────────────
# Import these directly in decision_engine.py and sarvam_stt/tts.py

gemini_breaker = CircuitBreaker(
    name="gemini",
    failure_threshold=3,
    recovery_timeout=60,
)

sarvam_stt_breaker = CircuitBreaker(
    name="sarvam-stt",
    failure_threshold=3,
    recovery_timeout=30,
)

sarvam_tts_breaker = CircuitBreaker(
    name="sarvam-tts",
    failure_threshold=3,
    recovery_timeout=30,
)
