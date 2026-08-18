import json

import pandas as pd

from artifact_makers.make_player_map import make_player_map


def test_player_map_preserves_ids_and_appends_new_players(wnba):
    wnba.data_root.mkdir(parents=True)
    (wnba.data_root / "player_map.json").write_text(
        json.dumps({"player-b": 0, "retired-player": 1})
    )
    pd.DataFrame({"Player ID": ["player-a", "player-b", "player-c"]}).to_csv(
        wnba.data_root / "agg.csv", index=False
    )

    result = make_player_map(wnba)

    assert result == {
        "player-b": 0,
        "retired-player": 1,
        "player-a": 2,
        "player-c": 3,
    }
