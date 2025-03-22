import pandas as pd
import json
import re

from nba.lib.helper_functions import validate_date
from nba.artifact_makers.make_team_map import extract_home_team_from_bs_filename
from .func import bs_filename_to_date

class BoxScoreStore:
    def __init__(self):
        
        # Load in the data for our game by game log
        df = pd.read_csv("data/agg.csv" )
        df.rename(columns = {"Team" : "team_ln"}, inplace=True)
  
        with open("data/team_map.json", "r") as reader:
            team_abbrev_map = json.load(reader)
        team_rev_map = {v:k for k,v in team_abbrev_map.items()}

        with open("data/player_map.json", "r") as reader:
            pid_map = json.load(reader)

        df["team"] = df.team_ln.map(team_rev_map)
        
        df["home_abrev"]=df.filename.apply(extract_home_team_from_bs_filename)
        df["is_home"] = df.home_abrev == df.team
        
        # We use PID to index into our model's input vector
        df["pid"] = df["Player ID"].map(pid_map)
        df["date"]=df.filename.apply(bs_filename_to_date)
        
        self.df = df 
        self.Nplayers = len(pid_map)
        
        # Known players as of last training, if this number changes then our data has changed
        assert self.Nplayers == 1162 

    def game_data_frame(self, team:str, date:str):
        validate_date(date)
        
        df = self.df
        mask = df.team==team
        assert sum(mask)>0, f"Invalid team {team}"
        
        mask_dt = df.date == date
        assert sum(mask_dt)>0, f"No game for {team} on {date}"
        
        game_df = df[mask&mask_dt].reset_index(drop=True).copy()
        assert len(game_df) > 0
        return game_df
        