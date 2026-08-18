import subprocess
import sys

import pandas as pd
import pytest

from scripts.espn_dnp import classify


@pytest.mark.parametrize(
    "value, status, reason",
    [
        # The distinction the classifier exists to make: passed over vs unable to play.
        ("COACH'S DECISION", "not_chosen", "coach_decision"),
        ("DID NOT DRESS - TEAM DECISION", "not_chosen", "coach_decision"),
        ("DID NOT DRESS - INJURY/ILLNESS", "unavailable", "injury"),
        ("DID NOT DRESS", "unavailable", "undisclosed"),
        ("LEFT ANKLE", "unavailable", "injury"),
        ("NON-COVID ILLNESS", "unavailable", "illness"),
        ("NOT WITH TEAM - PREGNANCY", "unavailable", "not_with_team"),
        ("SUSPENDED BY LEAGUE", "unavailable", "suspension"),
        ("PERSONAL REASONS", "unavailable", "personal"),
        ("REST", "unavailable", "rest"),
    ],
)
def test_classify_maps_reason_text_to_status(value, status, reason):
    result = classify(pd.Series([value])).iloc[0]
    assert (result["status"], result["reason"]) == (status, reason)


@pytest.mark.parametrize(
    "value, reason",
    [
        ("ACHILLES", "injury"),  # regression: "ILL" inside ACH-ILL-ES read as illness
        ("UNDISCLOSED", "undisclosed"),  # regression: "DISC" inside UN-DISC-LOSED read as injury
    ],
)
def test_classify_does_not_match_medical_words_as_substrings(value, reason):
    assert classify(pd.Series([value])).iloc[0]["reason"] == reason


def test_classify_leaves_unrecognized_text_unknown():
    """A silent default would hide new ESPN vocabulary behind a plausible label."""
    result = classify(pd.Series(["SOME BRAND NEW ESPN PHRASE", None])).squeeze()
    assert list(result["status"]) == ["unknown", "unknown"]


def test_script_entrypoint_supports_documented_direct_execution():
    """Regression guard for ``python scripts/espn_dnp.py ...`` import path handling."""
    result = subprocess.run(
        [sys.executable, "scripts/espn_dnp.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Classify ESPN did-not-play rows" in result.stdout
