import os
from datetime import UTC, datetime

import pandas as pd
import redis
from mcp.server import MCPServer

from artifact_makers.aggregate import aggregate_box_scores, cached_box_scores
from artifact_makers.make_player_map import make_player_map
from leagues.registry import LeagueRegistry
from status.store import StatusStore
from throttle.redis_throttle import RedisThrottle

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATASETS = ("schedules", "boxscores")
ARTIFACTS = ("agg", "team_map", "player_map")

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
    """What games we actually hold for a league: date range, counts, and missing dates.

    Reads the league's agg.csv rather than Redis -- the data on disk is the only honest
    answer to "what do we have", since Redis only records the last run.
    """
    lg = registry.get(league)
    agg = lg.data_root / "agg.csv"
    cached = cached_box_scores(lg)
    if not agg.exists():
        return {"league": league, "agg_csv": None, "cached_box_scores": len(cached)}

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
    }


@mcp.tool()
def build_artifacts(league: str) -> dict:
    """Aggregate box scores into agg.csv and generate player_map.json.

    This two-step process parses all cached box scores and creates the aggregated
    dataset and player map for the league.
    """
    lg = registry.get(league)

    # Step 1: Aggregate box scores
    rows_out, source_files = aggregate_box_scores(lg)
    store.set_aggregation(
        lg.key,
        "agg",
        {
            "last_run": datetime.now(UTC).isoformat(),
            "rows_out": str(rows_out),
            "source_files": str(source_files),
        }
    )

    # Step 2: Generate player map
    if rows_out > 0:
        player_map = make_player_map(lg)
        store.set_aggregation(
            lg.key,
            "player_map",
            {
                "last_run": datetime.now(UTC).isoformat(),
                "player_count": str(len(player_map)),
            }
        )
        players_found = len(player_map)
    else:
        players_found = 0

    return {
        "league": league,
        "aggregation": {
            "rows_written": rows_out,
            "source_files_parsed": source_files,
            "agg_csv_path": str(lg.data_root / "agg.csv"),
        },
        "player_map": {
            "players_found": players_found,
            "player_map_path": str(lg.data_root / "player_map.json"),
        }
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
