import time

import requests

from leagues.config import LeagueConfig
from lib.helper_functions import link_to_file_name
from throttle.base import Throttle

# A stalled socket with no timeout blocks forever; requests defaults to no timeout.
DEFAULT_TIMEOUT = (5, 30)


class DownloadManager:
    """Fetches pages for one league, caching them under that league's raw directory.

    The throttle is injected rather than constructed here so that every league shares
    one budget -- basketball-reference limits per IP, not per league.
    """

    def __init__(self, league: LeagueConfig, throttle: Throttle, timeout=DEFAULT_TIMEOUT):
        self.league = league
        self.throttle = throttle
        self.timeout = timeout
        league.raw_dir.mkdir(parents=True, exist_ok=True)

    def download_if_new(self, link: str, verbose=False, max_retries=3, max_age_seconds=None):
        """returns True, webpage if freshly downloaded
        returns False, webpage if cached

        max_age_seconds re-fetches a cached page once it is older than that. Box scores
        and finished seasons never change, so they are cached forever (the default). An
        in-progress season's schedule page does change -- it gains games as they are
        played -- and without an age limit the scraper reads a frozen copy forever and
        can never discover a new game.
        """
        path = self.league.raw_dir / link_to_file_name(link)
        if path.exists() and not self._is_stale(path, max_age_seconds):
            if verbose:
                print(f"Returning cached version of: {path.name}")
            return False, path.read_bytes()

        url = f"{self.league.base_url}{link}"

        for attempt in range(max_retries):
            # Claim the slot before the request, so an in-flight or failed request
            # still counts against the budget.
            self.throttle.reserve()
            response = requests.get(url, timeout=self.timeout)

            if response.status_code == 429:
                # Being told to back off is exactly when we must not retry blindly.
                delay = float(response.headers.get("Retry-After", 60))
                if verbose:
                    print(f"429 for {url}, sleeping {delay}s")
                time.sleep(delay)
                continue

            if response.status_code != 200:
                raise RuntimeError(f"{response.status_code} for {url}")

            # Write via a temp file so an interrupted write can't poison the cache with
            # a truncated page that later looks like a successful download.
            tmp = path.with_suffix(".part")
            tmp.write_bytes(response.content)
            tmp.rename(path)
            return True, response.content

        raise RuntimeError(f"Rate limited {max_retries} times for {url}")

    @staticmethod
    def _is_stale(path, max_age_seconds) -> bool:
        if max_age_seconds is None:
            return False
        return time.time() - path.stat().st_mtime > max_age_seconds
