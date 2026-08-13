"""Download behaviour around the shared rate limit and the on-disk cache."""

import pytest
import requests

import download_manager as dm_module
from download_manager import DownloadManager
from leagues.config import HostConfig
from throttle.memory import InMemoryThrottle


@pytest.fixture
def throttle():
    return InMemoryThrottle(HostConfig(max_requests=10, window_seconds=60, min_gap_seconds=0))


class FakeResponse:
    def __init__(self, status_code=200, content=b"<html>ok</html>", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def test_failed_request_still_consumes_a_slot(monkeypatch, wnba, throttle):
    """Regression: the original recorded the request only AFTER a successful response,
    so a request that raised was never counted -- meaning a run full of errors sailed
    straight past the rate limit, exactly when the host was least happy with us.
    """
    def boom(url, timeout):
        raise requests.ConnectionError("connection reset")

    monkeypatch.setattr(dm_module.requests, "get", boom)
    dm = DownloadManager(wnba, throttle)

    with pytest.raises(requests.ConnectionError):
        dm.download_if_new("/wnba/boxscores/202605170ATL.html")

    assert throttle.status()["in_window"] == 1


def test_cache_hit_costs_no_request(monkeypatch, wnba, throttle):
    """Contract: a cached page must not touch the network or the rate limit."""
    link = "/wnba/boxscores/202605170ATL.html"
    dm = DownloadManager(wnba, throttle)
    (wnba.raw_dir / "wnba_boxscores_202605170ATL.html").write_bytes(b"<html>cached</html>")

    def fail(url, timeout):
        raise AssertionError("network was used for a cached page")

    monkeypatch.setattr(dm_module.requests, "get", fail)

    is_new, content = dm.download_if_new(link)
    assert (is_new, content) == (False, b"<html>cached</html>")
    assert throttle.status()["in_window"] == 0


def test_downloads_into_the_league_raw_dir(monkeypatch, wnba, nba, throttle):
    """Contract: each league caches under its own data root, so a WNBA pull can never
    land in the NBA dataset."""
    monkeypatch.setattr(dm_module.requests, "get", lambda url, timeout: FakeResponse())
    dm = DownloadManager(wnba, throttle)

    is_new, _ = dm.download_if_new("/wnba/boxscores/202605170ATL.html")

    assert is_new
    assert (wnba.raw_dir / "wnba_boxscores_202605170ATL.html").exists()
    assert not list(nba.raw_dir.glob("*.html")) if nba.raw_dir.exists() else True


def test_no_partial_file_left_on_success(monkeypatch, wnba, throttle):
    """Regression: a non-atomic write left truncated pages that later looked cached and
    were never re-fetched. The write goes via a .part file and renames."""
    monkeypatch.setattr(dm_module.requests, "get", lambda url, timeout: FakeResponse())
    dm = DownloadManager(wnba, throttle)
    dm.download_if_new("/wnba/boxscores/202605170ATL.html")

    assert not list(wnba.raw_dir.glob("*.part"))


def test_non_200_raises(monkeypatch, wnba, throttle):
    monkeypatch.setattr(dm_module.requests, "get", lambda url, timeout: FakeResponse(status_code=404))
    dm = DownloadManager(wnba, throttle)

    with pytest.raises(RuntimeError, match="404"):
        dm.download_if_new("/wnba/boxscores/202605170ATL.html")
