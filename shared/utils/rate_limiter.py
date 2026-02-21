# shared/utils/rate_limiter.py
# Token bucket rate limiter for external API calls.
# Prevents quota exhaustion on Gemini and Sarvam APIs.

import time
from threading import Lock
from shared.logging.logger import get_logger

logger = get_logger("rate_limiter")


class RateLimiter:
    """
    Token bucket algorithm.
    Allows burst up to max_tokens, refills at rate tokens/second.
    
    Usage:
        limiter = RateLimiter(name="gemini", max_tokens=10, refill_rate=0.25)
        if limiter.acquire():
            call_api()
        else:
            handle_rate_limited()
    """

    def __init__(self, name: str, max_tokens: int, refill_rate: float):
        """
        Args:
            name:        identifier for logging
            max_tokens:  max burst size
            refill_rate: tokens added per second (e.g. 0.25 = 1 token per 4 seconds)
        """
        self.name        = name
        self.max_tokens  = max_tokens
        self.refill_rate = refill_rate
        self._tokens     = float(max_tokens)
        self._last_refill = time.time()
        self._lock       = Lock()

    def _refill(self):
        now     = time.time()
        elapsed = now - self._last_refill
        added   = elapsed * self.refill_rate
        self._tokens      = min(self.max_tokens, self._tokens + added)
        self._last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens. Returns True if allowed, False if rate limited.
        Non-blocking — never waits.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            logger.warning(
                f"Rate limited [{self.name}] — "
                f"{self._tokens:.1f} tokens available, {tokens} needed"
            )
            return False

    def wait_and_acquire(self, tokens: int = 1, timeout: float = 10.0) -> bool:
        """
        Blocking version — waits up to timeout seconds.
        Returns True if acquired, False if timed out.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.acquire(tokens):
                return True
            time.sleep(0.1)
        return False

    def __repr__(self):
        return (
            f"RateLimiter(name={self.name!r}, "
            f"tokens={self._tokens:.1f}/{self.max_tokens}, "
            f"rate={self.refill_rate}/s)"
        )


# Pre-built limiters matching free tier quotas
# Gemini free tier: ~15 RPM = 1 per 4 seconds
gemini_limiter = RateLimiter(
    name="gemini",
    max_tokens=5,
    refill_rate=0.25,
)

# Sarvam: generous limits, keeping conservative
sarvam_limiter = RateLimiter(
    name="sarvam",
    max_tokens=10,
    refill_rate=1.0,
)
