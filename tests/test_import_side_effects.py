"""Importing a module must not touch the filesystem.

Regression: basketballreference_boxscore_parser.py ran its aggregation loop at module
scope, so merely importing it walked the current working directory and overwrote
agg.csv. Inside a container -- where the daemon imports modules on startup and the cwd
holds real data -- that destroys the dataset.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "module",
    [
        # Ran its aggregation loop at module scope: import walked the cwd, wrote agg.csv.
        "basketballreference_boxscore_parser",
        # Ran os.chdir("../data") at module scope -- a process-global side effect -- and
        # rewrote player_map.json, renumbering every player id.
        "artifact_makers.make_player_map",
    ],
)
def test_import_writes_nothing_and_does_not_chdir(tmp_path, module):
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", f"import os; import {module}; print(os.getcwd())"],
        cwd=tmp_path, env=env, check=True, capture_output=True, text=True,
    )

    assert sorted(p.name for p in tmp_path.iterdir()) == []
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()
