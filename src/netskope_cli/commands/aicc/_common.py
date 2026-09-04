"""Shared helpers for the AICC (AI Command Center) command group.

All AICC endpoints live under ``/api/v2/aicc`` and share a common set of
conventions that differ from older Netskope APIs:

- Time-range parameters (``start_time`` / ``end_time``) are ISO 8601 / RFC
  3339 strings in UTC (e.g. ``2026-02-04T00:00:00Z``) — NOT epoch integers.
- Responses use a ``{"success": true, "metadata": {...}, "data": {...}}``
  envelope.  Paginated list endpoints nest rows under ``data.items`` (or
  ``data.violations`` for data-protection) alongside ``total`` / ``offset``
  / ``limit``.
- Inventory list endpoints take a JSON-encoded ``sort`` parameter, e.g.
  ``{"field": "bytes", "order": "desc"}``.

The helpers here centralise those conventions so every ``aicc`` subcommand
behaves identically: same time flags, same pagination flags, same output
handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import AuthorizationError, NotFoundError
from netskope_cli.core.output import OutputFormatter, echo_error, spinner
from netskope_cli.core.output import build_formatter as _core_build_formatter
from netskope_cli.utils.helpers import validate_time_range

AICC_BASE = "/api/v2/aicc"

# Page size used when --all is requested.  The API accepts larger limits but
# 100 keeps individual responses fast and memory bounded.
ALL_PAGE_SIZE = 100

LICENSE_HINT = (
    "The AI Command Center inventory endpoints returned 404. This usually means "
    "the AICC / AI Security Discovery feature is not enabled on this tenant, or "
    "your API token lacks the 'ai_security_discovery' scope. Check Settings > "
    "Tools > REST API v2 for the token's scopes."
)

# ---------------------------------------------------------------------------
# Reusable help strings (kept identical across every aicc subcommand so the
# CLI reads consistently and agents can rely on uniform flag semantics).
# ---------------------------------------------------------------------------
HELP_START = (
    "Start of the reporting window. Accepts a relative offset ('24h', '7d', '30d', '4w'), "
    "an ISO 8601 date/datetime ('2026-06-01', '2026-06-01T00:00:00Z'), or a Unix epoch. "
    "Converted to the ISO 8601 UTC format the AICC API requires. Default: 7d (last 7 days)."
)
HELP_END = (
    "End of the reporting window. Same formats as --start. Default: now. "
    "Combine with --start for a fixed historical window, e.g. --start 2026-06-01 --end 2026-06-30."
)
HELP_LIMIT = "Maximum number of rows to return in this page. The API default is 10; the CLI default is 50."
HELP_OFFSET = "Number of rows to skip (pagination). Use with --limit to page through results."
HELP_ALL = (
    "Fetch every page and return the complete result set (ignores --limit/--offset). "
    "Use for full exports and report generation."
)
HELP_SEARCH = "Free-text search filter applied server-side to names."
HELP_FIELDS = (
    "Comma-separated list of fields to include in the output (client-side projection — "
    "any response field is valid, unlike the events API where --fields is server-side). "
    "Example: --fields name,ccl,identities"
)
HELP_TIMEZONE = (
    "IANA timezone used by the API to align trend buckets to local days (e.g. America/Los_Angeles). " "Default: UTC."
)
HELP_ACTIVE_ONLY = "Only include entities with activity inside the time window (excludes dormant entities)."
HELP_FIRST_SEEN_AFTER = (
    "Only include entities first discovered after this time (same formats as --start). "
    "Useful for 'what is new since last review?' queries."
)


# ---------------------------------------------------------------------------
# Context helpers (same shape as every other command module)
# ---------------------------------------------------------------------------
def get_console(ctx: typer.Context) -> Console:
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def get_no_color(ctx: typer.Context) -> bool:
    state = ctx.obj
    return bool(state.no_color) if state is not None else False


def build_aicc_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def build_formatter(ctx: typer.Context) -> OutputFormatter:
    """Build the shared OutputFormatter for this context (delegates to core.output.build_formatter)."""
    return _core_build_formatter(ctx)


def get_output_format(ctx: typer.Context) -> str:
    state = ctx.obj
    if state is not None and getattr(state, "output", None) is not None:
        return str(state.output.value)
    return "table"


# ---------------------------------------------------------------------------
# Time handling
# ---------------------------------------------------------------------------
def to_iso_utc(unix_ts: float) -> str:
    """Render a Unix timestamp as the ISO 8601 UTC string AICC expects."""
    return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_time_range(
    ctx: typer.Context,
    start: Optional[str],
    end: Optional[str],
    *,
    default_start: str = "7d",
) -> tuple[str, str]:
    """Convert user-supplied --start/--end values into ISO 8601 UTC strings.

    Accepts relative offsets ('7d'), ISO dates, or epoch values and always
    produces the timezone-aware UTC strings the AICC API requires.
    """
    try:
        unix_start, unix_end = validate_time_range(start or default_start, end)
    except ValueError as exc:
        echo_error(str(exc), no_color=get_no_color(ctx))
        raise typer.Exit(code=2)
    return to_iso_utc(unix_start), to_iso_utc(unix_end)


def resolve_single_time(ctx: typer.Context, value: str) -> str:
    """Convert a single user-supplied time value into an ISO 8601 UTC string."""
    from netskope_cli.utils.helpers import _parse_time_value

    try:
        return to_iso_utc(_parse_time_value(value))
    except ValueError as exc:
        echo_error(str(exc), no_color=get_no_color(ctx))
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# Query-parameter helpers
# ---------------------------------------------------------------------------
def build_sort(sort_by: Optional[str], sort_dir: str) -> Optional[str]:
    """Build the JSON-encoded ``sort`` parameter for inventory list endpoints."""
    if sort_by is None:
        return None
    return json.dumps({"field": sort_by, "order": sort_dir})


def add_filters(params: dict[str, Any], **filters: Any) -> dict[str, Any]:
    """Merge non-empty filter values into *params*.

    ``None`` values and empty lists are skipped.  Boolean ``False`` is skipped
    too — AICC filter flags are opt-in.
    """
    for key, value in filters.items():
        if value is None or value is False:
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        params[key] = value
    return params


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------
def aicc_get(
    ctx: typer.Context,
    path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    spinner_text: str = "Fetching...",
    client: Optional[NetskopeClient] = None,
) -> Any:
    """Perform a GET against an AICC endpoint with a spinner and 403/404 hints."""
    own_client = client or build_aicc_client(ctx)
    no_color = get_no_color(ctx)
    try:
        with spinner(spinner_text, no_color=no_color):
            return own_client.request("GET", path, params=params or None)
    except NotFoundError:
        echo_error(LICENSE_HINT, no_color=no_color)
        raise typer.Exit(code=1)
    except AuthorizationError as exc:
        exc.suggestion = (
            "AICC endpoints require the 'AI Security Discovery' (ai_security_discovery) "
            "read scope on your REST API v2 token. Create or update the token under "
            "Settings > Tools > REST API v2 and grant the AI Command Center endpoints."
        )
        raise


def unwrap_data(response: Any) -> Any:
    """Extract the ``data`` payload from the AICC response envelope."""
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def extract_items(payload: Any) -> tuple[list[Any], dict[str, Any]]:
    """Return ``(rows, page_meta)`` from an AICC paginated payload.

    Rows live under ``items`` for most endpoints and ``violations`` for the
    data-protection violations endpoint.
    """
    if not isinstance(payload, dict):
        return (payload if isinstance(payload, list) else []), {}
    for key in ("items", "violations"):
        if isinstance(payload.get(key), list):
            meta = {k: payload[k] for k in ("total", "offset", "limit") if k in payload}
            return payload[key], meta
    return [], {}


def parse_fields(fields: Optional[str]) -> Optional[list[str]]:
    if not fields:
        return None
    parsed = [f.strip() for f in fields.split(",") if f.strip()]
    return parsed or None


def run_list(
    ctx: typer.Context,
    path: str,
    params: dict[str, Any],
    *,
    title: str,
    limit: int,
    offset: int,
    fetch_all: bool,
    fields: Optional[str] = None,
    default_fields: Optional[list[str]] = None,
    empty_hint: Optional[str] = None,
    spinner_text: Optional[str] = None,
) -> None:
    """Fetch a paginated AICC list endpoint and print it.

    Handles single-page fetches (``--limit``/``--offset``), full pagination
    (``--all``), envelope unwrapping, and the "Showing X of Y" footnote.
    """
    formatter = build_formatter(ctx)
    fmt = get_output_format(ctx)
    console = get_console(ctx)
    client = build_aicc_client(ctx)
    text = spinner_text or f"Fetching {title}..."

    rows: list[Any] = []
    total: Optional[int] = None

    if fetch_all:
        page_offset = 0
        while True:
            page_params = {**params, "offset": page_offset, "limit": ALL_PAGE_SIZE}
            response = aicc_get(ctx, path, page_params, spinner_text=text, client=client)
            items, meta = extract_items(unwrap_data(response))
            rows.extend(items)
            total = meta.get("total", total)
            if not items or len(items) < ALL_PAGE_SIZE:
                break
            if total is not None and len(rows) >= total:
                break
            page_offset += len(items)
        total = total if total is not None else len(rows)
    else:
        page_params = {**params, "offset": offset, "limit": limit}
        response = aicc_get(ctx, path, page_params, spinner_text=text, client=client)
        items, meta = extract_items(unwrap_data(response))
        rows = items
        total = meta.get("total")

    if total is not None and total > len(rows) and fmt in ("table", "human", "csv"):
        console.print(f"[dim]Showing {len(rows)} of {total} results — use --all for everything.[/dim]")

    formatter.format_output(
        rows,
        fmt=fmt,
        title=title,
        unwrap=False,
        fields=parse_fields(fields),
        default_fields=default_fields,
        empty_hint=empty_hint,
    )


def show_payload(
    ctx: typer.Context,
    payload: Any,
    *,
    title: str,
    fields: Optional[str] = None,
    default_fields: Optional[list[str]] = None,
    empty_hint: Optional[str] = None,
) -> None:
    """Print a non-paginated payload (detail objects, trends, analytics)."""
    formatter = build_formatter(ctx)
    formatter.format_output(
        payload,
        fmt=get_output_format(ctx),
        title=title,
        unwrap=False,
        fields=parse_fields(fields),
        default_fields=default_fields,
        empty_hint=empty_hint,
    )
