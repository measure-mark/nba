import json
import sys

import pandas as pd

from leagues.config import LeagueConfig
from leagues.registry import LeagueRegistry


def _most_common_name(series: pd.Series) -> str:
    """Return the canonical spelling used most often for one team."""
    names = series.dropna().astype(str).str.strip()
    if names.empty:
        raise ValueError("Cannot build a team map from empty team names")
    return names.value_counts().index[0]


def make_team_map(league: LeagueConfig) -> dict[str, str]:
    """Build ``team_map.json`` as ``{team_code: full_team_name}`` for a league.

    Newly aggregated data carries ``Team Code`` directly. Older NBA aggregates do
    not, so they retain the original fallback: infer the home code from each game's
    filename and select the name most commonly associated with that home code.
    """
    df = pd.read_csv(league.data_root / "agg.csv")

    if "Team Code" in df.columns:
        source = df[["Team Code", "Team"]].dropna().copy()
        source["Team Code"] = source["Team Code"].astype(str).str.strip()
        team_map = (
            source.groupby("Team Code")["Team"]
            .apply(_most_common_name)
            .sort_index()
            .to_dict()
        )
    else:
        source = df[["filename", "Team"]].copy()
        source["home_abrev"] = source.filename.apply(
            lambda filename: league.links.parse_boxscore_filename(filename)[1]
        )
        team_map = (
            source.groupby("home_abrev")["Team"]
            .apply(_most_common_name)
            .sort_index()
            .to_dict()
        )

    league.data_root.mkdir(parents=True, exist_ok=True)
    with open(league.data_root / "team_map.json", "w") as writer:
        json.dump(team_map, writer, indent=1)

    print(f"{league.key}: {len(team_map)} teams")
    return team_map


if __name__ == "__main__":
    make_team_map(LeagueRegistry().get(sys.argv[1] if len(sys.argv) > 1 else "nba"))
