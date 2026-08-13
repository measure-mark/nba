import logging
import os
import time
from datetime import date

import redis

from download_manager import DownloadManager
from leagues.registry import LeagueRegistry
from scraper.sweep import LeagueSweeper
from status.store import StatusStore
from throttle.redis_throttle import RedisThrottle

log = logging.getLogger("scraper")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# The target: which seasons should exist locally. Ranges allowed, e.g.
# SEASONS=2015-2025 or SEASONS=1997-2010,2025. Unset means the current season.
#
# This is the whole job. At 19 requests/65s a deep backfill runs for days or weeks, so
# the scraper works through it continuously and only idles once it has caught up.
SEASONS = os.environ.get("SEASONS", "").strip()

# How long to wait before looking for new games, once there is no backlog left.
IDLE_POLL_SECONDS = int(os.environ.get("IDLE_POLL_SECONDS", 6 * 3600))

# A finished season's schedule never changes, so its pages are cached forever. The
# current season's pages gain games as they are played, so they go stale.
SCHEDULE_MAX_AGE_SECONDS = int(os.environ.get("SCHEDULE_MAX_AGE_SECONDS", 6 * 3600))


def parse_seasons(spec: str) -> list[int]:
    """"2015-2017,2025" -> [2015, 2016, 2017, 2025]."""
    seasons: list[int] = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            seasons.extend(range(lo, hi + 1))
        else:
            seasons.append(int(part))
    return sorted(set(seasons))


def seasons_for(league, today: date) -> list[int]:
    return parse_seasons(SEASONS) if SEASONS else [league.current_season(today)]


def build_sweepers(registry: LeagueRegistry, r) -> list[LeagueSweeper]:
    """One throttle instance per league, all sharing the single Redis window.

    They must share it: basketball-reference rate limits per IP, so scraping two
    leagues at once has to draw from one budget, not two.
    """
    status = StatusStore(r)
    leagues = registry.enabled()
    status.register_leagues([lg.key for lg in leagues])
    return [
        LeagueSweeper(
            lg,
            DownloadManager(lg, RedisThrottle(r, registry.host)),
            status,
        )
        for lg in leagues
    ]


def run_once(sweepers: list[LeagueSweeper], today: date | None = None) -> dict:
    """One pass over every league and season. Returns totals for the pass."""
    today = today or date.today()
    totals = {"new": 0, "cached": 0, "failed": 0}

    for sweeper in sweepers:
        league = sweeper.league
        for season in seasons_for(league, today):
            # Only the in-progress season's schedule can gain games.
            max_age = (
                SCHEDULE_MAX_AGE_SECONDS if season == league.current_season(today) else None
            )
            log.info("sweeping %s season %s", league.key, season)
            try:
                result = sweeper.sweep(season, schedule_max_age=max_age)
                log.info("%s %s: %s", league.key, season, result)
                for k in totals:
                    totals[k] += result.get(k, 0)
            except Exception:
                # One league failing must not stop the others or kill the daemon.
                log.exception("sweep failed for %s season %s", league.key, season)
                totals["failed"] += 1

    return totals


def run_forever(sweepers: list[LeagueSweeper], sleep=time.sleep) -> None:
    """Work the backlog down, then keep the current season fresh.

    There is one mode. While there is anything left to fetch the scraper keeps going
    with no pause beyond the rate limit; once a pass downloads nothing new it has caught
    up, and it idles until it is worth looking again. Daily incremental pulling is not a
    separate behaviour -- it is what this loop does once the backlog is empty.

    A pass that downloads nothing cannot spin, because idling is exactly the
    nothing-downloaded case; and a pass that downloads something is rate limited by
    definition. Progress survives restarts: the cache is on disk.
    """
    while True:
        totals = run_once(sweepers)
        if totals["new"]:
            log.info("backlog still draining: %s", totals)
            continue

        if totals["failed"]:
            log.warning("caught up, but %s request(s) failing; see get_status", totals["failed"])
        log.info("caught up; next check in %ss", IDLE_POLL_SECONDS)
        sleep(IDLE_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    registry = LeagueRegistry()
    r = redis.from_url(REDIS_URL)
    sweepers = build_sweepers(registry, r)
    today = date.today()
    log.info(
        "scraper up: targets=%s",
        {s.league.key: seasons_for(s.league, today) for s in sweepers},
    )
    run_forever(sweepers)


if __name__ == "__main__":
    main()
