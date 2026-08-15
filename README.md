# nba

Scrapes basketball-reference into CSV artifacts that feed a prediction model. The ML
models are not in this repo, just the scaffolding.

Covers **NBA** and **WNBA**; NCAA is stubbed in config but not implemented.

## Conventions

* for gamedates, we use YYYYMMDD format
* for teams, we use the three letter codes from basketball reference
* seasons use basketball-reference's labelling: NBA seasons straddle the new year and
  are named for the ending year (2019 = 2018-19); WNBA seasons sit inside one year

## Layout

```
leagues/          per-league config (leagues.yaml) + the link/filename convention
throttle/         rate limiting: one shared budget, in-memory or Redis-backed
status/           scrape + aggregation state in Redis
scraper/          the sweep and the daemon that runs it
mcp_server/       read-only MCP status server
data/<league>/    agg.csv, schedule.csv, team_map.json, player_map.json
data/<league>/raw/  cached box-score and play-by-play HTML (gitignored)
```

Adding a league means adding an entry to `leagues/leagues.yaml` — no code change,
unless its URL shape differs from the NBA/WNBA one (as NCAA's does).

## Running

Local:

```bash
conda env create -f environment.yml && conda activate nba && pytest
```

Full stack (redis + scraper daemon + MCP server):

```bash
docker compose up -d
```

Then point Claude Code at the status server:

```bash
claude mcp add --transport http nba-status http://localhost:8000/mcp
```

## Rate limiting

basketball-reference limits per IP, not per league, so **all leagues share one budget**
(`br:ratelimit:requests` in Redis). The window lives in Redis rather than process
memory so that a restarted container doesn't reset it and immediately burst.

## The scraper is a backfiller

This is the thing to understand before reading `scraper/`. The scraper's job is to make
the local cache match a target set of seasons, and at 19 requests / 65s that job runs
for days or weeks. It is a long-lived worker, not a cron tick.

There is **one mode**. It works the target down with no pause beyond the rate limit;
once a pass downloads nothing new it has caught up and idles until it is worth looking
again. Incremental daily pulling is not a second mode — it is what the same loop does
when the backlog happens to be empty.

Set the target in `.env`:

```
LEAGUES=wnba
SEASONS=2015-2025
```

Then just bring it up. It keeps going across restarts and reboots:

```bash
docker compose up -d
```

Progress is visible through the MCP server (`get_status`, `get_coverage`). The run
is resumable — the cache is on disk, so an interrupted run picks up where it stopped.
Finished seasons are never re-fetched; only the in-progress season's schedule pages
expire, which is how new games get discovered.

Each discovered box score also has its play-by-play page cached. `get_coverage` reports
PBP availability, including cached files that are missing the required `table#pbp`.

## TODO

* figure out how to handle nba cup/in season tournament
* WNBA has no `schedule.csv` or `player_map.json` yet; `Schedule` and the `pid` column
  need them (the box scores in `agg.csv` work without either)
