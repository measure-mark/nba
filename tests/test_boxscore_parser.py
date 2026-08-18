"""Box score parsing, against real basketball-reference HTML.

Regression: the parser identified tables by caption prose, matching
"<Team> Basic and Advanced Stats Table". basketball-reference now writes
"<Team> (0-1) Table", so every table fell through to (None, None), get_minimal_stats
concatenated an empty list, and the box score yielded nothing -- for every league.

The fixture is a real page (trimmed to four tables and the officials block), not
hand-written HTML. The bug survived the earlier tests precisely because those used
synthetic markup shaped to match what the parser already expected.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from artifact_makers.make_minimal_box_scores import (
    get_minimal_stats,
    get_officials,
    get_team_and_period,
    get_team_name,
)

FIXTURE = Path(__file__).parent / "fixtures" / "wnba_boxscores_202505160WAS.html"


@pytest.fixture
def soup():
    return BeautifulSoup(FIXTURE.read_bytes(), "html.parser")


@pytest.fixture
def tables(soup):
    return {t.get("id"): t for t in soup.find_all("table")}


def test_full_game_table_is_identified(tables):
    assert get_team_and_period(tables["box-ATL-game-basic"]) == ("ATL", "FG")
    assert get_team_and_period(tables["box-WAS-game-basic"]) == ("WAS", "FG")


def test_period_splits_are_identified_not_confused_with_full_game(tables):
    """Quarter tables must be recognised and then skipped -- not silently unparseable."""
    assert get_team_and_period(tables["box-ATL-q1-basic"]) == ("ATL", "Q1")


def test_non_box_score_tables_are_rejected(tables):
    """The advanced-stats table has a different id shape and must not be mistaken for
    a full-game table, or every player would be counted twice."""
    assert get_team_and_period(tables["ATL-advanced"]) == (None, None)


def test_team_name_strips_the_win_loss_record(tables):
    """agg.csv's Team column holds the full name and team_map.json is keyed on it, so
    the record that basketball-reference now appends has to come off."""
    assert get_team_name(tables["box-ATL-game-basic"]) == "Atlanta Dream"


def test_extracts_officials_from_game_metadata(soup):
    """agg.csv's Officials column feeds official_map.json, so the crew has to come off
    the real page -- where the label carries a non-breaking space and the names sit in
    the parent div, not in the <strong> the search finds."""
    assert get_officials(soup) == ("Kevin Fahy", "Charles Watson", "Blanca Burns")


def test_parses_both_teams_once_each(soup):
    df = get_minimal_stats(soup, "wnba_boxscores_202505160WAS.html")

    assert sorted(df["Team Code"].unique()) == ["ATL", "WAS"]
    assert sorted(df.Team.unique()) == ["Atlanta Dream", "Washington Mystics"]
    assert set(df.Period) == {"FG"}
    # One row per player per game -- a duplicated table would double this.
    assert not df.duplicated(subset=["Player ID"]).any()


def test_parsed_minutes_satisfy_the_wnba_rule(soup, wnba):
    """End-to-end: real parsed minutes must satisfy the league rule. Each WNBA team
    plays 200 player-minutes in regulation (5 x 40); the NBA's 240 would reject this."""
    df = get_minimal_stats(soup, "wnba_boxscores_202505160WAS.html")

    def to_minutes(mp):
        m, s = mp.split(":")
        return int(m) + int(s) / 60

    for code, group in df.groupby("Team Code"):
        total = sum(to_minutes(mp) for mp in group.MP)
        assert any(
            abs(total - valid) <= 0.1 for valid in wnba.valid_game_minutes()
        ), f"{code} totalled {total}"


def test_empty_page_raises_rather_than_returning_nothing(wnba):
    """A page with no full-game tables must fail loudly. Returning an empty frame is
    how the caption bug stayed invisible."""
    empty = BeautifulSoup("<html><body>no tables</body></html>", "html.parser")

    with pytest.raises(ValueError, match="No full-game tables"):
        get_minimal_stats(empty, "wnba_boxscores_202505160WAS.html")
