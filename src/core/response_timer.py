from time import perf_counter
from typing import Callable, Optional


class ResponseTimer:
    """
    Measure Mairon's active processing time for one user turn.

    The timer starts as soon as Core receives final user text and stops when
    the final answer is ready to display.

    Human approval waits can be paused so a user taking 30 seconds to decide
    whether to approve a calendar/cloud action does not make Mairon's processing
    latency look 30 seconds slower.
    """

    def __init__(
        self,
        clock: Callable[[], float] = perf_counter,
    ):
        self._clock = clock
        self._started_at = float(
            self._clock()
        )
        self._paused_at: Optional[float] = None
        self._paused_total = 0.0
        self._stopped_at: Optional[float] = None

    @property
    def is_paused(
        self,
    ) -> bool:
        return (
            self._paused_at
            is not None
            and self._stopped_at
            is None
        )

    @property
    def is_stopped(
        self,
    ) -> bool:
        return (
            self._stopped_at
            is not None
        )

    def pause(
        self,
    ) -> None:
        if (
            self.is_stopped
            or self.is_paused
        ):
            return

        self._paused_at = float(
            self._clock()
        )

    def resume(
        self,
    ) -> None:
        if (
            self.is_stopped
            or not self.is_paused
        ):
            return

        now = float(
            self._clock()
        )

        self._paused_total += max(
            0.0,
            now - float(
                self._paused_at
            ),
        )

        self._paused_at = None

    def elapsed(
        self,
    ) -> float:
        if self._stopped_at is not None:
            endpoint = self._stopped_at

        elif self._paused_at is not None:
            endpoint = self._paused_at

        else:
            endpoint = float(
                self._clock()
            )

        return max(
            0.0,
            (
                endpoint
                - self._started_at
                - self._paused_total
            ),
        )

    def stop(
        self,
    ) -> float:
        if self._stopped_at is not None:
            return self.elapsed()

        if self._paused_at is not None:
            self.resume()

        self._stopped_at = float(
            self._clock()
        )

        return self.elapsed()
