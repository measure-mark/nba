#!/usr/bin/env python3
"""Classify ESPN did-not-play rows as "not chosen" vs "unavailable".

A player-game with no minutes means one of two very different things, and the model
cares about the difference: the coach had the player available and passed them over
("did not play"), or the player could not be used at all ("did not dress"). ESPN records
only a free-text ``reason``, so this post-parser maps that vocabulary onto a status.

Run scripts/wehoop_wnba_player_box.py first to populate the raw archive.

Example:
    python scripts/espn_dnp.py data/wnba
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.wehoop_wnba_player_box import normalize

OUTPUT_COLUMNS = ["player_name", "player_id", "date", "status", "reason", "value", "source_file"]

NOT_CHOSEN = "not_chosen"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

# Ordered (pattern, status, reason) rules; the first match wins, so the specific
# categories are listed before the broad injury vocabulary that would swallow them.
# Every pattern was derived from the 316 distinct reason strings in the 2012-2026
# archive -- see Data-Notes.md.
RULES: list[tuple[str, str, str]] = [
    (r"COACH'?S DECISION|TEAM DECISION", NOT_CHOSEN, "coach_decision"),
    (r"SUSPEND|INELIGIBLE", UNAVAILABLE, "suspension"),
    (r"NOT WITH TEAM|DID NOT TRAVEL|OVERSEAS|NATIONAL TEAM|OLYMPIC|TRADE|G LEAGUE", UNAVAILABLE, "not_with_team"),
    (r"PERSONAL|FAMILY|BEREAVE|MENTAL HEALTH|MATERNITY|PREGNAN", UNAVAILABLE, "personal"),
    (r"\bREST\b|LOAD MANAGEMENT|FATIGUE", UNAVAILABLE, "rest"),
    (r"INJUR", UNAVAILABLE, "injury"),
    (
        r"\bILL|SICK|\bFLU\b|COVID|HEALTH & SAFETY|MIGRAINE|VERTIGO|DEHYDRAT|KIDNEY|"
        r"CROHN|MEDICAL|EVALUAT|COLLAPSED LUNG|DENTAL",
        UNAVAILABLE,
        "illness",
    ),
    (
        # Body parts, mechanisms of injury, and treatment/recovery language.
        r"CONCUSSION|SURGERY|REHAB|RECONDITION|RECOVERY|PROTOCOL|SPRAIN|STRAIN|FRACTUR|BROKEN|"
        r"TEAR|TORN|RUPTUR|BRUISE|CONTUSION|SORE|STIFF|SPASM|INFLAM|TENDIN|TENDON|LIGAMENT|"
        r"MENISCUS|BONE|CYST|DISLOCAT|STRESS REACTION|PLANTAR|FASCIITIS|\bDISC\b|POINTER|"
        r"KNEE|ANKLE|FOOT|HEEL|TOE|ACHILLES|\bACL\b|\bMCL\b|HAMSTRING|CALF|GROIN|\bHIP\b|"
        r"BACK|SHOULDER|WRIST|THUMB|FINGER|HAND|\bARM\b|ELBOW|\bLEG\b|SHIN|QUAD|THIGH|"
        r"GLUTE|ADDUCTOR|ABDUCTOR|PATELLA|TIBIA|FIBULA|ULNAR|RHOMBOID|NECK|HEAD|\bRIB\b|"
        r"STERNUM|ABDOM|CHEST|FACE|FACIAL|NOSE|NASAL|\bJAW\b|MOUTH|\bEYE\b|LOWER BODY|"
        r"STRENGTHEN",
        UNAVAILABLE,
        "injury",
    ),
    (r"UNDISCLOSED|DID NOT DRESS|INACTIVE", UNAVAILABLE, "undisclosed"),
]


def classify(reasons: pd.Series) -> pd.DataFrame:
    """Map raw reason text to a (status, reason) pair, vectorized over the whole column.

    Unmatched text is left as ``unknown`` rather than being folded into a bucket -- a
    silent default would hide new ESPN vocabulary behind a plausible-looking label.
    """
    text = reasons.fillna("").str.upper()
    status = pd.Series(UNKNOWN, index=reasons.index)
    category = pd.Series(UNKNOWN, index=reasons.index)
    for pattern, rule_status, rule_reason in RULES:
        unmatched = status.eq(UNKNOWN)
        hits = unmatched & text.str.contains(pattern, regex=True, na=False)
        status = status.mask(hits, rule_status)
        category = category.mask(hits, rule_reason)
    return pd.DataFrame({"status": status, "reason": category})


def season_frame(path: Path) -> pd.DataFrame:
    """Read one season parquet and return only its did-not-play rows."""
    frame = normalize(pd.read_parquet(path))
    scratches = frame[frame["did_not_play"]]
    return scratches.assign(source_file=path.name)


def run(output_dir: Path) -> None:
    raw_dir = output_dir / "raw" / "wehoop"
    paths = sorted(raw_dir.glob("player_box_*.parquet"))
    if not paths:
        raise RuntimeError(f"no season parquet files in {raw_dir}; run wehoop_wnba_player_box.py first")

    scratches = pd.concat([season_frame(path) for path in paths], ignore_index=True)
    classified = classify(scratches["reason"])
    output = (
        scratches.rename(columns={"athlete_display_name": "player_name", "athlete_id": "player_id"})
        .assign(
            date=scratches["game_date"],
            status=classified["status"],
            reason=classified["reason"],
            value=scratches["reason"],
        )
        .reindex(columns=OUTPUT_COLUMNS)
        .sort_values(["date", "player_name"])
    )
    output_path = output_dir / "espn_dnp.csv"
    output.to_csv(output_path, index=False)

    print(f"wrote {len(output):,} did-not-play rows to {output_path}")
    print(f"  seasons: {paths[0].stem[-4:]}-{paths[-1].stem[-4:]}")
    print("\n  status:")
    for status, count in output["status"].value_counts().items():
        print(f"    {count:7,}  ({count / len(output):5.1%})  {status}")
    print("\n  reason:")
    for reason, count in output["reason"].value_counts().items():
        print(f"    {count:7,}  ({count / len(output):5.1%})  {reason}")
    unknown = output[output["status"] == UNKNOWN]
    if not unknown.empty:
        print(f"\n  unclassified reason text ({unknown['value'].nunique()} distinct) -- extend RULES:")
        for value, count in unknown["value"].value_counts(dropna=False).items():
            print(f"    {count:5,}  {value!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, help="Base output directory, for example data/wnba")
    args = parser.parse_args()
    run(args.output_dir)


if __name__ == "__main__":
    main()
