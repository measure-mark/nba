import pandas as pd
from lagged_minutes import LagMinutesOneGame
from lib.helper_functions import is_zero


def check_minuntes_make_sense(minutes):
    """ Validate that the total minutes played is a full game or close to a full game"""
    if is_zero(minutes-240, tol=0.1):
        return True
    # Single overtime
    if is_zero(minutes-265, tol=0.1):
        return True

    # Double overtime
    if is_zero(minutes-290, tol=0.1):
        return True
    return False


class MinutesPlayedModel:
    def _check_validity(self, df):
        assert type(df) is pd.DataFrame
        assert "MPC" in df
        assert "pid" in df
        assert "team" in df

    def predict_mp(self, home_team, away_team, game_date) -> pd.DataFrame:
        raise NotImplementedError