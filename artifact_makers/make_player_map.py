# This SHOULD NOT BE RERUN unless you are retraining.
# It only needs to be rerun when new players are added that are worth modeling directly.
#
# Rerunning renumbers every player id, because the map is built from unique() order.
# BoxScoreStore asserts the player count against a hardcoded tripwire (1442 for NBA)
# to ensure that a silent renumbering shows up as a loud failure rather than garbage
# model inputs.

import json

import pandas as pd

from leagues.config import LeagueConfig


def make_player_map(league: LeagueConfig) -> dict:
    """Build and write a league's player_map.json. Returns the map."""
    df = pd.read_csv(league.data_root / "agg.csv")
    pid_map = {pid: i for i, pid in enumerate(df["Player ID"].unique())}

    with open(league.data_root / "player_map.json", "w") as writer:
        json.dump(pid_map, writer, indent=1)

    print(f"{league.key}: {len(pid_map)} players")
    return pid_map


if __name__ == "__main__":
    import sys

    from leagues.registry import LeagueRegistry

    make_player_map(LeagueRegistry().get(sys.argv[1] if len(sys.argv) > 1 else "nba"))
