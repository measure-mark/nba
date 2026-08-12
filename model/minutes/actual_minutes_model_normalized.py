from data_model.box_score_store import BoxScoreStore
from lib.helper_functions import is_zero
from model.minutes import check_minuntes_make_sense
from model.minutes import MinutesPlayedModel


import pandas as pd
from IPython.display import display


class ActualMinutesModelNormalized(MinutesPlayedModel):

    def __init__(self, box_score_store: BoxScoreStore):
        self.g = box_score_store

    def predict_mp(self, home_team, away_team, game_date) -> pd.DataFrame:

        g = self.g

        hdf = g.game_data_frame(home_team, game_date)
        adf = g.game_data_frame(away_team, game_date)

        #Setup the feature vector for our model
        if not check_minuntes_make_sense(hdf.MPC.sum()):
                display(adf[["Player", "MP", "MPC"]])
                raise Exception(f"{game_date} home team {home_team} minutes totalled wrong {hdf.MPC.sum()}")
        hdf["MPCi"] = hdf.MPC * 240 / hdf.MPC.sum()

            #Setup the feature vector for our model
        if not check_minuntes_make_sense(adf.MPC.sum()):
                display(adf[["Player", "MP", "MPC"]])
                raise Exception(f"{game_date} away team {away_team} minutes totalled wrong {adf.MPC.sum()}")

        adf["MPCi"] = -1 * adf.MPC * 240 / adf.MPC.sum()
        df=pd.concat([hdf, adf])

        assert is_zero(df.MPCi.sum()), f"Total offset minutes are {df.MPCi.sum()}"
        assert is_zero(df.MPCi.apply(abs).sum() - 480), df.MPCi.apply(abs).sum()

        # dropping for safety
        df.drop(columns=["PTS"], inplace=True)

        return df