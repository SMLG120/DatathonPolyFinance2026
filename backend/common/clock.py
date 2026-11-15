"""Time helpers.

The clock is injected everywhere so tests never sleep and never depend on the
wall clock. Timestamps on the wire are UTC ISO-8601 with millisecond precision
and a ``Z`` suffix, for example ``2026-11-14T15:04:05.123Z``.
"""

from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone


class SystemClock:
    """Real time. ``time()`` is epoch seconds as a float."""

    def time(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


def to_iso(epoch_seconds: float) -> str:
    millis = int(round(epoch_seconds * 1000))
    whole = datetime.fromtimestamp(millis // 1000, tz=timezone.utc)
    return f"{whole.strftime('%Y-%m-%dT%H:%M:%S')}.{millis % 1000:03d}Z"


def from_iso(value: str) -> float:
    """Inverse of :func:`to_iso`. Raises ``ValueError`` on any other format."""
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return calendar.timegm(parsed.timetuple()) + parsed.microsecond / 1_000_000
