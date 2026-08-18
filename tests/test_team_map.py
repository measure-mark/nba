import json

import pandas as pd

from artifact_makers.make_team_map import make_team_map


def test_team_map_uses_codes_from_aggregated_wnba_rows(wnba):
    wnba.data_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "Team Code": ["ATL", "ATL", "NYL"],
            "Team": ["Atlanta Dream", " Atlanta Dream ", "New York Liberty"],
            "filename": [
                "wnba_boxscores_202605170ATL.html",
                "wnba_boxscores_202605170ATL.html",
                "wnba_boxscores_202605170ATL.html",
            ],
        }
    ).to_csv(wnba.data_root / "agg.csv", index=False)

    team_map = make_team_map(wnba)

    assert team_map == {"ATL": "Atlanta Dream", "NYL": "New York Liberty"}
    assert json.loads((wnba.data_root / "team_map.json").read_text()) == team_map


def test_team_map_supports_legacy_aggregate_without_team_code(nba):
    nba.data_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "Team": ["Boston Celtics", "New York Knicks", "Boston Celtics"],
            "filename": [
                "boxscores_202601010BOS.html",
                "boxscores_202601010BOS.html",
                "boxscores_202601030BOS.html",
            ],
        }
    ).to_csv(nba.data_root / "agg.csv", index=False)

    assert make_team_map(nba) == {"BOS": "Boston Celtics"}
