"""Shared play-by-play cache discovery and availability validation."""

from bs4 import BeautifulSoup

from leagues.config import LeagueConfig


def cached_play_by_play(league: LeagueConfig) -> list[str]:
    """Cached PBP filenames belonging to ``league``, sorted by filename."""
    if not league.raw_dir.exists():
        return []
    return sorted(
        path.name
        for path in league.raw_dir.iterdir()
        if league.links.matches_pbp_filename(path.name)
    )


def has_pbp_table(page: bytes | str) -> bool:
    """Whether a Basketball Reference PBP page has its confirmed event table."""
    return BeautifulSoup(page, "html.parser").find("table", id="pbp") is not None


def play_by_play_coverage(
    league: LeagueConfig, boxscore_filenames: list[str], years: set[int] | None = None
) -> dict:
    """Compare cached PBP pages to the supplied cached box-score game set."""
    if years is not None:
        boxscore_filenames = [
            filename
            for filename in boxscore_filenames
            if int(league.links.parse_boxscore_filename(filename)[0][:4]) in years
        ]

    expected = {league.links.pbp_filename_for_boxscore(filename) for filename in boxscore_filenames}
    pbp_filenames = cached_play_by_play(league)
    if years is not None:
        pbp_filenames = [
            filename
            for filename in pbp_filenames
            if int(league.links.parse_pbp_filename(filename)[0][:4]) in years
        ]

    valid = []
    invalid = []
    for filename in pbp_filenames:
        page = (league.raw_dir / filename).read_bytes()
        (valid if has_pbp_table(page) else invalid).append(filename)

    missing = sorted(expected - set(pbp_filenames))
    return {
        "expected_games": len(expected),
        "cached_files": len(pbp_filenames),
        "valid_files": len(valid),
        "invalid_files": len(invalid),
        "missing_files": len(missing),
        "missing": missing,
        "invalid": invalid,
    }
