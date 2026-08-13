from abc import ABC, abstractmethod


class Throttle(ABC):
    """A rate limiter for one host.

    The interface is a single `reserve()` rather than the older throttle()/add() pair
    because the two must not be separable: a caller that waits, makes a request, and
    only then records it leaves a window where the request is in flight but uncounted,
    and drops the request entirely if it raises. reserve() claims the slot up front.
    """

    @abstractmethod
    def reserve(self) -> None:
        """Block until a request slot is free, then claim it."""

    @abstractmethod
    def status(self) -> dict:
        """Current window occupancy, for status reporting."""
