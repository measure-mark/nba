#!/usr/bin/env python3
"""Download ESPN WNBA game JSON and extract any historical availability data.

Example:
    python scripts/espn_wnba_availability.py 2025 data

Raw game responses are saved under ``<output-dir>/raw/espn/wnba/<season>/``.
The script intentionally saves the complete response before parsing it: ESPN's
historical response shape is not documented and the parser can be improved later
without re-downloading the season.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
USER_AGENT = "nba-availability-research/0.1 (historical-data-collector)"
REQUEST_TIMEOUT = (10, 45)
MAX_RETRIES = 5
MIN_REQUEST_GAP_SECONDS = 3.0
MAX_REQUEST_GAP_SECONDS = 6.0

OUTPUT_COLUMNS = [
    "game_id",
    "game_date",
    "team_id",
    "team_abbreviation",
    "player_id",
    "player_name",
    "availability_status",
    "absence_reason",
    "status_date",
    "status_detail",
    "source_json_path",
]

INJURY_WORDS = ("injur", "inactive", "didnotplay", "did_not_play", "availability")
RELATED_WORDS = INJURY_WORDS + ("status", "reason", "comment", "athlete")


class RequestPacer:
    """Ensure requests are sequential and separated by 3 + U(0, 3) seconds."""

    def __init__(self) -> None:
        self.last_request_at: float | None = None

    def wait(self) -> None:
        if self.last_request_at is None:
            return
        gap = random.uniform(MIN_REQUEST_GAP_SECONDS, MAX_REQUEST_GAP_SECONDS)
        remaining = gap - (time.monotonic() - self.last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def mark_request(self) -> None:
        self.last_request_at = time.monotonic()


def fetch_json(
    session: requests.Session, pacer: RequestPacer, url: str, params: dict[str, str]
) -> tuple[dict[str, Any], bytes]:
    """Fetch one non-empty JSON document, retrying only transient HTTP failures."""
    for attempt in range(MAX_RETRIES):
        pacer.wait()
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"request failed after {MAX_RETRIES} attempts: {exc}") from exc
            delay = 2**attempt
            print(f"network error for {response_url(url, params)}; retrying in {delay}s: {exc}")
            time.sleep(delay)
            continue
        finally:
            pacer.mark_request()

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"200 response was not JSON: {response.url}") from exc
            if not payload:
                raise RuntimeError(f"200 response contained empty JSON: {response.url}")
            if not isinstance(payload, dict):
                raise RuntimeError(f"200 response JSON was not an object: {response.url}")
            # Keep the original bytes, not a re-serialized approximation, in the raw cache.
            return payload, response.content

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == MAX_RETRIES - 1:
                break
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            print(f"HTTP {response.status_code} for {response.url}; retrying in {delay:.0f}s")
            time.sleep(delay)
            continue

        body_preview = response.text[:200].replace("\n", " ")
        raise RuntimeError(f"HTTP {response.status_code} for {response.url}: {body_preview!r}")

    raise RuntimeError(f"HTTP {response.status_code} after {MAX_RETRIES} attempts for {response.url}")


def response_url(url: str, params: dict[str, str]) -> str:
    request = requests.Request("GET", url, params=params).prepare()
    return request.url


def schedule_games(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return a de-duplicated schedule from ESPN scoreboard ``events``."""
    games: dict[str, dict[str, str]] = {}
    for event in payload.get("events", []):
        competitions = event.get("competitions", [])
        competitors = competitions[0].get("competitors", []) if competitions else []
        home = next((c.get("team", {}) for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c.get("team", {}) for c in competitors if c.get("homeAway") == "away"), {})
        game_id = str(event.get("id", ""))
        if not game_id or not home or not away:
            continue
        games[game_id] = {
            "game_id": game_id,
            "game_date": event.get("date", ""),
            "home_team": home.get("abbreviation", ""),
            "away_team": away.get("abbreviation", ""),
        }
    return sorted(games.values(), key=lambda game: (game["game_date"], game["game_id"]))


def key_is_related(key: str) -> bool:
    normalized = key.replace("_", "").lower()
    return any(word in normalized for word in RELATED_WORDS)


def key_is_injury_specific(key: str) -> bool:
    normalized = key.replace("_", "").lower()
    return any(word in normalized for word in INJURY_WORDS)


def walk_related_paths(value: Any, path: str = "$") -> set[str]:
    """Report all JSON paths whose field names look availability-related."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key_is_related(key):
                found.add(child_path)
            found.update(walk_related_paths(child, child_path))
    elif isinstance(value, list):
        for child in value:
            found.update(walk_related_paths(child, f"{path}[]"))
    return found


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        return value.get("displayName") or value.get("name") or value.get("description")
    return None


def first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = as_text(item.get(key))
        if value:
            return value
    return None


def availability_records(game: dict[str, str], payload: dict[str, Any]) -> list[dict[str, str | None]]:
    """Extract athlete-bearing injury/status objects without inventing missing fields.

    ESPN's schema changes. We retain only objects that identify an athlete and carry an
    injury-specific field, or a status combined with a reason/comment. The source JSON
    path remains in the output so ambiguous records are auditable.
    """
    records: list[dict[str, str | None]] = []

    def visit(value: Any, path: str, injury_context: bool = False) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child, f"{path}[]", injury_context)
            return
        if not isinstance(value, dict):
            return

        keys = tuple(value)
        has_injury_key = any(key_is_injury_specific(key) for key in keys)
        has_status = any(key.lower() == "status" for key in keys)
        has_explanation = any(
            key.lower() in {"reason", "comment", "shortcomment", "longcomment", "details"}
            for key in keys
        )
        athlete = value.get("athlete")
        athlete = athlete if isinstance(athlete, dict) else None

        if athlete and (injury_context or has_injury_key or (has_status and has_explanation)):
            team = value.get("team") if isinstance(value.get("team"), dict) else {}
            detail = first_text(value, ("longComment", "shortComment", "comment", "details", "description"))
            records.append(
                {
                    "game_id": game["game_id"],
                    "game_date": game["game_date"],
                    "team_id": as_text(team.get("id")),
                    "team_abbreviation": as_text(team.get("abbreviation")),
                    "player_id": as_text(athlete.get("id")),
                    "player_name": first_text(athlete, ("displayName", "fullName", "shortName", "name")),
                    "availability_status": first_text(value, ("availabilityStatus", "status")),
                    "absence_reason": first_text(value, ("reason", "injury", "type")),
                    "status_date": first_text(value, ("statusDate", "reportedDate", "lastUpdated")),
                    "status_detail": detail,
                    "source_json_path": path,
                }
            )

        for key, child in value.items():
            # ``athlete`` is metadata belonging to the availability object above.
            # Do not let that child inherit the context and become a duplicate row.
            child_context = injury_context or key_is_injury_specific(key)
            visit(child, f"{path}.{key}", child_context if key != "athlete" else False)

    visit(payload, "$")
    # A response can expose the same object through multiple sections; remove exact duplicates.
    return list({tuple(record.items()): record for record in records}.values())


def load_or_fetch_game(
    session: requests.Session, pacer: RequestPacer, raw_dir: Path, game_id: str
) -> tuple[dict[str, Any], bool]:
    path = raw_dir / f"{game_id}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"cached JSON is unreadable: {path}") from exc
        if not payload:
            raise RuntimeError(f"cached JSON is empty: {path}")
        return payload, False

    payload, raw_response = fetch_json(session, pacer, SUMMARY_URL, {"event": game_id})
    path.write_bytes(raw_response)
    return payload, True


def run(season: int, output_dir: Path) -> None:
    raw_dir = output_dir / "raw" / "espn" / "wnba" / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"espn_wnba_availability_{season}.csv"
    schedule_path = raw_dir / "schedule.json"
    pacer = RequestPacer()

    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        schedule_payload, schedule_raw = fetch_json(
            session, pacer, SCOREBOARD_URL, {"dates": str(season), "limit": "1000"}
        )
        schedule_path.write_bytes(schedule_raw)
        games = schedule_games(schedule_payload)
        if not games:
            raise RuntimeError(
                f"ESPN schedule response contained no complete WNBA games for {season}; "
                f"saved response to {schedule_path} for inspection"
            )

        rows: list[dict[str, str | None]] = []
        related_paths: Counter[str] = Counter()
        downloaded = 0
        games_with_data = 0
        for number, game in enumerate(games, start=1):
            payload, was_downloaded = load_or_fetch_game(session, pacer, raw_dir, game["game_id"])
            downloaded += was_downloaded
            paths = walk_related_paths(payload)
            related_paths.update(paths)
            records = availability_records(game, payload)
            if records:
                games_with_data += 1
                rows.extend(records)
            print(f"[{number}/{len(games)}] {game['game_id']} ({'downloaded' if was_downloaded else 'cached'})")

    pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_csv(output_path, index=False)
    print("\nDiagnostic summary")
    print(f"  schedule games: {len(games)}")
    print(f"  games downloaded this run: {downloaded}")
    print(f"  games containing availability records: {games_with_data}")
    print(f"  normalized records: {len(rows)}")
    print(f"  raw cache: {raw_dir}")
    print(f"  normalized CSV: {output_path}")
    print("  injury/availability-related JSON paths:")
    for path in sorted(related_paths):
        print(f"    {path}")
    if rows:
        print("  example records:")
        for row in rows[:5]:
            print("   ", json.dumps(row, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", type=int, help="WNBA calendar season, for example 2025")
    parser.add_argument("output_dir", type=Path, help="Base output directory, for example data")
    args = parser.parse_args()
    run(args.season, args.output_dir)


if __name__ == "__main__":
    main()
