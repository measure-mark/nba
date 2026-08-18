import json
import sys

import pandas as pd

from leagues.config import LeagueConfig
from leagues.registry import LeagueRegistry


def _official_names(values: pd.Series) -> set[str]:
    return {
        name.strip()
        for crew in values.dropna().astype(str)
        for name in crew.split("|")
        if name.strip()
    }


def make_official_map(league: LeagueConfig) -> dict[str, int]:
    """Build a stable name-to-indicator-index map from ``agg.csv``.

    Existing indices are preserved and newly observed officials are appended, so an
    artifact refresh cannot silently change an already-trained model's inputs.
    """
    df = pd.read_csv(league.data_root / "agg.csv", usecols=["Officials"])
    path = league.data_root / "official_map.json"
    official_map = json.loads(path.read_text()) if path.exists() else {}

    next_id = max(official_map.values(), default=-1) + 1
    for name in sorted(_official_names(df["Officials"]).difference(official_map)):
        official_map[name] = next_id
        next_id += 1

    path.write_text(json.dumps(official_map, indent=1))
    print(f"{league.key}: {len(official_map)} officials")
    return official_map


if __name__ == "__main__":
    make_official_map(LeagueRegistry().get(sys.argv[1] if len(sys.argv) > 1 else "nba"))
