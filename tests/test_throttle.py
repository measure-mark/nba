"""Rate limiter behaviour.

The limit is per-IP against one host, so it is one budget shared by every league; and
it must not be possible for the limiter itself to hang.
"""

import fakeredis
import pytest

from leagues.config import HostConfig
from throttle.memory import InMemoryThrottle
from throttle.redis_throttle import KEY, RedisThrottle


class FakeClock:
    """A clock the test drives, so sleeps advance time without real waiting."""

    def __init__(self, t=1000.0):
        self.t = t
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


@pytest.fixture
def host():
    return HostConfig(max_requests=3, window_seconds=10, min_gap_seconds=0)


def test_window_caps_requests(host):
    """Business rule: no more than max_requests may be claimed within the window."""
    clock = FakeClock()
    t = InMemoryThrottle(host, clock=clock, sleep=clock.sleep)

    for _ in range(host.max_requests):
        t.reserve()
    assert t.status()["in_window"] == host.max_requests

    t.reserve()
    # Waited for the oldest entry to age out, rather than exceeding the window.
    assert clock.sleeps == [10.0]
    assert t.status()["in_window"] <= host.max_requests


def test_backward_clock_step_does_not_hang(host):
    """Regression: the original throttle used naive wall-clock datetime.now(), so a
    backward clock step (NTP correction, DST fall-back, container suspend/resume) left
    entries un-purgeable and spun `while len(self)>=19: sleep(1)` for the length of the
    jump -- an hour, on a DST fall-back.

    A correct limiter terminates in a bounded number of sleeps even if handed a clock
    that jumps backwards.
    """
    clock = FakeClock()
    t = InMemoryThrottle(host, clock=clock, sleep=clock.sleep)
    for _ in range(host.max_requests):
        t.reserve()

    clock.t -= 3600  # the clock steps back an hour
    clock.sleeps.clear()

    t.reserve()
    assert len(clock.sleeps) <= 2, f"spun {len(clock.sleeps)} times instead of terminating"


def test_min_gap_between_requests():
    """Business rule: consecutive requests are spaced, not just capped per window."""
    host = HostConfig(max_requests=100, window_seconds=60, min_gap_seconds=3)
    clock = FakeClock()
    t = InMemoryThrottle(host, clock=clock, sleep=clock.sleep)

    t.reserve()
    t.reserve()
    assert clock.sleeps == [3.0]


def test_redis_window_is_shared_across_leagues(host):
    """The requirement that motivated Redis: NBA and WNBA scraping concurrently must
    draw from ONE budget, because basketball-reference limits per IP, not per league.
    """
    r = fakeredis.FakeStrictRedis()
    nba = RedisThrottle(r, host, sleep=lambda s: None)
    wnba = RedisThrottle(r, host, sleep=lambda s: None)

    nba.reserve()
    nba.reserve()
    wnba.reserve()

    # One key, three entries -- not two independent windows of three.
    assert r.zcard(KEY) == host.max_requests
    assert wnba.status()["in_window"] == host.max_requests
    assert nba.status()["seconds_until_slot"] > 0


def test_redis_reserve_is_atomic_check_and_claim(host):
    """Contract: reserve() claims the slot in the same round trip that checks it, so two
    processes cannot both conclude the last slot is free."""
    r = fakeredis.FakeStrictRedis()
    a = RedisThrottle(r, host, sleep=lambda s: None)
    b = RedisThrottle(r, host, sleep=lambda s: None)

    a.reserve()
    assert r.zcard(KEY) == 1
    b.reserve()
    assert r.zcard(KEY) == 2
