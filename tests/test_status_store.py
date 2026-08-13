"""Redis status keys must be namespaced per league.

Contract: the daemon sweeps every enabled league each cycle. If status keys were not
league-scoped, the last league to finish would overwrite the others and the MCP server
would report one league's timestamps for all of them.
"""

import fakeredis
import pytest

from status.store import StatusStore


@pytest.fixture
def store():
    return StatusStore(fakeredis.FakeStrictRedis())


def test_pull_status_is_per_league(store):
    store.pull_started("nba", "boxscores")
    store.pull_finished("nba", "boxscores", files_new=5, files_cached=100)
    store.pull_started("wnba", "boxscores")
    store.pull_finished("wnba", "boxscores", files_new=2, files_cached=3)

    assert store.get_pull("nba", "boxscores")["files_new"] == "5"
    assert store.get_pull("wnba", "boxscores")["files_new"] == "2"


def test_pull_status_is_per_dataset(store):
    store.pull_finished("nba", "schedules", files_new=30, files_cached=0)
    store.pull_finished("nba", "boxscores", files_new=7, files_cached=1200)

    assert store.get_pull("nba", "schedules")["files_new"] == "30"
    assert store.get_pull("nba", "boxscores")["files_new"] == "7"


def test_error_is_recorded_without_losing_counts(store):
    """A failure must not erase what the last good run reported."""
    store.pull_finished("wnba", "boxscores", files_new=4, files_cached=0)
    store.pull_failed("wnba", "boxscores", "GSV: 404")

    status = store.get_pull("wnba", "boxscores")
    assert status["files_new"] == "4"
    assert "404" in status["last_error"]


def test_pull_started_clears_the_previous_error(store):
    """Otherwise a stale error from an old run looks like a current failure."""
    store.pull_failed("wnba", "boxscores", "GSV: 404")
    store.pull_started("wnba", "boxscores")

    assert store.get_pull("wnba", "boxscores")["last_error"] == ""


def test_inflight_is_per_league(store):
    store.mark_inflight("nba", "job-1")
    store.mark_inflight("wnba", "job-2")
    assert store.get_inflight("nba") == "job-1"
    assert store.get_inflight("wnba") == "job-2"

    store.clear_inflight("nba")
    assert store.get_inflight("nba") is None
    assert store.get_inflight("wnba") == "job-2"


def test_aggregation_status_round_trips(store):
    store.aggregation_ran("wnba", "agg", duration_s=1.2345, rows_out=402, source_files=3)

    status = store.get_aggregation("wnba", "agg")
    assert status["rows_out"] == "402"
    assert status["source_files"] == "3"
    assert status["duration_s"] == "1.234" or status["duration_s"] == "1.235"
    assert status["last_run"].endswith("+00:00")  # ISO-8601 UTC
