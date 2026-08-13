import re

from lib.helper_functions import validate_date


class LinkScheme:
    """Builds basketball-reference links, and decodes the cached filenames they map to.

    NBA and WNBA share one encoding -- 8-digit date, a game-number digit, then the
    3-letter home team code -- and differ only by a path prefix, so one class covers
    both. NCAA lives on a different host with slug team ids; when it lands it will need
    its own scheme, and LeagueConfig is the seam it plugs into.

    The round trip that matters is link -> cached filename -> (date, team):

        /boxscores/202105160TOR.html      -> boxscores_202105160TOR.html      -> 20210516, TOR
        /wnba/boxscores/202605170ATL.html -> wnba_boxscores_202605170ATL.html -> 20260517, ATL

    because link_to_file_name turns "/" into "_", which is what puts the league prefix
    on the front of the filename.
    """

    def __init__(self, path_prefix: str = ""):
        self.path_prefix = path_prefix
        self._root = f"/{path_prefix}" if path_prefix else ""
        # link_to_file_name strips the leading "/" then maps "/" -> "_", so the cached
        # name carries the same prefix with an underscore.
        name_prefix = f"{path_prefix}_" if path_prefix else ""
        self._filename_re = re.compile(
            rf"^{name_prefix}boxscores_(\d{{8}})\d([A-Z]{{3}})\.html$"
        )
        self._link_re = re.compile(
            rf"^{re.escape(self._root)}/boxscores/(\d{{8}})\d([A-Z]{{3}})\.html$"
        )

    def boxscore_link(self, date: str, home_team: str) -> str:
        validate_date(date)
        return f"{self._root}/boxscores/{date}0{home_team}.html"

    def schedule_link(self, team: str, season: int) -> str:
        return f"{self._root}/teams/{team}/{season}_games.html"

    def is_boxscore_link(self, href: str) -> bool:
        """Whether an href scraped off a schedule page is one of our box scores."""
        return self._link_re.match(href) is not None

    def matches_boxscore_filename(self, filename: str) -> bool:
        """Whether a cached file belongs to this league. Used to scan a raw directory."""
        return self._filename_re.match(filename) is not None

    def parse_boxscore_filename(self, filename: str) -> tuple[str, str]:
        """Cached filename -> (yyyymmdd, home team). Raises ValueError if it isn't ours."""
        m = self._filename_re.match(filename)
        if not m:
            raise ValueError(f"Not a {self.path_prefix or 'nba'} box score filename: {filename}")
        return m.group(1), m.group(2)
