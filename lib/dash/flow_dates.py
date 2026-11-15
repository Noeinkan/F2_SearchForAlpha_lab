"""European presentation of Flow dates; stored dates remain ISO 8601."""

from __future__ import annotations

from datetime import date, datetime


def display_date(value: str, *, time: bool = False) -> str:
    try:
        if time:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            utc = stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0
            return stamp.strftime("%d/%m/%Y %H:%M") + (" UTC" if utc else "")
        return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "Date unavailable"
