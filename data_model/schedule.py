import pandas as pd
import json

from lib.helper_functions import validate_date
from leagues.config import LeagueConfig


class Schedule:
    """Schedule information for one league. Mostly used to find the previous game a
    team played, which we then use for backtesting.
    """

    def __init__(self, league: LeagueConfig):
        self.league = league

        schedules_df = pd.read_csv(league.data_root / "schedule.csv")
        schedules_df["yyyymmdd"] = schedules_df.yyyymmdd.apply(int).apply(str)
        schedules_df.sort_values(["team", "season", "yyyymmdd"], inplace=True)
        schedules_df.reset_index(drop=True, inplace=True)

        # Next/previous game, chained by row adjacency within a team. The chain has to
        # break at a season boundary as well as a team boundary -- otherwise the last
        # game of one season links to the first game of the next.
        same_next = (schedules_df.team.shift(-1) == schedules_df.team) & (
            schedules_df.season.shift(-1) == schedules_df.season
        )
        schedules_df["next_game_dt"] = schedules_df.yyyymmdd.shift(-1).where(same_next)

        same_prev = (schedules_df.team.shift(1) == schedules_df.team) & (
            schedules_df.season.shift(1) == schedules_df.season
        )
        schedules_df["prev_game_dt"] = schedules_df.yyyymmdd.shift(1).where(same_prev)

        with open(league.data_root / "team_map.json", "r") as reader:
            team_abbrev_map = json.load(reader)
        team_rev_map = {v.strip(): k for k, v in team_abbrev_map.items()}

        schedules_df["opp"] = schedules_df.opp_name.str.strip().map(team_rev_map)
        schedules_df["home_team"] = schedules_df["team"]
        away = schedules_df.game_location == "@"
        schedules_df.loc[away, "home_team"] = schedules_df.loc[away, "opp"]

        self.schedules_df = schedules_df
        self.next_games = {
            team: gg.set_index("yyyymmdd").next_game_dt.to_dict()
            for team, gg in schedules_df.groupby("team")
        }
        self.prev_games = {
            team: gg.set_index("yyyymmdd").prev_game_dt.to_dict()
            for team, gg in schedules_df.groupby("team")
        }

    def get_next_game(self, team, date):
        """team: three letter abbreviation. date: yyyymmdd, must be a valid game date."""
        validate_date(date)
        return self.next_games[team][date]

    def get_prev_game(self, team, date):
        """team: three letter abbreviation. date: yyyymmdd, must be a valid game date."""
        validate_date(date)
        return self.prev_games[team][date]

    def get_all_games_on(self, date):
        """All games on a date, as a DataFrame with columns date, home, away."""
        validate_date(date)
        df = self.schedules_df
        # Home rows only -- an away row is the same game seen from the other side.
        games = df[(df.yyyymmdd == date) & df.game_location.isnull()]
        return (
            games[["yyyymmdd", "home_team", "opp", "game_result"]]
            .rename(columns={"yyyymmdd": "date", "home_team": "home", "opp": "away"})
            .reset_index(drop=True)
        )

    def game_score(self, team, date):
        validate_date(date)
        df = self.schedules_df
        xxx = df.loc[(df.yyyymmdd == date) & (df.team == team), ["pts", "opp_pts"]]

        assert xxx.shape == (1, 2)
        return xxx.iloc[0, 0], xxx.iloc[0, 1]

    def get_away_team(self, home_team, date):
        validate_date(date)
        df = self.schedules_df
        rv = df.loc[(df.yyyymmdd == date) & (df.home_team == home_team), ["opp"]]
        return rv.iloc[0, 0]

    def get_record(self, team, date):
        validate_date(date)
        df = self.schedules_df
        rv = df.loc[(df.yyyymmdd == date) & (df.team == team), ["wins", "losses"]]
        return rv.iloc[0, :2]
