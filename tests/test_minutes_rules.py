"""The 'is this a complete game' rule, which is league-specific.

Business rule: a complete game is regulation plus zero or more overtime periods, where
regulation is 5 players x the league's game length. Getting this wrong is silent and
total -- applying NBA's 240 to the WNBA rejects every WNBA game and produces an empty
dataset with no error anywhere.
"""

import pytest

from model.minutes import check_minuntes_make_sense


def test_regulation_differs_by_league(nba, wnba):
    """NBA regulation is 240 player-minutes (5x48), WNBA is 200 (5x40)."""
    assert check_minuntes_make_sense(240, nba)
    assert check_minuntes_make_sense(200, wnba)


def test_one_league_rule_rejects_the_other(nba, wnba):
    """The whole point of parameterizing: each league must reject the other's total."""
    assert not check_minuntes_make_sense(200, nba)
    assert not check_minuntes_make_sense(240, wnba)


@pytest.mark.parametrize("minutes", [265, 290, 315, 340])
def test_nba_overtimes(minutes, nba):
    """Each OT period adds 25 player-minutes. 315 (3OT) and 340 (4OT) were rejected by
    the old hardcoded 240/265/290 rule, even though schedule.csv contains 3OT and 4OT
    games -- the 'Handle overtimes' README TODO."""
    assert check_minuntes_make_sense(minutes, nba)


@pytest.mark.parametrize("minutes", [225, 250])
def test_wnba_overtimes(minutes, wnba):
    assert check_minuntes_make_sense(minutes, wnba)


def test_rejects_incomplete_game(nba):
    """A total between regulation and 1OT means missing or double-counted players."""
    assert not check_minuntes_make_sense(250, nba)
