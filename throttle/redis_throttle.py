import time
import uuid

from leagues.config import HostConfig
from throttle.base import Throttle

# Purge, count and reserve in one script so the check and the claim are atomic: two
# scraper processes cannot both decide the last slot is theirs.
#
# Scores come from Redis's own TIME, not the caller's clock, so host clock skew and
# backward clock steps cannot corrupt the window no matter how many machines take part.
#
# Each member is "<timestamp_ms>-<token>" so the timestamp can be read back from the
# member itself. That avoids ZRANGE ... WITHSCORES, which real Redis returns as a flat
# array but fakeredis returns as nested tables -- writing against either shape would
# make the tests prove the wrong thing. Plain ZRANGE agrees across both.
#
# Returns 0 when the slot is claimed, otherwise the milliseconds to wait.
_RESERVE_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local max_requests = tonumber(ARGV[2])
local min_gap_ms = tonumber(ARGV[3])
local token = ARGV[4]

local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)

local wait = 0
if redis.call('ZCARD', key) >= max_requests then
    local oldest = redis.call('ZRANGE', key, 0, 0)
    wait = tonumber(string.match(oldest[1], '^(%d+)')) + window_ms - now_ms
else
    local newest = redis.call('ZRANGE', key, -1, -1)
    if newest[1] then
        wait = tonumber(string.match(newest[1], '^(%d+)')) + min_gap_ms - now_ms
    end
end

if wait > 0 then
    return wait
end

redis.call('ZADD', key, now_ms, now_ms .. '-' .. token)
redis.call('PEXPIRE', key, window_ms * 2)
return 0
"""

_STATUS_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local oldest = redis.call('ZRANGE', key, 0, 0)
local oldest_ms = 0
if oldest[1] then
    oldest_ms = tonumber(string.match(oldest[1], '^(%d+)'))
end
return {redis.call('ZCARD', key), oldest_ms, now_ms}
"""

KEY = "br:ratelimit:requests"


class RedisThrottle(Throttle):
    """Sliding-window limiter shared by every league and every process.

    One key, deliberately: the limit is enforced per-IP against one host, so NBA, WNBA
    and NCAA all draw from the same budget. Scraping two leagues at once must not mean
    two limits' worth of traffic.

    Persisting the window is also what makes the scraper safe to restart. With the
    window in process memory, a container restart reset it to zero and the scraper
    immediately burst a full window of requests -- straight into a 429, which crashed
    it, which restarted it, which burst again.

    If Redis is unreachable the redis client raises and that propagates. This fails
    closed on purpose: never fall back to unthrottled scraping.
    """

    def __init__(self, redis_client, host: HostConfig, sleep=time.sleep):
        self.host = host
        self._sleep = sleep
        self._reserve = redis_client.register_script(_RESERVE_LUA)
        self._status = redis_client.register_script(_STATUS_LUA)

    def reserve(self) -> None:
        args = [
            int(self.host.window_seconds * 1000),
            self.host.max_requests,
            int(self.host.min_gap_seconds * 1000),
        ]
        while True:
            wait_ms = self._reserve(keys=[KEY], args=[*args, uuid.uuid4().hex])
            if wait_ms <= 0:
                return
            self._sleep(wait_ms / 1000)

    def status(self) -> dict:
        count, oldest_ms, now_ms = self._status(
            keys=[KEY], args=[int(self.host.window_seconds * 1000)]
        )
        full = count >= self.host.max_requests
        wait_ms = (oldest_ms + self.host.window_seconds * 1000 - now_ms) if full else 0
        return {
            "in_window": count,
            "capacity": self.host.max_requests,
            "window_seconds": self.host.window_seconds,
            "seconds_until_slot": max(wait_ms, 0) / 1000,
        }
