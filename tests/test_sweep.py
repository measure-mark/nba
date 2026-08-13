"""A sweep reads box score links off schedule pages and records what it did.

Contract: one bad team code must not take down the sweep, and every league's status
must be written under its own keys.
"""

import fakeredis
import pytest

from download_manager import DownloadManager
from leagues.config import HostConfig
from scraper.sweep import LeagueSweeper
from status.store import StatusStore
from throttle.memory import InMemoryThrottle

SCHEDULE_HTML = """
<html><body><table id="games">
  <tr><td><a href="/wnba/boxscores/202605170ATL.html">Final</a></td></tr>
  <tr><td><a href="/wnba/boxscores/202605190ATL.html">Final</a></td></tr>
  <tr><td><a href="/wnba/players/h/howarrh01.html">Rhyne Howard</a></td></tr>
  <tr><td><a href="/boxscores/202105160TOR.html">an NBA game</a></td></tr>
</table></body></html>
"""


class StubDownloader(DownloadManager):
    """Serves canned pages, and 404s for team codes we say don't exist."""

    def __init__(self, league, throttle, missing_teams=()):
        super().__init__(league, throttle)
        self.missing = set(missing_teams)
        self.requested = []

    def download_if_new(self, link, verbose=False, max_retries=3, max_age_seconds=None):
        self.requested.append(link)
        self.throttle.reserve()
        if any(f"/teams/{t}/" in link for t in self.missing):
            raise RuntimeError(f"404 for {link}")
        if "/teams/" in link:
            return True, SCHEDULE_HTML.encode()
        return True, b"<html>box score</html>"


@pytest.fixture
def sweeper(wnba):
    r = fakeredis.FakeStrictRedis()
    throttle = InMemoryThrottle(HostConfig(max_requests=500, window_seconds=60, min_gap_seconds=0))
    downloader = StubDownloader(wnba, throttle, missing_teams={"GSV"})
    return LeagueSweeper(wnba, downloader, StatusStore(r)), downloader


def test_sweep_collects_only_this_leagues_box_scores(sweeper, wnba):
    """Schedule pages link to players and to other leagues; only WNBA box scores count."""
    sw, downloader = sweeper
    links, _ = sw.fetch_schedules(season=2026)

    assert links == [
        "/wnba/boxscores/202605170ATL.html",
        "/wnba/boxscores/202605190ATL.html",
    ]


def test_a_404_team_is_skipped_not_fatal(sweeper):
    """The WNBA team list was assembled without access to basketball-reference, so a
    wrong or retired code is likely. It must degrade to a recorded skip."""
    sw, _ = sweeper
    links, skipped = sw.fetch_schedules(season=2026)

    assert len(skipped) == 1 and "GSV" in skipped[0]
    assert links, "the other teams' pages should still have been read"
    assert "404" in sw.status.get_pull("wnba", "schedules")["last_error"]


def test_sweep_records_status_under_its_own_league(sweeper, wnba):
    sw, _ = sweeper
    result = sw.sweep(season=2026)

    assert result["new"] == 2  # two distinct box scores, deduped across 12 team pages
    assert sw.status.get_pull("wnba", "boxscores")["files_new"] == "2"
    assert sw.status.get_pull("nba", "boxscores") == {}
    assert sw.status.get_inflight("wnba") is None  # cleared when the sweep ends


def test_every_request_goes_through_the_throttle(sweeper):
    """The whole point of the shared budget: no request may bypass the limiter."""
    sw, downloader = sweeper
    sw.sweep(season=2026)

    assert downloader.throttle.status()["in_window"] == len(downloader.requested)
