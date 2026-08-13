import pytest

from leagues.registry import LeagueRegistry


@pytest.fixture
def registry(tmp_path):
    """Registry rooted at a temp data dir, so tests never touch data/."""
    return LeagueRegistry(data_root=tmp_path)


@pytest.fixture
def nba(registry):
    return registry.get("nba")


@pytest.fixture
def wnba(registry):
    return registry.get("wnba")
