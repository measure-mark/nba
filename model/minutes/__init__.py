import pandas as pd

from leagues.config import LeagueConfig
from lib.helper_functions import is_zero


def check_minuntes_make_sense(minutes, league: LeagueConfig):
    """Validate that the total minutes played is a full game, or a full game plus
    overtime, for this league.

    The valid totals are league-specific: NBA regulation is 240 player-minutes
    (5 x 48), WNBA is 200 (5 x 40). Applying one league's totals to the other rejects
    every game, so this takes the league rather than assuming.
    """
    return any(
        is_zero(minutes - total, tol=0.1) for total in league.valid_game_minutes()
    )


class MinutesPlayedModel:
    def _check_validity(self, df):
        assert type(df) is pd.DataFrame
        assert "MPC" in df
        assert "pid" in df
        assert "team" in df

    def predict_mp(self, home_team, away_team, game_date) -> pd.DataFrame:
        raise NotImplementedError