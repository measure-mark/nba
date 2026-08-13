import pandas as pd
from bs4 import BeautifulSoup

from artifact_makers.make_minimal_box_scores import get_minimal_stats
from leagues.config import LeagueConfig


def cached_box_scores(league: LeagueConfig) -> list[str]:
    """Cached box score filenames belonging to this league, oldest first.

    Membership is decided by the league's own LinkScheme. The previous hardcoded
    `^boxscores_\\d{9}\\w{3}\\.html` was anchored, so a wnba_-prefixed file was silently
    skipped -- producing an empty WNBA dataset with no error anywhere.
    """
    if not league.raw_dir.exists():
        return []
    return sorted(
        p.name for p in league.raw_dir.iterdir()
        if league.links.matches_boxscore_filename(p.name)
    )


def aggregate_box_scores(league: LeagueConfig) -> tuple[int, int]:
    """Parse every cached box score for a league into its agg.csv.

    Returns (rows written, source files parsed).
    """
    filenames = cached_box_scores(league)
    dfs = [
        get_minimal_stats(
            BeautifulSoup((league.raw_dir / fn).read_bytes(), "html.parser"), fn
        )
        for fn in filenames
    ]
    if not dfs:
        return 0, 0

    out = pd.concat(dfs, ignore_index=True)
    league.data_root.mkdir(parents=True, exist_ok=True)
    out.to_csv(league.data_root / "agg.csv", index=False)
    return len(out), len(filenames)
