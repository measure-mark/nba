"""A sweep reads box score links off schedule pages and records what it did.

Contract: one bad team code must not take down the sweep, and every league's status
must be written under its own keys.
"""

import json

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

BOX_SCORE_HTML = """
<html><body>
<div><strong>Officials:&nbsp;</strong>Ref A, Ref B, Ref C</div>
<table class="suppress_all sortable stats_table" id="box-ATL-game-basic">
  <caption>Atlanta Dream (1-0) Table</caption>
  <tr><th colspan="3">header</th></tr>
  <tr><th>Rk</th><th>MP</th><th>PTS</th></tr>
  <tr><th><a href="/wnba/players/h/howarrh01w.html">Rhyne Howard</a></th><td>32:11</td><td>21</td></tr>
  <tr><th><a href="/wnba/players/g/grayal01w.html">Allisha Gray</a></th><td>28:04</td><td>14</td></tr>
</table>
</body></html>
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
        if "/boxscores/pbp/" in link:
            return True, b'<html><table id="pbp"></table></html>'
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

    assert result["new"] == 4  # two box scores plus their two PBP pages
    assert result["boxscores"] == {"new": 2, "cached": 0, "failed": 0}
    assert result["pbp"] == {"new": 2, "cached": 0, "failed": 0}
    assert sw.status.get_pull("wnba", "boxscores")["files_new"] == "2"
    assert sw.status.get_pull("wnba", "pbp")["files_new"] == "2"
    assert sw.status.get_pull("nba", "boxscores") == {}
    assert sw.status.get_inflight("wnba") is None  # cleared when the sweep ends


def test_every_request_goes_through_the_throttle(sweeper):
    """The whole point of the shared budget: no request may bypass the limiter."""
    sw, downloader = sweeper
    sw.sweep(season=2026)

    assert downloader.throttle.status()["in_window"] == len(downloader.requested)


def test_invalid_pbp_page_is_recorded_without_stopping_the_sweep(sweeper):
    sw, downloader = sweeper
    original = downloader.download_if_new

    def missing_table(link, **kwargs):
        if "/boxscores/pbp/" in link:
            downloader.requested.append(link)
            downloader.throttle.reserve()
            return True, b"<html>not a PBP page</html>"
        return original(link, **kwargs)

    downloader.download_if_new = missing_table
    result = sw.sweep(season=2026)

    assert result["pbp"] == {"new": 0, "cached": 0, "failed": 2}
    assert "missing table#pbp" in sw.status.get_pull("wnba", "pbp")["last_error"]


def test_aggregate_builds_official_map_for_normal_scraper_path(sweeper, wnba):
    sw, _ = sweeper
    wnba.raw_dir.mkdir(parents=True, exist_ok=True)
    (wnba.raw_dir / "wnba_boxscores_202605170ATL.html").write_text(BOX_SCORE_HTML)

    assert sw.aggregate() == (2, 1)

    official_map = json.loads((wnba.data_root / "official_map.json").read_text())
    assert official_map == {"Ref A": 0, "Ref B": 1, "Ref C": 2}
    assert sw.status.get_aggregation("wnba", "official_map")["rows_out"] == "3"
