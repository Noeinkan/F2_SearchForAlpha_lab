"""European presentation of Flow dates; stored dates remain ISO 8601."""

from __future__ import annotations

from datetime import date, datetime
import re


def display_date(value: str, *, time: bool = False) -> str:
    try:
        if time:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            utc = stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0
            return stamp.strftime("%d/%m/%Y %H:%M") + (" UTC" if utc else "")
        return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "Date unavailable"


_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}:\d{2}:\d{2}))?")
_HTML_TEXT = re.compile(r">([^<>]+)<")


def localize_html_text(html_source: str) -> str:
    """Convert dates in an already saved static Flow report without touching attributes."""
    def text_node(match: re.Match[str]) -> str:
        def date_part(value: re.Match[str]) -> str:
            day = f"{value[3]}/{value[2]}/{value[1]}"
            return f"{day} {value[4]}" if value[4] else day
        return ">" + _ISO_DATE.sub(date_part, match[1]) + "<"
    return _HTML_TEXT.sub(text_node, html_source)
