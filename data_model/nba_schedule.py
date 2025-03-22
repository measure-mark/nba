import pandas as pd
import re
import json
from nba.lib.helper_functions import validate_date

class NBASchedule:
    """
    Contains NBA schedule information. Currently most useful for finding the previous game 
    a team played, which we can then use for backtesting.
    
    """
    def __init__(self):
            
        schedules_df=pd.read_csv("data/schedule.csv")
        schedules_df["yyyymmdd"]=schedules_df.yyyymmdd.apply(int).apply(str)
        schedules_df.sort_values(['team', 'yyyymmdd'], inplace=True)
        schedules_df.reset_index(drop=True, inplace=True)
        
            # Assign next game date to each row
        schedules_df["next_game_dt"]=schedules_df.yyyymmdd.shift(-1)
        schedules_df.loc[schedules_df.team.shift(-1) != schedules_df.team, "next_game_dt"]=None

  
            # Assign next game date to each row
        schedules_df["prev_game_dt"]=schedules_df.yyyymmdd.shift(1)
        schedules_df.loc[schedules_df.team.shift(1) != schedules_df.team, "prev_game_dt"]=None

        
        self.schedules_df=schedules_df
        
        self.next_games = {}
        self.prev_games = {}
        
        for g,gg in schedules_df.groupby("team"):
            self.next_games[g] = gg.set_index('yyyymmdd').next_game_dt.to_dict()

        for g,gg in schedules_df.groupby("team"):
            self.prev_games[g] = gg.set_index('yyyymmdd').prev_game_dt.to_dict()
            
        with open("data/team_map.json", "r") as reader:
            team_abbrev_map = json.load(reader)
            team_rev_map = {v.strip() : k for k,v in team_abbrev_map.items()}

        schedules_df["opp"] = schedules_df.opp_name.map(team_rev_map) 
        schedules_df["home_team"]=schedules_df['team']
        mask = schedules_df.game_location=='@'
        schedules_df.loc[mask, 'home_team'] = schedules_df[mask].opp
        
        
        
    def get_next_game(self, team, date):
        """ team: three letter abbreviation
            date: yyyymmdd format, must be a valid game date
        """     
        validate_date(date)
        return self.next_games[team][date]
    
    def get_prev_game(self, team, date):
        """ team: three letter abbreviation
            date: yyyymmdd format, must be a valid game date
        """     
        validate_date(date)
        return self.prev_games[team][date]
    
    def get_all_games_on(self, date):
        """ returns a DataFrame for all games on a given date
            with columns date, home, away
        """
        validate_date(date)
        df = self.schedules_df
        mask = df.yyyymmdd==date
        mask &= df.game_location.isnull()# | df.game_location=="NaN"
        df = df[["yyyymmdd", "home_team", "opp", "game_result"]].copy()
        df.reset_index(drop=True, inplace=True)
        df.rename(columns = {'yyyymmdd': 'date', 'home_team': 'home', 'opp': 'away'}, inplace=True)
        return df[mask]
  
    def game_score(self, team, date):
        validate_date(date)
        df = self.schedules_df
        xxx = df.loc[(df.yyyymmdd == date) & (df.team == team), ["pts", "opp_pts"]]
        
        assert xxx.shape == (1,2)
        
        #mask &= df.game_location.isnull()# | df.game_location=="NaN"
        #df = df[["yyyymmdd", "team", "OPP", "game_result"]].copy()
        #df.reset_index(drop=True, inplace=True)
        #df.rename(columns = {'yyyymmdd': 'date', 'team': 'home', 'OPP': 'away'}, inplace=True)
        return xxx.iloc[0, 0], xxx.iloc[0, 1]

    def get_away_team(self, home_team, date):
        validate_date(date)
        df = self.schedules_df
        rv = df.loc[(df.yyyymmdd == date) & (df.home_team == home_team), ["opp"]]
        return rv.iloc[0,0]

    def get_record(self, team, date):
        validate_date(date)
        df = self.schedules_df
        rv = df.loc[(df.yyyymmdd == date) & (df.team == team), ["wins", "losses"]]
        return rv.iloc[0,:2]
