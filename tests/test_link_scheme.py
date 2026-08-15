"""Contract: a league's LinkScheme owns the link <-> cached-filename convention.

Three call sites used to carry their own regex for this and disagreed about anchoring,
which is what made WNBA files silently unparseable in some places and silently skipped
in others.
"""

import pytest

from data_model.func import bs_filename_to_date, bs_filename_to_hometeam
from lib.helper_functions import link_to_file_name


@pytest.mark.parametrize(
    "league_key,date,team,expected_link,expected_filename",
    [
        ("nba", "20210516", "TOR", "/boxscores/202105160TOR.html", "boxscores_202105160TOR.html"),
        (
            "wnba",
            "20260517",
            "ATL",
            "/wnba/boxscores/202605170ATL.html",
            "wnba_boxscores_202605170ATL.html",
        ),
    ],
)
def test_round_trip(registry, league_key, date, team, expected_link, expected_filename):
    """link -> cached filename -> (date, team) must return exactly what we started with.

    The literal values are the real basketball-reference shapes; link_to_file_name maps
    "/" to "_", which is what puts the league prefix on the front of the filename.
    """
    links = registry.get(league_key).links

    link = links.boxscore_link(date, team)
    assert link == expected_link

    filename = link_to_file_name(link)
    assert filename == expected_filename

    assert links.parse_boxscore_filename(filename) == (date, team)


def test_schemes_reject_each_others_files(nba, wnba):
    """A league must not claim another league's cached files -- that would merge WNBA
    games into the NBA dataset."""
    assert not nba.links.matches_boxscore_filename("wnba_boxscores_202605170ATL.html")
    assert not wnba.links.matches_boxscore_filename("boxscores_202105160TOR.html")


def test_nba_helpers_reject_wnba_filenames():
    """Regression: the module-level NBA helpers must raise on a wnba_-prefixed name
    rather than matching it partway and returning a plausible-looking wrong answer."""
    with pytest.raises(ValueError):
        bs_filename_to_date("wnba_boxscores_202605170ATL.html")
    with pytest.raises(ValueError):
        bs_filename_to_hometeam("wnba_boxscores_202605170ATL.html")


def test_nba_helpers_still_work():
    assert bs_filename_to_date("boxscores_202105160TOR.html") == "20210516"
    assert bs_filename_to_hometeam("boxscores_202105160TOR.html") == "TOR"


def test_is_boxscore_link_discriminates(nba, wnba):
    """Sweeps read box score links off schedule pages, which also link to players,
    teams and other leagues."""
    assert nba.links.is_boxscore_link("/boxscores/202105160TOR.html")
    assert not nba.links.is_boxscore_link("/wnba/boxscores/202605170ATL.html")
    assert not nba.links.is_boxscore_link("/players/w/willima02.html")
    assert wnba.links.is_boxscore_link("/wnba/boxscores/202605170ATL.html")
    assert not wnba.links.is_boxscore_link("/boxscores/202105160TOR.html")


@pytest.mark.parametrize(
    "league_key,boxscore,pbp,boxscore_filename,pbp_filename",
    [
        (
            "nba",
            "/boxscores/202105160TOR.html",
            "/boxscores/pbp/202105160TOR.html",
            "boxscores_202105160TOR.html",
            "boxscores_pbp_202105160TOR.html",
        ),
        (
            "wnba",
            "/wnba/boxscores/202606220ATL.html",
            "/wnba/boxscores/pbp/202606220ATL.html",
            "wnba_boxscores_202606220ATL.html",
            "wnba_boxscores_pbp_202606220ATL.html",
        ),
    ],
)
def test_pbp_links_and_filenames_follow_the_boxscore_game(
    registry, league_key, boxscore, pbp, boxscore_filename, pbp_filename
):
    links = registry.get(league_key).links

    assert links.pbp_link_for_boxscore(boxscore) == pbp
    assert links.pbp_filename_for_boxscore(boxscore_filename) == pbp_filename
    assert links.matches_pbp_filename(pbp_filename)
    assert not links.matches_boxscore_filename(pbp_filename)
