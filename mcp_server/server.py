import os
import time
from datetime import UTC, datetime

import pandas as pd
import redis
from mcp.server import MCPServer

from artifact_makers.aggregate import aggregate_box_scores, cached_box_scores
from artifact_makers.make_official_map import make_official_map
from artifact_makers.make_player_map import make_player_map
from artifact_makers.make_team_map import make_team_map
from leagues.registry import LeagueRegistry
from scraper.play_by_play import play_by_play_coverage
from status.store import StatusStore
from throttle.redis_throttle import RedisThrottle

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATASETS = ("schedules", "boxscores", "pbp")
ARTIFACTS = ("agg", "team_map", "player_map", "official_map")

mcp = MCPServer("nba-status", instructions="Read-only status for the basketball-reference scraper.")
registry = LeagueRegistry()
_redis = redis.from_url(REDIS_URL)
store = StatusStore(_redis)


def _leagues(league: str | None):
    return [registry.get(league)] if league else registry.enabled()


@mcp.tool()
def get_status(league: str | None = None) -> dict:
    """Deployment config, pull/aggregation status, and the shared rate-limit window.

    league: restrict per-league sections to one league key (e.g. "wnba"). Omit for
    all enabled leagues. The rate limit is global -- one window covers every league,
    since the limit is per-IP against one host.

    `stale` under `aggregation` means a box score was cached after the last
    aggregation run, so agg.csv no longer reflects everything on disk.
    """
    leagues = {}
    for lg in _leagues(league):
        artifacts = {a: store.get_aggregation(lg.key, a) for a in ARTIFACTS}
        newest = _newest_raw_mtime(lg)
        last_run = artifacts.get("agg", {}).get("last_run")
        leagues[lg.key] = {
            "display_name": lg.display_name,
            "base_url": lg.base_url + (f"/{lg.path_prefix}" if lg.path_prefix else ""),
            "regulation_minutes": lg.regulation_minutes,
            "season_spans_years": lg.season_spans_years,
            "data_root": str(lg.data_root),
            "enabled": lg.enabled,
            "pull": {
                "inflight": store.get_inflight(lg.key),
                **{ds: store.get_pull(lg.key, ds) for ds in DATASETS},
            },
            "aggregation": {
                "artifacts": artifacts,
                "newest_raw_file": newest.isoformat() if newest else None,
                "stale": bool(newest and last_run and newest > datetime.fromisoformat(last_run)),
            },
        }
    return {
        "leagues": leagues,
        "rate_limit": RedisThrottle(_redis, registry.host).status(),
    }


@mcp.tool()
def get_coverage(league: str, season: int | None = None) -> dict:
    """What games we hold for a league, including play-by-play completeness.

    Reads the league's agg.csv rather than Redis -- the data on disk is the only honest
    answer to "what do we have", since Redis only records the last run. Play-by-play
    coverage compares cached PBP pages to cached box scores, so it works before an
    aggregation has run.
    """
    lg = registry.get(league)
    agg = lg.data_root / "agg.csv"
    cached = cached_box_scores(lg)
    pbp = play_by_play_coverage(
        lg, cached, _season_years(lg, season) if season is not None else None
    )
    if not agg.exists():
        return {
            "league": league,
            "season": season,
            "agg_csv": None,
            "cached_box_scores": len(cached),
            "play_by_play": pbp,
        }

    df = pd.read_csv(agg, usecols=["filename"])
    dates = pd.Series(
        [lg.links.parse_boxscore_filename(fn)[0] for fn in df.filename.unique()]
    ).sort_values()
    if season is not None:
        dates = dates[dates.str[:4].astype(int).isin(_season_years(lg, season))]

    return {
        "league": league,
        "season": season,
        "games": len(dates),
        "cached_box_scores": len(cached),
        "first_game": dates.iloc[0] if len(dates) else None,
        "last_game": dates.iloc[-1] if len(dates) else None,
        "distinct_game_dates": int(dates.nunique()),
        "play_by_play": pbp,
    }


@mcp.tool()
def build_artifacts(league: str) -> dict:
    """Build agg.csv and its team, player, and official maps for one league.

    The maps are generated from the newly aggregated dataset, so every artifact is
    scoped to the requested league and reflects the same source files.
    """
    lg = registry.get(league)
    start_time = time.time()

    # Step 1: Aggregate box scores
    rows_out, source_files = aggregate_box_scores(lg)
    agg_duration = time.time() - start_time
    store.aggregation_ran(lg.key, "agg", agg_duration, rows_out, source_files)

    team_map_duration = 0.0
    player_map_duration = 0.0
    official_map_duration = 0.0
    teams_found = 0
    players_found = 0
    officials_found = 0

    if rows_out > 0:
        # Step 2: Generate team map
        map_started = time.time()
        team_map = make_team_map(lg)
        team_map_duration = time.time() - map_started
        store.aggregation_ran(
            lg.key, "team_map", team_map_duration, len(team_map), source_files
        )
        teams_found = len(team_map)

        # Step 3: Generate official map
        map_started = time.time()
        official_map = make_official_map(lg)
        official_map_duration = time.time() - map_started
        store.aggregation_ran(
            lg.key,
            "official_map",
            official_map_duration,
            len(official_map),
            source_files,
        )
        officials_found = len(official_map)

        # Step 4: Generate player map
        map_started = time.time()
        player_map = make_player_map(lg)
        player_map_duration = time.time() - map_started
        store.aggregation_ran(
            lg.key, "player_map", player_map_duration, len(player_map), source_files
        )
        players_found = len(player_map)

    return {
        "league": league,
        "aggregation": {
            "rows_written": rows_out,
            "source_files_parsed": source_files,
            "duration_s": round(agg_duration, 3),
            "agg_csv_path": str(lg.data_root / "agg.csv"),
        },
        "team_map": {
            "teams_found": teams_found,
            "duration_s": round(team_map_duration, 3),
            "team_map_path": str(lg.data_root / "team_map.json"),
        },
        "player_map": {
            "players_found": players_found,
            "duration_s": round(player_map_duration, 3),
            "player_map_path": str(lg.data_root / "player_map.json"),
        },
        "official_map": {
            "officials_found": officials_found,
            "duration_s": round(official_map_duration, 3),
            "official_map_path": str(lg.data_root / "official_map.json"),
        },
    }


def _season_years(lg, season: int) -> set[int]:
    return {season - 1, season} if lg.season_spans_years else {season}


def _newest_raw_mtime(lg) -> datetime | None:
    if not lg.raw_dir.exists():
        return None
    mtimes = [p.stat().st_mtime for p in lg.raw_dir.iterdir() if p.is_file()]
    return datetime.fromtimestamp(max(mtimes), UTC) if mtimes else None


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", 8000)),
    )
