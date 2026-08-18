"""AICC AI application inventory commands (``ntsk aicc apps``)."""

from __future__ import annotations

import urllib.parse
from enum import Enum
from typing import Optional

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_ACTIVE_ONLY,
    HELP_ALL,
    HELP_END,
    HELP_FIELDS,
    HELP_FIRST_SEEN_AFTER,
    HELP_LIMIT,
    HELP_OFFSET,
    HELP_SEARCH,
    HELP_START,
    HELP_TIMEZONE,
    add_filters,
    aicc_get,
    build_sort,
    resolve_single_time,
    resolve_time_range,
    run_list,
    show_payload,
    unwrap_data,
)

apps_app = typer.Typer(
    name="apps",
    help=(
        "AI application inventory — every generative-AI app discovered in your traffic.\n\n"
        "Each application carries a Cloud Confidence Index score (cci_score, 0-100), a "
        "Cloud Confidence Level (ccl: Poor/Low/Medium/High/Excellent), a sanctioning "
        "status (Sanctioned/Unsanctioned), usage volumes (bytes, sessions, transactions), "
        "and the number of identities using it. Start with 'list', then drill into a "
        "specific app with 'get', 'identities', 'trend', and 'violations'."
    ),
    no_args_is_help=True,
)


class _SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class _IdentitySort(str, Enum):
    name_ = "name"
    events = "events"
    sessions = "sessions"
    uploaded_bytes = "uploaded_bytes"
    downloaded_bytes = "downloaded_bytes"


class _TrendKind(str, Enum):
    traffic = "traffic"
    identity = "identity"
    risk = "risk"


def _app_path(app_name: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/ai-applications/{urllib.parse.quote(app_name, safe='')}{suffix}"


@apps_app.command("list")
def list_apps(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    category: Optional[list[str]] = typer.Option(
        None,
        "--category",
        help=(
            "Filter by app category (repeatable). Discover valid values with "
            "'ntsk aicc analytics breakdown apps --dimension category'. "
            "Examples: Conversation, Code, Writing."
        ),
    ),
    status: Optional[list[str]] = typer.Option(
        None, "--status", help="Filter by sanctioning status (repeatable): Sanctioned or Unsanctioned."
    ),
    ccl: Optional[list[str]] = typer.Option(
        None,
        "--ccl",
        help="Filter by Cloud Confidence Level (repeatable): Poor, Low, Medium, High, Excellent.",
    ),
    risk_level: Optional[list[str]] = typer.Option(
        None, "--risk-level", help="Filter by risk level (repeatable), e.g. Low, Medium, High, Critical, Unknown."
    ),
    first_seen_after: Optional[str] = typer.Option(None, "--first-seen-after", help=HELP_FIRST_SEEN_AFTER),
    active_only: bool = typer.Option(False, "--active-only", help=HELP_ACTIVE_ONLY),
    sort_by: Optional[str] = typer.Option(
        None,
        "--sort-by",
        help=(
            "Server-side sort field. Valid: bytes, sessions, transactions, identities, "
            "cci_score, risk_level. Sent as the API's JSON sort parameter."
        ),
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """List discovered AI applications with usage and risk data.

    Queries GET /api/v2/aicc/inventory/ai-applications. Each row includes
    name, category, status (Sanctioned/Unsanctioned), cci_score, ccl,
    identities/known_users/unknown_users, uploaded_bytes, downloaded_bytes,
    sessions, transactions, footprint, first_seen, and last_seen.

    Examples:
        ntsk aicc apps list
        ntsk aicc apps list --start 30d --sort-by bytes --limit 10
        ntsk aicc apps list --status Unsanctioned --ccl Poor --ccl Low
        ntsk aicc apps list --start 2026-06-01 --end 2026-06-30 --all -o json
        ntsk aicc apps list --search claude --fields name,status,ccl,identities
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(
        params,
        search=search,
        category=category,
        status=status,
        ccl=ccl,
        risk_level=risk_level,
        active_only=active_only,
        sort=build_sort(sort_by, sort_dir.value),
    )
    if first_seen_after:
        params["first_seen_after"] = resolve_single_time(ctx, first_seen_after)

    run_list(
        ctx,
        f"{AICC_BASE}/inventory/ai-applications",
        params,
        title="AICC — AI Applications",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        fields=fields,
        default_fields=[
            "name",
            "category",
            "status",
            "cci_score",
            "ccl",
            "identities",
            "uploaded_bytes",
            "downloaded_bytes",
            "sessions",
            "first_seen",
        ],
        empty_hint="No AI applications found in this window. Try a longer --start (e.g. 30d 90d) or drop filters.",
    )


@apps_app.command("get")
def get_app(
    ctx: typer.Context,
    app_name: str = typer.Argument(
        ...,
        help=(
            "Exact application name as returned by 'aicc apps list' (the 'name' field), "
            "e.g. 'Anthropic Claude' or 'ChatGPT'. Quote names containing spaces."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """Show full details for one AI application.

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}. Returns
    metadata (category, status, ccl, cci_score, domains, footprint,
    first/last seen), a usage_summary (bytes, sessions, identities,
    transactions), and the top associated_identities.

    Examples:
        ntsk aicc apps get "Anthropic Claude"
        ntsk aicc apps get ChatGPT --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _app_path(app_name),
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {app_name}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC App — {app_name}", fields=fields)


@apps_app.command("status")
def app_status(
    ctx: typer.Context,
    app_name: str = typer.Argument(..., help="Exact application name, e.g. 'Anthropic Claude'."),
) -> None:
    """Show the CASB sanctioning status and CCI score for an application.

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}/status.
    A lightweight check that returns name, status, cci_score, and ccl.

    Examples:
        ntsk aicc apps status ChatGPT
    """
    response = aicc_get(ctx, _app_path(app_name, "/status"), spinner_text=f"Fetching status for {app_name}...")
    show_payload(ctx, unwrap_data(response), title=f"AICC App Status — {app_name}")


@apps_app.command("identities")
def app_identities(
    ctx: typer.Context,
    app_name: str = typer.Argument(..., help="Exact application name, e.g. 'Anthropic Claude'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _IdentitySort = typer.Option(
        _IdentitySort.events,
        "--sort-by",
        help="Sort field: name, events, sessions, uploaded_bytes, downloaded_bytes.",
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """List the identities (users and unknown sources) using an application.

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}/identities.
    Rows include name, type (user/unknown), uploaded_bytes, downloaded_bytes,
    sessions, and events.

    Examples:
        ntsk aicc apps identities "Anthropic Claude"
        ntsk aicc apps identities ChatGPT --sort-by uploaded_bytes --limit 10
        ntsk aicc apps identities ChatGPT --all -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {
        "start_time": start_iso,
        "end_time": end_iso,
        "sort_by": sort_by.value,
        "sort_dir": sort_dir.value,
    }
    add_filters(params, search=search)
    run_list(
        ctx,
        _app_path(app_name, "/identities"),
        params,
        title=f"AICC App Identities — {app_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        fields=fields,
        default_fields=["name", "type", "uploaded_bytes", "downloaded_bytes", "sessions", "events"],
    )


@apps_app.command("deployments")
def app_deployments(
    ctx: typer.Context,
    app_name: str = typer.Argument(..., help="Exact application name, e.g. 'Anthropic Claude'."),
    deployment_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=(
            "Deployment class to list — a footprint key from 'aicc apps get' "
            "(footprint.types), e.g. cloud_web, endpoint, vm, kubernetes. "
            "An unknown type returns an empty list."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """List deployment instances of an application (per footprint type).

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}/deployments.
    First run 'aicc apps get NAME' and check footprint.types for the valid
    --type values for this app.

    Examples:
        ntsk aicc apps deployments "Anthropic Claude" --type cloud_web
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "type": deployment_type}
    run_list(
        ctx,
        _app_path(app_name, "/deployments"),
        params,
        title=f"AICC App Deployments — {app_name} ({deployment_type})",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        fields=fields,
        empty_hint=(
            "No deployments of this type. Run 'ntsk aicc apps get' and use one of the "
            "footprint.types values as --type."
        ),
    )


@apps_app.command("trend")
def app_trend(
    ctx: typer.Context,
    app_name: str = typer.Argument(..., help="Exact application name, e.g. 'Anthropic Claude'."),
    kind: _TrendKind = typer.Option(
        _TrendKind.traffic,
        "--kind",
        "-k",
        help=(
            "Trend to fetch: 'traffic' (bytes/sessions/events per bucket), "
            "'identity' (identity counts per bucket), or 'risk' (risk score over time)."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show a time-bucketed trend for one application.

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}/
    {traffic-trend|identity-trend|risk-trend}. The response includes the
    bucket resolution (e.g. 1d) and one row per bucket.

    Examples:
        ntsk aicc apps trend "Anthropic Claude"
        ntsk aicc apps trend ChatGPT --kind identity --start 30d
        ntsk aicc apps trend ChatGPT --kind risk -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    if kind is not _TrendKind.risk:
        params["timezone"] = tz
    response = aicc_get(
        ctx,
        _app_path(app_name, f"/{kind.value}-trend"),
        params,
        spinner_text=f"Fetching {kind.value} trend for {app_name}...",
    )
    payload = unwrap_data(response)
    # Trends nest buckets under "data" — surface them as rows when present.
    rows = payload.get("data") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        rows if isinstance(rows, list) else payload,
        title=f"AICC App {kind.value.title()} Trend — {app_name}",
        empty_hint="No trend data in this window.",
    )


@apps_app.command("violations")
def app_violations(
    ctx: typer.Context,
    app_name: str = typer.Argument(..., help="Exact application name, e.g. 'Anthropic Claude'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """List policy violations triggered by an application's traffic.

    Queries GET /api/v2/aicc/inventory/ai-applications/{app_name}/violations.
    Rows include policy_name, severity, category (e.g. DLP), and count.

    Examples:
        ntsk aicc apps violations "Anthropic Claude" --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    run_list(
        ctx,
        _app_path(app_name, "/violations"),
        params,
        title=f"AICC App Violations — {app_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        fields=fields,
        default_fields=["policy_name", "severity", "category", "count"],
        empty_hint="No policy violations for this app in the window.",
    )
