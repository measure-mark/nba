"""Cached pages expire only when they can actually change.

Regression: download_if_new returned any file that existed on disk, with no age check.
Schedule pages were cached like everything else, so once the first sweep stored one the
scraper re-read a frozen copy forever and could never discover a game played since.
"""

import os
import time

import pytest

import download_manager as dm_module
from download_manager import DownloadManager
from leagues.config import HostConfig
from throttle.memory import InMemoryThrottle

LINK = "/wnba/teams/ATL/2026_games.html"
FILENAME = "wnba_teams_ATL_2026_games.html"


@pytest.fixture
def throttle():
    return InMemoryThrottle(HostConfig(max_requests=10, window_seconds=60, min_gap_seconds=0))


class FakeResponse:
    def __init__(self, content):
        self.status_code = 200
        self.content = content
        self.headers = {}


@pytest.fixture
def dm(monkeypatch, wnba, throttle):
    monkeypatch.setattr(
        dm_module.requests, "get", lambda url, timeout: FakeResponse(b"<html>fresh</html>")
    )
    return DownloadManager(wnba, throttle)


def _age_file(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_fresh_cache_is_reused(dm, wnba):
    dm.download_if_new(LINK)
    is_new, body = dm.download_if_new(LINK, max_age_seconds=3600)

    assert (is_new, body) == (False, b"<html>fresh</html>")


def test_stale_cache_is_refetched(dm, wnba):
    """The bug: without this, a new game played today is never discovered."""
    dm.download_if_new(LINK)
    _age_file(wnba.raw_dir / FILENAME, seconds=7200)

    is_new, _ = dm.download_if_new(LINK, max_age_seconds=3600)

    assert is_new is True


def test_no_max_age_means_cached_forever(dm, wnba):
    """Box scores and finished seasons are immutable -- re-fetching them would waste
    the rate limit budget that the backfill needs."""
    dm.download_if_new(LINK)
    _age_file(wnba.raw_dir / FILENAME, seconds=86400 * 365)

    is_new, _ = dm.download_if_new(LINK)

    assert is_new is False
