import numpy as np
import pandas as pd

from model.minutes import MinutesPlayedModel


class Model:
    def predict_one_game(self, home_team, game_date):
        raise NotImplementedError()
        
    def predict_games(self, jdf):
        """jdf is a dataframe with columns for date, home and away"""
        raise NotImplementedError
    
class EmbeddingToScoreModel(Model):
    def __init__(self, tf_model, mpm: MinutesPlayedModel):
        self.tf_model=tf_model
        self.mpm : MinutesPlayedModel = mpm
    
    def predict_games(self, jdf: pd.DataFrame):
        NGames = len(jdf)
        
        # Deal with this
        NPlayers = self.tf_model.input_shape[1]
        
        X = np.zeros((NPlayers, NGames))
      
        # TODO:  change "opp" to "home" with next reload
        to_iter = enumerate(jdf[["date", "home", "opp"]].itertuples(index=False, name=None))
        for i, (game_date, home_team, away_team) in to_iter:
            gdf = self.mpm.predict_mp(home_team, away_team, game_date)    
            X[gdf.pid.values, i] = gdf.MPCi

        preds=self.tf_model.predict(X.T)
        return preds