import pandas as pd
from IPython.display import display
from data_model.box_score_store import BoxScoreStore
from lib.helper_functions import is_zero
from model.minutes import check_minuntes_make_sense
from model.minutes import MinutesPlayedModel


class LagMinutesOneGame(MinutesPlayedModel):
    """use the exact minutes played from the previous game.
    This model will not respond to trade or injuries, and is really only
    useful as a baseline
    """

    def __init__(self, box_score_store: BoxScoreStore, sched: NBASchedule):
        self.box_score_store = box_score_store
        self.sched = sched

    def predict_mp(self, home_team, away_team, game_date) -> pd.DataFrame:
        df = self.setup_df_lagged_lineups(game_date, home_team, away_team)
        self._check_validity(df)
        return df
    
    def setup_df_lagged_lineups(self, game_date, home_team, away_team):
        
        # TODO--this needent be created here--put out to self
        g = self.box_score_Store
        sched = self.sched
        
        # Pull the previous lineups for the previous game for each team
        prev_home_date = sched.get_prev_game(home_team, game_date)
        assert prev_home_date < game_date
        hdf = g.game_data_frame(home_team, prev_home_date)
        
        prev_away_date = sched.get_prev_game(away_team, game_date)
        assert prev_away_date < game_date
        adf = g.game_data_frame(away_team, prev_away_date)
        
        #Setup the feature vector for our model
        if not check_minuntes_make_sense(hdf.MPC.sum()):
                display(hdf[["Player", "MP", "MPC"]])
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
        # Now assign the date of the game
        df["date"] = game_date
        df["filename"] = f"boxscores_{game_date}0{home_team}.html"
        df.drop(columns=["PTS"], inplace=True)
        
        return df

