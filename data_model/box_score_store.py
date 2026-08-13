import pandas as pd
import json

from lib.helper_functions import validate_date
from leagues.config import LeagueConfig


class BoxScoreStore:
    """Per-game player box score rows for one league, loaded from that league's data root."""

    def __init__(self, league: LeagueConfig):
        self.league = league
        links = league.links

        # Load in the data for our game by game log
        df = pd.read_csv(league.data_root / "agg.csv")
        df.rename(columns={"Team": "team_ln"}, inplace=True)

        with open(league.data_root / "team_map.json", "r") as reader:
            team_abbrev_map = json.load(reader)
        team_rev_map = {v.strip(): k for k, v in team_abbrev_map.items()}

        with open(league.data_root / "player_map.json", "r") as reader:
            pid_map = json.load(reader)

        df["team"] = df.team_ln.str.strip().map(team_rev_map)

        parsed = df.filename.apply(links.parse_boxscore_filename)
        df["date"] = parsed.str[0]
        df["home_abrev"] = parsed.str[1]
        df["is_home"] = df.home_abrev == df.team

        # We use PID to index into our model's input vector
        df["pid"] = df["Player ID"].map(pid_map)

        self.df = df
        self.Nplayers = len(pid_map)

        # Sanity check: if the player_map changes size, our data model may be stale.
        # For NBA, player_map.json has 1442 players; if it changes, investigate before
        # retraining models that depend on this embedding size.
        if league.key == "nba":
            expected_nba_players = 1442
            assert self.Nplayers == expected_nba_players, (
                f"{league.key}: player_map has {self.Nplayers} players, "
                f"expected {expected_nba_players} — data may have changed"
            )

    def game_data_frame(self, team: str, date: str):
        validate_date(date)

        df = self.df
        mask = df.team == team
        assert sum(mask) > 0, f"Invalid team {team}"

        mask_dt = df.date == date
        assert sum(mask_dt) > 0, f"No game for {team} on {date}"

        game_df = df[mask & mask_dt].reset_index(drop=True).copy()
        assert len(game_df) > 0
        return game_df
