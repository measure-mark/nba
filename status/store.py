from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StatusStore:
    """Scrape and aggregation state, in Redis.

    Keys (all values are strings; timestamps are ISO-8601 UTC):

        status:{league}:pull:{dataset}   HASH   last_started, last_finished, last_error,
                                                files_new, files_cached
        status:{league}:agg:{artifact}   HASH   last_run, duration_s, rows_out, source_files
        status:{league}:inflight         STRING current job id, with a TTL
        status:leagues                   SET    league keys this deployment knows about

    Every key is namespaced by league so two leagues sweeping concurrently cannot
    overwrite each other's status.
    """

    def __init__(self, redis_client):
        self.r = redis_client

    def register_leagues(self, league_keys) -> None:
        if league_keys:
            self.r.sadd("status:leagues", *league_keys)

    def known_leagues(self) -> list[str]:
        return sorted(k.decode() for k in self.r.smembers("status:leagues"))

    # -- pulls ---------------------------------------------------------------

    def pull_started(self, league: str, dataset: str) -> None:
        self.r.hset(
            f"status:{league}:pull:{dataset}",
            mapping={"last_started": _now(), "last_error": ""},
        )

    def pull_finished(self, league: str, dataset: str, files_new: int, files_cached: int) -> None:
        self.r.hset(
            f"status:{league}:pull:{dataset}",
            mapping={
                "last_finished": _now(),
                "files_new": files_new,
                "files_cached": files_cached,
            },
        )

    def pull_failed(self, league: str, dataset: str, error: str) -> None:
        self.r.hset(f"status:{league}:pull:{dataset}", mapping={"last_error": f"{_now()} {error}"})

    def get_pull(self, league: str, dataset: str) -> dict:
        return _decode(self.r.hgetall(f"status:{league}:pull:{dataset}"))

    # -- aggregations --------------------------------------------------------

    def aggregation_ran(
        self, league: str, artifact: str, duration_s: float, rows_out: int, source_files: int
    ) -> None:
        self.r.hset(
            f"status:{league}:agg:{artifact}",
            mapping={
                "last_run": _now(),
                "duration_s": round(duration_s, 3),
                "rows_out": rows_out,
                "source_files": source_files,
            },
        )

    def get_aggregation(self, league: str, artifact: str) -> dict:
        return _decode(self.r.hgetall(f"status:{league}:agg:{artifact}"))

    # -- in-flight -----------------------------------------------------------

    def mark_inflight(self, league: str, job_id: str, ttl_seconds: int = 3600) -> None:
        self.r.set(f"status:{league}:inflight", job_id, ex=ttl_seconds)

    def clear_inflight(self, league: str) -> None:
        self.r.delete(f"status:{league}:inflight")

    def get_inflight(self, league: str) -> str | None:
        v = self.r.get(f"status:{league}:inflight")
        return v.decode() if v else None


def _decode(h: dict) -> dict:
    return {k.decode(): v.decode() for k, v in h.items()}
