#!/usr/bin/env python3
"""One-time pull of historical WNBA player box scores from the wehoop archive.

The sportsdataverse ``load_wnba_player_boxscore`` loader reads season parquet files
committed to https://github.com/sportsdataverse/wehoop-wnba-data. We fetch those files
directly rather than depending on the loader package: it is one URL per season, and it
keeps the raw archive on disk so the normalization below can be revised without
re-downloading.

Example:
    python scripts/wehoop_wnba_player_box.py data/wnba
    python scripts/wehoop_wnba_player_box.py data/wnba --start 2015 --end 2025 --refresh
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import pandas as pd

TREE_URL = "https://api.github.com/repos/sportsdataverse/wehoop-wnba-data/git/trees/main?recursive=1"
PARQUET_DIR = "wnba/player_box/parquet"
PARQUET_URL = f"https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-data/main/{PARQUET_DIR}"
REQUEST_TIMEOUT = 120

# ESPN reports availability per player-game. Everything else in the file is box-score
# detail we already scrape from basketball-reference, so we keep only the identifiers
# needed to join plus the availability fields that are the point of this pull.
KEEP_COLUMNS = [
    "game_id",
    "season",
    "season_type",
    "game_date",
    "athlete_id",
    "athlete_display_name",
    "team_id",
    "team_abbreviation",
    "opponent_team_abbreviation",
    "home_away",
    "starter",
    "minutes",
    "active",
    "ejected",
    "did_not_play",
    "reason",
]


def available_seasons() -> list[int]:
    """Read the season list from the archive rather than hardcoding a range."""
    with urllib.request.urlopen(TREE_URL, timeout=REQUEST_TIMEOUT) as response:
        tree = json.load(response)["tree"]
    prefix = f"{PARQUET_DIR}/player_box_"
    return sorted(
        int(entry["path"][len(prefix) : -len(".parquet")])
        for entry in tree
        if entry["path"].startswith(prefix) and entry["path"].endswith(".parquet")
    )


def download_season(season: int, raw_dir: Path, refresh: bool) -> Path:
    path = raw_dir / f"player_box_{season}.parquet"
    if path.exists() and not refresh:
        print(f"  {season}: cached ({path.stat().st_size / 1e6:.1f} MB)")
        return path
    with urllib.request.urlopen(f"{PARQUET_URL}/player_box_{season}.parquet", timeout=REQUEST_TIMEOUT) as response:
        payload = response.read()
    path.write_bytes(payload)
    print(f"  {season}: downloaded ({len(payload) / 1e6:.1f} MB)")
    return path


def cached_seasons(raw_dir: Path) -> list[int]:
    """Seasons already present in the local raw archive."""
    prefix = "player_box_"
    return sorted(
        int(path.stem[len(prefix) :])
        for path in raw_dir.glob(f"{prefix}*.parquet")
    )


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim to the availability columns and blank ``reason`` where it is meaningless.

    ESPN fills ``reason`` with "COACH'S DECISION" on every row, including players who
    logged minutes. Carrying that forward would make a played game look like a scratch,
    so the reason is retained only where ``did_not_play`` is true.

    Seasons before 2012 omit the availability columns altogether; reindexing against the
    full column set gives them as nulls so every season has the same shape.
    """
    trimmed = frame.reindex(columns=KEEP_COLUMNS)
    did_not_play = trimmed["did_not_play"].astype("boolean").fillna(False).astype(bool)
    return trimmed.assign(
        did_not_play=did_not_play,
        reason=trimmed["reason"].where(did_not_play),
        game_date=pd.to_datetime(trimmed["game_date"]).dt.date,
    )


def run(output_dir: Path, start: int | None, end: int | None, refresh: bool) -> None:
    raw_dir = output_dir / "raw" / "wehoop"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "wehoop_player_box.parquet"

    archive = available_seasons() if refresh or not cached_seasons(raw_dir) else cached_seasons(raw_dir)
    seasons = [season for season in archive if (start is None or season >= start) and (end is None or season <= end)]
    if not seasons:
        raise RuntimeError(f"the archive has no seasons in [{start}, {end}]")
    print(f"seasons {seasons[0]}-{seasons[-1]} ({len(seasons)} files) -> {raw_dir}")

    paths = [download_season(season, raw_dir, refresh) for season in seasons]
    combined = normalize(pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True))
    combined.to_parquet(output_path, index=False)

    scratches = combined[combined["did_not_play"]]
    print(f"\nwrote {len(combined):,} player-games to {output_path}")
    print(f"  games: {combined['game_id'].nunique():,}")
    print(f"  did-not-play rows: {len(scratches):,} ({len(scratches) / len(combined):.1%})")
    print(f"  rows missing a reason: {scratches['reason'].isna().sum():,}")
    print("  most common reasons:")
    for reason, count in scratches["reason"].value_counts().head(10).items():
        print(f"    {count:6,}  {reason}")
    print("  did-not-play rows by season:")
    for season, count in scratches.groupby("season").size().items():
        print(f"    {season}  {count:6,}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, help="Base output directory, for example data/wnba")
    parser.add_argument("--start", type=int, default=None, help="First season to pull (default: earliest available)")
    parser.add_argument("--end", type=int, default=None, help="Last season to pull (default: latest available)")
    parser.add_argument("--refresh", action="store_true", help="Re-download seasons already cached on disk")
    args = parser.parse_args()
    run(args.output_dir, args.start, args.end, args.refresh)


if __name__ == "__main__":
    main()
