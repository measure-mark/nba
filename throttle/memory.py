import time
from collections import deque

from leagues.config import HostConfig
from throttle.base import Throttle


class InMemoryThrottle(Throttle):
    """Sliding-window limiter for a single process.

    Used in tests and for one-off local runs. The scraper uses RedisThrottle, because
    an in-memory window resets on restart and cannot be shared across processes.

    The clock is `time.monotonic`, not wall time. The original implementation used
    naive datetime.now(), which meant a backward clock step (NTP correction, DST
    fall-back, container suspend/resume) left queued timestamps in the future, the
    purge never fired, and the wait loop spun for the duration of the jump. Monotonic
    time cannot go backwards, so that failure is impossible by construction.

    It also sleeps for exactly as long as a slot actually needs, rather than polling
    once a second.
    """

    def __init__(self, host: HostConfig, clock=time.monotonic, sleep=time.sleep):
        self.host = host
        self._clock = clock
        self._sleep = sleep
        self.d = deque()

    def reserve(self) -> None:
        while True:
            now = self._clock()
            self._purge(now)
            wait = self._wait_needed(now)
            if wait <= 0:
                self.d.append(now)
                return
            self._sleep(wait)

    def status(self) -> dict:
        now = self._clock()
        self._purge(now)
        return {
            "in_window": len(self.d),
            "capacity": self.host.max_requests,
            "seconds_until_slot": max(self._wait_needed(now), 0.0),
        }

    def _purge(self, now: float) -> None:
        horizon = now - self.host.window_seconds
        while self.d and self.d[0] <= horizon:
            self.d.popleft()

    def _wait_needed(self, now: float) -> float:
        """Seconds until a slot is free. Zero or less means go now."""
        if len(self.d) >= self.host.max_requests:
            return self.d[0] + self.host.window_seconds - now
        if self.d:
            return self.d[-1] + self.host.min_gap_seconds - now
        return 0.0
