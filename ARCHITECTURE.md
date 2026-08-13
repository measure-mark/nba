# Architecture

## Overview

A multi-league basketball-reference scraper and data model. It scrapes NBA and
WNBA (NCAA is configured but stubbed/disabled) box scores and schedules into
CSV/JSON artifacts under `data/<league>/`, which feed prediction models kept
outside this repo. A Redis-backed scraper daemon and a read-only MCP status
server can run as a long-lived stack via `docker compose`; the same code also
runs as one-off local scripts.

## Package map

- **`leagues/`** — per-league configuration. `config.py` defines `LeagueConfig`
  (base URL, path prefix, regulation/OT minutes, team codes, data root) and
  `HostConfig` (the shared rate-limit budget); `registry.py`'s `LeagueRegistry`
  loads `leagues.yaml` into `LeagueConfig` objects and filters by the `LEAGUES`
  env var; `links.py`'s `LinkScheme` builds basketball-reference links and
  decodes cached filenames back to (date, team).

- **`throttle/`** — rate limiting for the one shared per-IP budget.
  `base.py` defines the `Throttle` ABC (`reserve()`/`status()`); `memory.py`'s
  `InMemoryThrottle` is a sliding-window limiter for a single process (tests,
  one-off local runs); `redis_throttle.py`'s `RedisThrottle` does the same
  atomically across processes via a Lua script, keyed by Redis's own clock.

- **`status/`** — scrape/aggregation state in Redis. `store.py`'s
  `StatusStore` tracks per-league pull and aggregation status, an in-flight
  job marker, and the set of known leagues, all namespaced by league key.

- **`scraper/`** — the sweep and the daemon that runs it. `sweep.py`'s
  `LeagueSweeper` does one pass per league: fetch team schedule pages, collect
  box score links off them, download missing box scores, aggregate; one bad
  team code is skipped rather than aborting the sweep. `daemon.py` builds a
  `LeagueSweeper` per enabled league and loops it on an interval.

- **`mcp_server/`** — read-only MCP status server. `server.py` exposes tools
  (e.g. `get_status`) backed by `LeagueRegistry` and `StatusStore`/Redis,
  for querying scrape/aggregation state without touching the scraper.

- **`data_model/`** — typed readers over the on-disk artifacts. `schedule.py`'s
  `Schedule` finds a team's previous game (used for backtesting);
  `box_score_store.py`'s `BoxScoreStore` loads per-game player box score rows
  for one league and asserts the player count against a hardcoded tripwire
  (1442 for NBA) to detect silent player-id renumbering; `func.py` holds legacy
  `bs_filename_to_*` helpers that predate multi-league support, backed by a
  module-level default NBA `LinkScheme`.

- **`lib/`** — small stateless helpers used across packages:
  `link_to_file_name`, `validate_date`, `is_zero` (float-tolerance equality).

- **`model/`** — prediction scaffolding, not the trained models themselves.
  `model.py`'s `Model` is an unimplemented base for per-game prediction.
  `minutes/` holds minutes-played models: `__init__.py`'s
  `check_minuntes_make_sense` validates a game's total minutes against the
  league's regulation/OT minutes; `lagged_minutes.py`'s `LagMinutesOneGame`
  uses a player's previous game's minutes; `actual_minutes_model_normalized.py`
  normalizes actual minutes.

- **`artifact_makers/`** — turns cached raw HTML into the CSV/JSON artifacts.
  `make_minimal_box_scores.py` parses one box score page's stats tables;
  `aggregate.py` finds a league's cached box score files (via its
  `LinkScheme`, not a hardcoded regex) and aggregates them into `agg.csv`;
  `make_team_map.py` and `make_player_map.py` derive `team_map.json` and
  `player_map.json` from `agg.csv` (the player map is deliberately not rerun
  casually — rerunning renumbers every player id); `nba_box_scores.py` holds a
  standalone `convertMinutes` helper.

- **Root-level `.py` files**: `download_manager.py`'s `DownloadManager`
  fetches and caches pages for one league through an injected `Throttle`, with
  retry-on-429 and an optional cache max-age for in-progress schedules.
  `basketballreference_boxscore_parser.py` is an older standalone
  parse-and-aggregate script (`parseTable`, `get_minimal_stats`, a `main()`
  that walks the cwd for `boxscores_*.html`); its `main()` runs only under
  `if __name__ == "__main__"`, so importing it is side-effect free.

- **`tests/`** — pytest suite exercising rate limiting, download caching,
  the link/filename contract, minutes-validation rules, status-store
  namespacing, sweep behavior, aggregation, and import-time side effects.
  `conftest.py` provides shared fixtures off `LeagueRegistry`.

## Data flow

1. `scraper.daemon` (or a manual script) builds a `LeagueRegistry` from
   `leagues/leagues.yaml` and, per enabled league, a `LeagueSweeper` wired to
   a `DownloadManager` and a shared `RedisThrottle`.
2. `LeagueSweeper.sweep()` fetches each team's schedule page through
   `DownloadManager` (caching raw HTML under `data/<league>/raw/`,
   gitignored), collects box score links off it via `LinkScheme`, then
   downloads any box scores not already cached.
3. `artifact_makers.aggregate` reads the cached box score HTML and writes
   `data/<league>/agg.csv`. `make_team_map.py` and `make_player_map.py` derive
   `team_map.json` and `player_map.json` from that CSV.
4. `data_model.Schedule` and `data_model.BoxScoreStore` read
   `data/<league>/schedule.csv` and `agg.csv`/`player_map.json` respectively,
   for use by `model/` (minutes-played models) and by downstream ML models
   kept outside this repo.
5. Throughout, `status.StatusStore` records per-league pull/aggregation
   progress in Redis, which `mcp_server.server` exposes read-only via MCP
   tools.

## MCP servers

- **Project-configured (`.mcp.json`, `.claude/settings*.json`, `.vscode/`)**:
  none. No `.mcp.json` exists at the repo root, and neither `.claude/settings.json`
  nor `.claude/settings.local.json` nor `.vscode/settings.json` declare an MCP
  server. `.vscode/settings.json` only sets pytest test-discovery options.
- **This repo also builds its own MCP server** (`mcp_server/server.py`,
  package name `nba-status`, run via `python -m mcp_server.server` or the
  `mcp` service in `docker-compose.yml`, reachable at
  `http://localhost:8000/mcp` and addable with
  `claude mcp add --transport http nba-status http://localhost:8000/mcp` per
  `README.md`). This is an artifact the repo produces, not a project-level
  Claude Code MCP registration; it is not present in `.mcp.json`.
- The `mcp` and `redis` packages it imports are not installed in the ambient
  Python on this machine (`ModuleNotFoundError` for both, and for `fakeredis`);
  they are declared as dependencies in `environment.yml` and
  `pyproject.toml`, so they are expected to resolve inside the project's conda
  env / container, not in a bare system Python.

## Subagents

`.claude/agents/`:

- **`repo-doc-keeper.md`** — regenerates `ARCHITECTURE.md`/`DIVERGENCE.md`
  from a survey of the repo (this agent).
- **`test-auditor.md`** — audits `tests/` for missing coverage and low-value
  existing tests.
- **`todo-triage.md`** — sorts repo TODOs (grepped `TODO`/`FIXME`/`XXX`/`HACK`
  plus the README TODO list) into actionable/blocked/stale with a proposed
  next step for each.

## Environment & tests

- **Env**: `environment.yml` (conda, `python=3.14`) — pandas, numpy,
  beautifulsoup4, requests, pyyaml, pytest, ipython, plus pip-installed
  redis, mcp, fakeredis. `pyproject.toml` mirrors the runtime deps and puts
  pytest/fakeredis/ipython under an optional `dev` extra; it sets
  `pythonpath = ["."]` and `testpaths = ["tests"]` so the repo root (not just
  `tests/`) is importable during collection.
- **Local run**: `conda env create -f environment.yml && conda activate nba
  && pytest`.
- **Container run**: `docker compose up -d` starts `redis`, `scraper`
  (`python -m scraper.daemon`), and `mcp` (`python -m mcp_server.server`);
  `docker-compose.yml` builds its image inline via `dockerfile_inline`.
- **Tests**: run via `pytest` from the repo root; `tests/` covers throttle,
  download caching, link/filename parsing, minutes-validation rules, the
  status store, sweep behavior, aggregation, and import-time side effects.

---
Generated against commit `330049b`.
