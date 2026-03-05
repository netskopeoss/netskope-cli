"""General-purpose utility helpers for the Netskope CLI."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone


def format_timestamp(unix_ts: int | float) -> str:
    """Convert a Unix timestamp to a human-readable UTC datetime string.

    Parameters
    ----------
    unix_ts:
        Seconds since the Unix epoch.

    Returns
    -------
    str
        Formatted as ``YYYY-MM-DD HH:MM:SS UTC``.
    """
    dt = datetime.fromtimestamp(float(unix_ts), tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def truncate_string(s: str, max_len: int = 80) -> str:
    """Truncate *s* to *max_len* characters, appending an ellipsis if needed.

    Parameters
    ----------
    s:
        The input string.
    max_len:
        Maximum allowed length (including the ellipsis character).

    Returns
    -------
    str
        The (possibly truncated) string.
    """
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"


def parse_key_value_args(args: list[str]) -> dict[str, str]:
    """Parse a list of ``key=value`` strings into a dictionary.

    Supports both ``key=value`` and ``key value`` (two-element) patterns when
    called from CLI ``--set`` style arguments.

    Parameters
    ----------
    args:
        Strings of the form ``"key=value"``.

    Returns
    -------
    dict[str, str]

    Raises
    ------
    ValueError
        If an argument cannot be parsed as ``key=value``.
    """
    result: dict[str, str] = {}
    for arg in args:
        if "=" not in arg:
            raise ValueError(f"Invalid key=value argument: {arg!r}. Expected format: key=value")
        key, _, value = arg.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Empty key in argument: {arg!r}")
        result[key] = value
    return result


# ---------------------------------------------------------------------------
# Relative-time parser
# ---------------------------------------------------------------------------

_RELATIVE_TIME_RE = re.compile(r"^(\d+)\s*([smhdw])$", re.IGNORECASE)

_UNIT_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def _parse_relative_time(value: str) -> float:
    """Return a Unix timestamp for a relative offset like ``'1h'`` or ``'7d'``.

    The offset is subtracted from the current time.
    """
    match = _RELATIVE_TIME_RE.match(value.strip())
    if not match:
        raise ValueError(
            f"Invalid relative time {value!r}. "
            "Expected a number followed by a unit: s (seconds), m (minutes), h (hours), d (days), w (weeks). "
            "Examples: 1h, 24h, 7d, 30m"
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    return time.time() - amount * _UNIT_SECONDS[unit]


def _parse_time_value(value: str | int | float) -> float:
    """Interpret *value* as either a Unix timestamp or a relative time string."""
    # Already numeric
    if isinstance(value, (int, float)):
        return float(value)

    value_str = str(value).strip()

    # Pure numeric string
    try:
        return float(value_str)
    except ValueError:
        pass

    # Relative time (e.g. "1h", "7d")
    try:
        return _parse_relative_time(value_str)
    except ValueError:
        pass

    # ISO 8601 date/datetime (e.g. "2026-03-01", "2026-03-01T00:00:00Z")
    try:
        dt = datetime.fromisoformat(value_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(int(dt.timestamp()))
    except ValueError:
        pass

    raise ValueError(
        f"Cannot parse time value {value_str!r}. "
        "Expected a Unix timestamp, a relative offset (e.g. '24h', '7d'), "
        "or an ISO 8601 date (e.g. '2026-03-01', '2026-03-01T00:00:00Z')."
    )


def validate_time_range(
    start: str | int | float,
    end: str | int | float | None = None,
) -> tuple[int, int]:
    """Validate and convert a time range to Unix timestamps.

    Parameters
    ----------
    start:
        Start of the range.  Accepts a Unix timestamp (int/float/str) or a
        relative offset such as ``"1h"``, ``"24h"``, ``"7d"``.
    end:
        End of the range.  Same formats as *start*.  Defaults to *now* when
        ``None``.

    Returns
    -------
    tuple[int, int]
        ``(unix_start, unix_end)`` as integers (seconds).

    Raises
    ------
    ValueError
        If the start time is after the end time or the values cannot be parsed.
    """
    unix_start = _parse_time_value(start)
    unix_end = _parse_time_value(end) if end is not None else time.time()

    if unix_start > unix_end:
        raise ValueError(
            f"Start time ({unix_start:.0f}) is after end time ({unix_end:.0f}). "
            "Ensure the start time is before the end time."
        )

    return int(unix_start), int(unix_end)
