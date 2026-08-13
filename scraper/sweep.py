import json
import time
import uuid

import requests
from bs4 import BeautifulSoup

from artifact_makers.aggregate import aggregate_box_scores
from download_manager import DownloadManager
from leagues.config import LeagueConfig
from status.store import StatusStore

# What a failed fetch actually looks like: a network problem, or a bad status code
# (DownloadManager raises RuntimeError for those). Deliberately NOT bare Exception --
# swallowing TypeError/AttributeError here turns a coding mistake into a silent
# "skipped team", which is exactly how a broken sweep looks like an empty season.
FETCH_ERRORS = (requests.RequestException, RuntimeError, OSError)


class LeagueSweeper:
    """One pass over a league: refresh schedules, fetch missing box scores, aggregate.

    Box score links are read straight off the team schedule pages rather than
    reconstructed from a date range, so we only ever ask for games that exist.
    """

    def __init__(self, league: LeagueConfig, downloader: DownloadManager, status: StatusStore):
        self.league = league
        self.downloader = downloader
        self.status = status

    def teams(self) -> list[str]:
        """Configured team codes, or the keys of team_map.json when we already have one."""
        if self.league.teams:
            return list(self.league.teams)
        team_map = self.league.data_root / "team_map.json"
        if team_map.exists():
            return sorted(json.loads(team_map.read_text()))
        return []

    def sweep(self, season: int, verbose: bool = False, schedule_max_age=None) -> dict:
        league = self.league
        job_id = uuid.uuid4().hex
        self.status.mark_inflight(league.key, job_id)
        try:
            links, skipped = self.fetch_schedules(season, verbose, schedule_max_age)
            fetched = self.fetch_box_scores(links, verbose)
            rows, files = self.aggregate()
            return {"job": job_id, "skipped_teams": skipped, **fetched, "rows": rows, "files": files}
        finally:
            self.status.clear_inflight(league.key)

    def fetch_schedules(
        self, season: int, verbose: bool = False, max_age_seconds=None
    ) -> tuple[list[str], list[str]]:
        """Download each team's schedule page and collect the box score links on them.

        max_age_seconds forces a re-fetch of pages older than that, which is how an
        in-progress season's new games get discovered. Finished seasons pass None and
        are read from cache forever.

        A team whose page 404s (a retired or mistyped code) is recorded and skipped --
        one bad code must not take down the whole sweep.
        """
        league = self.league
        self.status.pull_started(league.key, "schedules")
        new = cached = 0
        box_links: set[str] = set()
        skipped: list[str] = []

        for team in self.teams():
            link = league.links.schedule_link(team, season)
            try:
                is_new, page = self.downloader.download_if_new(
                    link, verbose=verbose, max_age_seconds=max_age_seconds
                )
            except FETCH_ERRORS as exc:
                skipped.append(f"{team}: {exc}")
                self.status.pull_failed(league.key, "schedules", f"{team}: {exc}")
                continue
            new, cached = (new + 1, cached) if is_new else (new, cached + 1)
            box_links.update(self.box_score_links(page))

        self.status.pull_finished(league.key, "schedules", new, cached)
        return sorted(box_links), skipped

    def box_score_links(self, page: bytes) -> list[str]:
        soup = BeautifulSoup(page, "html.parser")
        return [
            a["href"]
            for a in soup.find_all("a", href=True)
            if self.league.links.is_boxscore_link(a["href"])
        ]

    def fetch_box_scores(self, links: list[str], verbose: bool = False) -> dict:
        league = self.league
        self.status.pull_started(league.key, "boxscores")
        new = cached = failed = 0

        for link in links:
            try:
                is_new, _ = self.downloader.download_if_new(link, verbose=verbose)
            except FETCH_ERRORS as exc:
                failed += 1
                self.status.pull_failed(league.key, "boxscores", f"{link}: {exc}")
                continue
            new, cached = (new + 1, cached) if is_new else (new, cached + 1)

        self.status.pull_finished(league.key, "boxscores", new, cached)
        return {"new": new, "cached": cached, "failed": failed}

    def aggregate(self) -> tuple[int, int]:
        started = time.monotonic()
        rows, files = aggregate_box_scores(self.league)
        self.status.aggregation_ran(
            self.league.key, "agg", time.monotonic() - started, rows, files
        )
        return rows, files
