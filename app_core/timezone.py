"""Timezone helpers for deterministic rule evaluation."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

NEW_YORK_TZ = ZoneInfo("America/New_York")


def as_new_york(moment: datetime) -> datetime:
    """Return an aware datetime converted to America/New_York.

    The current product behavior is tied to America/New_York. Naive datetimes
    are rejected so callers cannot accidentally evaluate rules in the host
    process timezone.
    """

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Parking reminder rules require a timezone-aware datetime")
    return moment.astimezone(NEW_YORK_TZ)
