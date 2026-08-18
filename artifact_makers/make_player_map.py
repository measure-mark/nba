# Existing player ids are immutable model inputs. New players are appended so an
# artifact refresh cannot silently change the meaning of already-trained weights.

import json
import sys

import pandas as pd

from leagues.config import LeagueConfig
from leagues.registry import LeagueRegistry


def make_player_map(league: LeagueConfig) -> dict:
    """Build a stable player map, preserving ids and appending new players."""
    df = pd.read_csv(league.data_root / "agg.csv")
    path = league.data_root / "player_map.json"
    pid_map = json.loads(path.read_text()) if path.exists() else {}

    next_id = max(pid_map.values(), default=-1) + 1
    for pid in df["Player ID"].dropna().unique():
        if pid not in pid_map:
            pid_map[pid] = next_id
            next_id += 1

    with open(path, "w") as writer:
        json.dump(pid_map, writer, indent=1)

    print(f"{league.key}: {len(pid_map)} players")
    return pid_map


if __name__ == "__main__":
    make_player_map(LeagueRegistry().get(sys.argv[1] if len(sys.argv) > 1 else "nba"))
