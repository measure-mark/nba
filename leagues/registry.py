import os
from pathlib import Path

import yaml

from leagues.config import HostConfig, LeagueConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "leagues.yaml"


class LeagueRegistry:
    """Loads leagues.yaml into LeagueConfig objects.

    data_root resolves against DATA_ROOT (so the container can point at /app/data)
    falling back to <repo>/data.
    """

    def __init__(self, config_path: Path = CONFIG_PATH, data_root: Path | None = None):
        raw = yaml.safe_load(config_path.read_text())
        base = Path(data_root or os.environ.get("DATA_ROOT") or REPO_ROOT / "data")

        self.host = HostConfig(**raw["host"])
        self._leagues = {
            key: LeagueConfig(
                key=key,
                data_root=base / key,
                period_labels=tuple(spec.pop("period_labels")),
                teams=tuple(spec.pop("teams", ()) or ()),
                **spec,
            )
            for key, spec in raw["leagues"].items()
        }

    def get(self, key: str) -> LeagueConfig:
        if key not in self._leagues:
            raise KeyError(f"Unknown league {key!r}; known: {sorted(self._leagues)}")
        return self._leagues[key]

    def enabled(self) -> list[LeagueConfig]:
        """Enabled leagues, narrowed by the LEAGUES env var when it is set."""
        selected = os.environ.get("LEAGUES")
        keys = [k.strip() for k in selected.split(",")] if selected else list(self._leagues)
        return [self.get(k) for k in keys if self.get(k).enabled]
