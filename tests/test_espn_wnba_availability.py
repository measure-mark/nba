from scripts.espn_wnba_availability import availability_records, schedule_games, walk_related_paths


def test_schedule_games_extracts_espn_game_metadata():
    payload = {
        "events": [
            {
                "id": "401857102",
                "date": "2026-07-31T23:30Z",
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "NYL"}},
                            {"homeAway": "away", "team": {"abbreviation": "LAS"}},
                        ]
                    }
                ],
            }
        ]
    }

    assert schedule_games(payload) == [
        {
            "game_id": "401857102",
            "game_date": "2026-07-31T23:30Z",
            "home_team": "NYL",
            "away_team": "LAS",
        }
    ]


def test_availability_records_only_emits_athlete_injury_objects():
    game = {"game_id": "1", "game_date": "2025-01-01", "home_team": "ABC", "away_team": "XYZ"}
    payload = {
        "injuries": [
            {
                "athlete": {"id": "12", "displayName": "Test Player"},
                "team": {"id": "9", "abbreviation": "ABC"},
                "status": "Out",
                "reason": "Knee",
                "comment": "Will not play",
            }
        ],
        "leaders": [{"athlete": {"id": "99", "displayName": "Not An Injury"}}],
    }

    records = availability_records(game, payload)

    assert len(records) == 1
    assert records[0]["player_name"] == "Test Player"
    assert records[0]["availability_status"] == "Out"
    assert records[0]["absence_reason"] == "Knee"
    assert records[0]["source_json_path"] == "$.injuries[]"
    assert "$.injuries" in walk_related_paths(payload)
