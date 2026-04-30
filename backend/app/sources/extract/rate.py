"""Thread-safe rate limiting for source extraction model calls."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Small sliding-window limiter shared by PDF, PPTX, and image extraction."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = max(1, int(requests_per_minute))
        self._lock = threading.Lock()
        self._requests_this_minute = 0
        self._minute_start_time = 0.0

    def wait_if_needed(self) -> float:
        with self._lock:
            current_time = time.time()
            waited = 0.0

            if current_time - self._minute_start_time >= 60:
                self._requests_this_minute = 0
                self._minute_start_time = current_time

            if self._requests_this_minute >= self.requests_per_minute:
                wait_time = 60 - (current_time - self._minute_start_time)
                if wait_time > 0:
                    logger.warning(
                        "Rate limit reached (%s/min). Waiting %.1fs...",
                        self.requests_per_minute,
                        wait_time,
                    )
                    time.sleep(wait_time)
                    waited = wait_time
                    self._requests_this_minute = 0
                    self._minute_start_time = time.time()

            self._requests_this_minute += 1
            return waited

    def reset(self) -> None:
        with self._lock:
            self._requests_this_minute = 0
            self._minute_start_time = 0.0

    @property
    def remaining_requests(self) -> int:
        with self._lock:
            current_time = time.time()
            if current_time - self._minute_start_time >= 60:
                return self.requests_per_minute
            return max(0, self.requests_per_minute - self._requests_this_minute)

    @property
    def seconds_until_reset(self) -> float:
        with self._lock:
            elapsed = time.time() - self._minute_start_time
            if elapsed >= 60:
                return 0.0
            return 60 - elapsed


def create_rate_limiter(requests_per_minute: int) -> RateLimiter:
    return RateLimiter(requests_per_minute)
