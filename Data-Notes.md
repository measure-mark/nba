# Data Notes

Quirks and caveats of the external data sources. Things that are true of the data
itself, not of our code.

## ESPN player availability (wehoop archive)

Source: the season parquet files in
[sportsdataverse/wehoop-wnba-data](https://github.com/sportsdataverse/wehoop-wnba-data),
which is what `sportsdataverse.load_wnba_player_boxscore` reads. We fetch the files
directly by URL rather than taking the package as a dependency.

- Pull: `python scripts/wehoop_wnba_player_box.py data/wnba`
  → raw seasons in `data/wnba/raw/wehoop/` (gitignored), combined
  `data/wnba/wehoop_player_box.parquet`.
- Post-parse: `python scripts/espn_dnp.py data/wnba` → `data/wnba/espn_dnp.csv`.

### Scratch data starts in 2012

The archive covers 2003-2026, but `did_not_play` is only populated from **2012**
onward, and 2012 itself is partial (180 scratch rows against ~750-1,200 in every later
season). Treat **2013-2026** as the usable availability history. Seasons 2003-2011 have
box scores but contribute zero scratch rows, so they fall out of `espn_dnp.csv` on
their own — no date filter is needed, but do not read their absence as "nobody sat".

Those early seasons also omit the availability columns from the file entirely, which is
why `normalize()` reindexes against the full column list instead of intersecting with
what is present.

### `reason` is populated on every row, including players who played

ESPN stamps `reason = "COACH'S DECISION"` on all 126k player-games, not just the
scratches — a player who logged 40 minutes carries it too. Taken at face value that
makes every game look like a bench game. `normalize()` therefore blanks `reason`
wherever `did_not_play` is false, and only the surviving values are meaningful.

### Distinguishing "not chosen" from "unavailable"

The reason text is free-form and unnormalized: 316 distinct strings across the archive,
with `KNEE INJURY`, `RIGHT KNEE INJURY`, `LEFT KNEE`, `SORE LEFT KNEE` and `ACL` all
appearing separately. `scripts/espn_dnp.py` maps that vocabulary onto two fields:

- **`status`** — the distinction we actually want:
  - `not_chosen` — available, coach passed them over (`COACH'S DECISION`,
    `DID NOT DRESS - TEAM DECISION`). 54% of scratches.
  - `unavailable` — could not be used. 46%.
  - `unknown` — text no rule matched. Currently 2 rows, both with a null reason.
- **`reason`** — the sub-category: `coach_decision`, `injury`, `illness`, `personal`,
  `not_with_team`, `rest`, `suspension`, `undisclosed`.
- **`value`** — the raw ESPN string, kept so any classification is auditable.

Judgement calls baked into the rules:

- **`REST` counts as `unavailable`, not `not_chosen`.** A rested player was ruled out
  before the game; a `not_chosen` player was dressed and available all night. Only 60
  rows, but they are different events.
- **`INJURY/ILLNESS` resolves to `injury`.** It is genuinely ambiguous; both land under
  `unavailable`, so only the sub-category is affected.
- **Unmatched text stays `unknown` rather than defaulting to `unavailable`.** The
  residual is overwhelmingly medical, so a default would usually be right — and would
  silently absorb new ESPN vocabulary under a plausible-looking label. The script prints
  every unclassified string so `RULES` can be extended.

Two substring traps, both now regression-tested: `ILL` matches ACH**ILL**ES and `DISC`
matches UN**DISC**LOSED. Word boundaries matter in this vocabulary.

## Metadata store (Postgres)

`meta/` mirrors each provider into `source_*` tables keyed by that provider's own ids,
and keeps the canonical `players`/`teams`/`seasons`/`games` tables empty until a merge
step fills them. Bring it up and load WNBA:

```
docker compose up -d postgres meta
python -m meta.load wnba
```

Re-running a loader is safe: every write is an upsert, and the canonical FK columns
(`team_id`, `player_id`, …) are excluded from the update list, so a reload never undoes
a merge.

### The two WNBA sources do not agree on team codes

The two lists barely overlap. Basketball Reference's agg.csv only goes back to 2021, so
it holds ~16 codes; ESPN's parquet goes back to 2003 and holds 31.

```
bbref  ATL CHI CON DAL GSV IND LAS LVA MIN NYL PHO POR SAS SEA TOR WAS
espn   ALL ATL CHA CHI CLA CLE COL COOP CT DEL EAST GS HOU IND LOS MIN NYL PAR PHO
       POR SAC SAS SEA SPO STE TOR TUL USA WAS WEST WIL
```

Three separate problems live in that diff:

- **Different codes for the same club.** ESPN writes `LOS` where Basketball Reference
  writes `LAS`, `CT` where it writes `CON`, `GS` where it writes `GSV`.
- **Folded franchises ESPN still carries** (`TUL`, `CLE`, `CHA`, `HOU`, `SAC`, `COL`)
  that have no Basketball Reference counterpart in our window.
- **Rows that are not clubs at all**: `ALL`, `EAST`, `WEST`, `USA` are All-Star sides.

So matching cannot key off the code, and not every source team gets a canonical row —
which is why `source_teams.team_id` is nullable rather than required.

ESPN's parquet carries no club name and no scoring column, so `source_teams.name` and
`source_player_games.points` are NULL for that source.

### Team matching with a local LFM2

```
ollama serve &
ollama pull hf.co/LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_K_M
python -m meta.agent.team_matcher wnba --dry-run
```

The agent talks to the `nba-meta` MCP server on port 3001. At 1.2B and 4-bit the model
reliably calls `list_teams` and reads the result, but its groupings are not trustworthy
— it invents club names for codes it does not recognise. `--dry-run` prints the groups
it would have written instead of writing them; read them before dropping the flag.
