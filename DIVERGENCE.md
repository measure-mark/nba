# Divergence report

Compared against commit `330049b` plus the current (largely uncommitted)
working tree.

## Subagent prompts reference deleted/renamed files

- **`.claude/agents/todo-triage.md:35`** — doc says: "a TODO to move
  `request_throttle.py` to a Redis-lock algorithm is blocked until the Redis
  container exists." Code says: `request_throttle.py` no longer exists; it was
  replaced by the `throttle/` package, whose `throttle/redis_throttle.py`
  already implements an atomic Redis-Lua-script throttle (`RedisThrottle`),
  and `docker-compose.yml` already stands up a `redis` service. The example is
  stale on two counts — the filename and the "blocked" status of the work it
  describes. Fix: update the example to a real current TODO (e.g. one of the
  four lines now in the root `TODO` file), or drop the example.

- **`.claude/agents/test-auditor.md:18`** — doc says: "Assert tautologies or
  sanity-check nothing (e.g. `assert 2==2` in `tests/test_func.py`)." Code
  says: `tests/test_func.py` is deleted (`git status` shows `D
  tests/test_func.py`); no such file exists. Fix: replace the example with a
  file that exists, or drop the specific citation and keep the general
  pattern description.

## MCP server package does not resolve in the ambient environment

- The `mcp` package that `mcp_server/server.py` imports (`from mcp.server
  import MCPServer`), along with `redis` and `fakeredis`, is not importable
  in the system Python on this machine (`ModuleNotFoundError` for all three).
  They are correctly declared in `environment.yml` and `pyproject.toml`, so
  this is expected once the `nba` conda env (or the Docker image) is actually
  built — but nothing in `README.md` flags that `pytest`/`mcp_server` will
  fail outside that env. Not a code bug; worth a one-line note in `README.md`
  ("requires the `nba` conda env; a bare system Python will not have
  `mcp`/`redis`/`fakeredis`") so a fresh clone doesn't read the failure as
  broken code.

## Test coverage gaps against `tests/`'s own pattern

- `tests/` has focused, purpose-tied tests for `throttle/`, `download_manager.py`,
  `leagues/links.py`, `model/minutes/__init__.py` (the minutes-completeness
  rule), `status/store.py`, `scraper/sweep.py`, and `artifact_makers/aggregate.py`
  — but `model/minutes/lagged_minutes.py`, `model/minutes/actual_minutes_model_normalized.py`,
  `model/model.py`, `artifact_makers/make_team_map.py`, and
  `artifact_makers/nba_box_scores.py` have no corresponding tests, unlike
  their package siblings. Not necessarily a defect (this is a report, not a
  mandate to add tests per-file), but it's the kind of asymmetry the repo's
  own `test-auditor` subagent is built to catch.

## `artifact_makers/nba_box_scores.py` is unimported

- No package or test imports `artifact_makers.nba_box_scores`
  (`convertMinutes`); it is not wired into `aggregate.py`'s pipeline or
  anything else in the tree. Either dead code left over from an earlier
  pipeline shape, or a helper intended for a caller that was never added.
  Fix: confirm with the repo owner whether it's still needed; if not, delete
  it (and its absence from `tests/` stops being an asymmetry).
