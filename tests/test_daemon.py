"""The scraper is one long-running backfiller.

Design decision being enforced: there is no "backfill mode" separate from "daemon mode".
The scraper works its season target down continuously, and incremental daily pulling is
what that same loop does once the backlog is empty.
"""

from datetime import date

import pytest

import scraper.daemon as daemon


class FakeSweeper:
    """Records what it was asked to sweep and replays scripted results."""

    def __init__(self, league, results):
        self.league = league
        self.results = list(results)
        self.calls = []

    def sweep(self, season, verbose=False, schedule_max_age=None):
        self.calls.append((season, schedule_max_age))
        return self.results.pop(0) if self.results else {"new": 0, "cached": 0, "failed": 0}


class StopLoop(Exception):
    """Breaks out of run_forever's infinite loop from the sleep hook."""


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.setattr(daemon, "SEASONS", "")
    monkeypatch.setattr(daemon, "IDLE_POLL_SECONDS", 60)
    monkeypatch.setattr(daemon, "SCHEDULE_MAX_AGE_SECONDS", 3600)


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("2025", [2025]),
        ("2023,2024", [2023, 2024]),
        ("2015-2018", [2015, 2016, 2017, 2018]),
        ("1997-1999,2025", [1997, 1998, 1999, 2025]),
        ("2025,2025", [2025]),
        (" 2024 , 2025 ", [2024, 2025]),
    ],
)
def test_parse_seasons(spec, expected):
    """Ranges matter: a real backfill target is a decade, not a list of years typed out."""
    assert daemon.parse_seasons(spec) == expected


def test_season_defaults_to_today(nba, wnba):
    """Unset SEASONS means the current season, which differs by league convention."""
    october = date(2026, 10, 20)
    assert daemon.seasons_for(nba, october) == [2027]
    assert daemon.seasons_for(wnba, october) == [2026]


def test_explicit_seasons_override_today(monkeypatch, wnba):
    monkeypatch.setattr(daemon, "SEASONS", "2015-2017")
    assert daemon.seasons_for(wnba, date(2026, 8, 13)) == [2015, 2016, 2017]


def test_finished_seasons_never_refetch_schedules(monkeypatch, wnba):
    """A finished season's schedule cannot change, so its pages are cached forever.

    The in-progress season's pages must expire -- otherwise the scraper reads a frozen
    schedule and can never discover a game played after the first sweep.
    """
    monkeypatch.setattr(daemon, "SEASONS", "2025,2026")
    sw = FakeSweeper(wnba, [])

    daemon.run_once([sw], date(2026, 8, 13))  # WNBA's current season in Aug 2026 is 2026

    assert sw.calls == [(2025, None), (2026, 3600)]


def test_keeps_working_while_backlog_remains(monkeypatch, wnba):
    """The core of the reframe: a pass that downloaded something must NOT sleep. With a
    multi-day backlog, sleeping between passes would stretch it out indefinitely."""
    sw = FakeSweeper(wnba, [
        {"new": 19, "cached": 0, "failed": 0},
        {"new": 19, "cached": 19, "failed": 0},
        {"new": 0, "cached": 38, "failed": 0},
    ])
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        raise StopLoop

    with pytest.raises(StopLoop):
        daemon.run_forever([sw], sleep=sleep)

    # Three passes ran back to back; only the one that found nothing new idled.
    assert len(sw.calls) == 3
    assert slept == [60]


def test_idles_once_caught_up(monkeypatch, wnba):
    """Being caught up is not an exit condition -- it is the incremental-pull state."""
    sw = FakeSweeper(wnba, [{"new": 0, "cached": 10, "failed": 0}])
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        raise StopLoop

    with pytest.raises(StopLoop):
        daemon.run_forever([sw], sleep=sleep)

    assert len(sw.calls) == 1
    assert slept == [60]


def test_persistent_failures_idle_rather_than_spin(monkeypatch, wnba):
    """A permanently failing page must not hot-loop. Nothing-new is the idle condition,
    so failures fall into it naturally and get retried on the next poll."""
    sw = FakeSweeper(wnba, [{"new": 0, "cached": 5, "failed": 2}] * 5)
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        raise StopLoop

    with pytest.raises(StopLoop):
        daemon.run_forever([sw], sleep=sleep)

    assert len(sw.calls) == 1
    assert slept == [60]
