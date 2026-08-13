"""Aggregation must find each league's cached box scores.

The bug this pins: the aggregation loop matched filenames with an anchored
`re.match(r"^boxscores_...")`, so every wnba_-prefixed file hit the `continue` branch.
No error was raised and no row was written -- the WNBA dataset just came out empty.
"""

import pandas as pd

from artifact_makers.aggregate import aggregate_box_scores, cached_box_scores

# Mirrors the real basketball-reference shape: the id carries team and period, and the
# caption carries the full name plus a win-loss record. See tests/fixtures/ for a real
# page, and test_boxscore_parser.py for the parse itself.
BOX_SCORE_HTML = """
<html><body>
<table class="suppress_all sortable stats_table" id="box-{code}-game-basic">
  <caption>{team} (0-1) Table</caption>
  <tr><th colspan="3">header</th></tr>
  <tr><th>Rk</th><th>MP</th><th>PTS</th></tr>
  <tr><th><a href="/players/g/{pid}.html">{player}</a></th><td>32:11</td><td>21</td></tr>
  <tr><th><a href="/players/h/{pid2}.html">{player2}</a></th><td>28:04</td><td>14</td></tr>
</table>
</body></html>
"""


def _write_box_score(league, filename, team, player, pid, player2, pid2, code="ATL"):
    league.raw_dir.mkdir(parents=True, exist_ok=True)
    (league.raw_dir / filename).write_text(
        BOX_SCORE_HTML.format(
            team=team, player=player, pid=pid, player2=player2, pid2=pid2, code=code
        )
    )


def test_wnba_box_scores_are_not_skipped(wnba):
    """The headline regression: a wnba_-prefixed file must be picked up."""
    _write_box_score(
        wnba, "wnba_boxscores_202605170ATL.html", "Atlanta Dream",
        "Rhyne Howard", "howarrh01", "Allisha Gray", "grayal01",
    )

    assert cached_box_scores(wnba) == ["wnba_boxscores_202605170ATL.html"]

    rows, files = aggregate_box_scores(wnba)
    assert (rows, files) == (2, 1)

    df = pd.read_csv(wnba.data_root / "agg.csv")
    assert list(df.columns) == [
        "Player", "Player ID", "MP", "PTS", "Team", "Team Code", "Period", "filename",
    ]
    assert set(df["Player ID"]) == {"howarrh01", "grayal01"}
    assert df.filename.unique().tolist() == ["wnba_boxscores_202605170ATL.html"]


def test_leagues_do_not_aggregate_each_others_files(nba, wnba):
    """Contract: both leagues' raw files can coexist, and each aggregation takes only
    its own. Without this, one league's games silently pollute the other's dataset."""
    _write_box_score(
        nba, "boxscores_202105160TOR.html", "Toronto Raptors",
        "Fred VanVleet", "vanvlfr01", "Pascal Siakam", "siakapa01",
    )
    _write_box_score(
        wnba, "wnba_boxscores_202605170ATL.html", "Atlanta Dream",
        "Rhyne Howard", "howarrh01", "Allisha Gray", "grayal01",
    )
    # A stray file from the other league sitting in the wrong raw dir must be ignored.
    _write_box_score(
        wnba, "boxscores_202105160TOR.html", "Toronto Raptors",
        "Fred VanVleet", "vanvlfr01", "Pascal Siakam", "siakapa01",
    )

    assert cached_box_scores(wnba) == ["wnba_boxscores_202605170ATL.html"]
    assert cached_box_scores(nba) == ["boxscores_202105160TOR.html"]

    aggregate_box_scores(nba)
    aggregate_box_scores(wnba)

    nba_df = pd.read_csv(nba.data_root / "agg.csv")
    wnba_df = pd.read_csv(wnba.data_root / "agg.csv")
    assert set(nba_df["Player ID"]) == {"vanvlfr01", "siakapa01"}
    assert set(wnba_df["Player ID"]) == {"howarrh01", "grayal01"}


def test_empty_raw_dir_is_not_an_error(wnba):
    """A league with nothing pulled yet aggregates to zero rows rather than raising --
    the daemon sweeps every league every cycle, including ones with no data."""
    assert aggregate_box_scores(wnba) == (0, 0)
