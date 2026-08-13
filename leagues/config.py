from dataclasses import dataclass
from datetime import date
from pathlib import Path

from leagues.links import LinkScheme


@dataclass(frozen=True)
class LeagueConfig:
    """Everything that differs between leagues on the same scraping pipeline.

    Nothing here is a rate limit: the limit is per-IP against one host family, so it is
    shared across every league and lives in HostConfig instead.
    """

    key: str
    display_name: str
    base_url: str
    path_prefix: str
    data_root: Path
    regulation_minutes: int
    overtime_minutes: int
    period_labels: tuple[str, ...]
    season_spans_years: bool
    teams: tuple[str, ...] = ()
    enabled: bool = True

    @property
    def links(self) -> LinkScheme:
        return LinkScheme(self.path_prefix)

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw"

    def current_season(self, today: date) -> int:
        """The season label basketball-reference uses for a given day.

        NBA seasons straddle the new year and are labelled by the ending year, so
        October 2025 belongs to season 2026. The WNBA season sits inside one calendar
        year and is labelled by it.
        """
        if not self.season_spans_years:
            return today.year
        return today.year + 1 if today.month >= 10 else today.year

    def valid_game_minutes(self, max_overtimes: int = 4) -> list[int]:
        """Total player-minutes for a complete game: regulation, plus each OT period.

        NBA: 240 (5 x 48), then 265, 290, ... WNBA: 200 (5 x 40), then 225, 250, ...
        schedule.csv already contains 3OT and 4OT games, so the default reaches those.
        """
        return [
            self.regulation_minutes + n * self.overtime_minutes
            for n in range(max_overtimes + 1)
        ]


@dataclass(frozen=True)
class HostConfig:
    """The rate limit, which is per-IP and therefore shared by every league."""

    max_requests: int = 19
    window_seconds: int = 65
    min_gap_seconds: float = 3.0
