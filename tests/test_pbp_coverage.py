from scraper.play_by_play import play_by_play_coverage


def test_pbp_coverage_reports_missing_and_invalid_files(wnba):
    valid_boxscore = "wnba_boxscores_202606220ATL.html"
    missing_boxscore = "wnba_boxscores_202606240GSV.html"
    valid_pbp = "wnba_boxscores_pbp_202606220ATL.html"
    invalid_pbp = "wnba_boxscores_pbp_202606250ATL.html"

    wnba.raw_dir.mkdir(parents=True)
    (wnba.raw_dir / valid_boxscore).write_bytes(b"<html>box score</html>")
    (wnba.raw_dir / missing_boxscore).write_bytes(b"<html>box score</html>")
    (wnba.raw_dir / valid_pbp).write_bytes(b'<table id="pbp"></table>')
    (wnba.raw_dir / invalid_pbp).write_bytes(b"<html>missing table</html>")

    coverage = play_by_play_coverage(wnba, [valid_boxscore, missing_boxscore], years={2026})

    assert coverage == {
        "expected_games": 2,
        "cached_files": 2,
        "valid_files": 1,
        "invalid_files": 1,
        "missing_files": 1,
        "missing": ["wnba_boxscores_pbp_202606240GSV.html"],
        "invalid": [invalid_pbp],
    }


def test_pbp_coverage_filters_boxscores_and_pbp_by_season(wnba):
    old_boxscore = "wnba_boxscores_202506220ATL.html"
    current_boxscore = "wnba_boxscores_202606220ATL.html"
    old_pbp = "wnba_boxscores_pbp_202506220ATL.html"

    wnba.raw_dir.mkdir(parents=True)
    (wnba.raw_dir / old_pbp).write_bytes(b'<table id="pbp"></table>')

    coverage = play_by_play_coverage(wnba, [old_boxscore, current_boxscore], years={2026})

    assert coverage["expected_games"] == 1
    assert coverage["cached_files"] == 0
    assert coverage["missing"] == ["wnba_boxscores_pbp_202606220ATL.html"]
