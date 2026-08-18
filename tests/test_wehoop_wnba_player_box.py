import pandas as pd

from scripts import wehoop_wnba_player_box
from scripts.wehoop_wnba_player_box import normalize


def test_normalize_drops_reason_for_players_who_played():
    """ESPN stamps "COACH'S DECISION" on every row; only a DNP row's reason is real."""
    frame = pd.DataFrame(
        {
            "game_id": ["1", "1"],
            "game_date": ["2024-05-14", "2024-05-14"],
            "athlete_id": ["10", "11"],
            "minutes": [32.0, None],
            "did_not_play": [False, True],
            "reason": ["COACH'S DECISION", "LEFT ANKLE"],
        }
    )

    result = normalize(frame)

    assert pd.isna(result.loc[0, "reason"])
    assert result.loc[1, "reason"] == "LEFT ANKLE"


def test_normalize_treats_missing_did_not_play_as_played():
    """Early seasons carry nulls; a null must not become a phantom scratch."""
    frame = pd.DataFrame(
        {
            "game_id": ["1"],
            "game_date": ["2003-05-22"],
            "athlete_id": ["10"],
            "minutes": [18.0],
            "did_not_play": [None],
            "reason": ["COACH'S DECISION"],
        }
    )

    result = normalize(frame)

    assert result.loc[0, "did_not_play"] is False or not result.loc[0, "did_not_play"]
    assert pd.isna(result.loc[0, "reason"])


def test_run_can_rebuild_from_cached_seasons_without_github(monkeypatch, tmp_path):
    """A local reparse should not need the GitHub tree API when raw parquet is cached."""
    raw_dir = tmp_path / "raw" / "wehoop"
    raw_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "game_id": ["1"],
            "season": [2024],
            "season_type": [2],
            "game_date": ["2024-05-14"],
            "athlete_id": ["10"],
            "athlete_display_name": ["Test Player"],
            "team_id": ["1"],
            "team_abbreviation": ["ATL"],
            "opponent_team_abbreviation": ["NYL"],
            "home_away": ["home"],
            "starter": [False],
            "minutes": [None],
            "active": [False],
            "ejected": [False],
            "did_not_play": [True],
            "reason": ["LEFT ANKLE"],
        }
    ).to_parquet(raw_dir / "player_box_2024.parquet", index=False)

    def fail_available_seasons():
        raise AssertionError("available_seasons should not be called for cached rebuilds")

    monkeypatch.setattr(wehoop_wnba_player_box, "available_seasons", fail_available_seasons)

    wehoop_wnba_player_box.run(tmp_path, start=None, end=None, refresh=False)

    output = pd.read_parquet(tmp_path / "wehoop_player_box.parquet")
    assert output["athlete_display_name"].tolist() == ["Test Player"]
    assert output["reason"].tolist() == ["LEFT ANKLE"]
