"""AICC MCP server inventory commands (``ntsk aicc mcp``)."""

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
    HELP_LIMIT,
    HELP_OFFSET,
    HELP_SEARCH,
    HELP_START,
    HELP_TIMEZONE,
    add_filters,
    aicc_get,
    build_sort,
    resolve_time_range,
    run_list,
    show_payload,
    unwrap_data,
)

mcp_app = typer.Typer(
    name="mcp",
    help=(
        "MCP server inventory — Model Context Protocol servers your AI agents connect to.\n\n"
        "MCP servers give agents live access to real systems (databases, code, SaaS tools), "
        "so their enterprise-readiness matters. Each server carries a category, CCI score "
        "(cci_score), Cloud Confidence Level (ccl), user counts, and event/session volumes. "
        "Start with 'list', then drill in with 'get', 'identities', 'trend', 'violations'."
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


class _TrendKind(str, Enum):
    traffic = "traffic"
    identity = "identity"
    risk = "risk"


class _ViolationStatus(str, Enum):
    current = "current"
    dismissed = "dismissed"


def _mcp_path(server_name: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/mcp-servers/{urllib.parse.quote(server_name, safe='')}{suffix}"


@mcp_app.command("list")
def list_mcp(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    category: Optional[list[str]] = typer.Option(
        None,
        "--category",
        help=(
            "Filter by MCP server category (repeatable). Discover valid values with "
            "'ntsk aicc analytics breakdown mcp --dimension category'. Examples: "
            "'Observability and Monitoring', 'Knowledge and Memory'."
        ),
    ),
    ccl: Optional[list[str]] = typer.Option(
        None, "--ccl", help="Filter by Cloud Confidence Level (repeatable): Poor, Low, Medium, High, Excellent."
    ),
    risk_level: Optional[list[str]] = typer.Option(
        None, "--risk-level", help="Filter by risk level (repeatable), e.g. Low, Medium, High, Critical, Unknown."
    ),
    active_only: bool = typer.Option(False, "--active-only", help=HELP_ACTIVE_ONLY),
    sort_by: Optional[str] = typer.Option(
        None,
        "--sort-by",
        help="Server-side sort field. Valid: sessions, transactions, identities, cci_score, risk_level.",
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List discovered MCP servers with usage and risk data.

    Queries GET /api/v2/aicc/inventory/mcp-servers. Each row includes name,
    category, ccl, cci_score, users, events, sessions, footprint (where it
    runs), first_seen, and last_seen.

    Examples:
        ntsk aicc mcp list
        ntsk aicc mcp list --start 30d --sort-by sessions --limit 10
        ntsk aicc mcp list --ccl Poor --ccl Low --all -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(
        params,
        search=search,
        category=category,
        ccl=ccl,
        risk_level=risk_level,
        active_only=active_only,
        sort=build_sort(sort_by, sort_dir.value),
    )
    run_list(
        ctx,
        f"{AICC_BASE}/inventory/mcp-servers",
        params,
        title="AICC — MCP Servers",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=["name", "category", "cci_score", "ccl", "users", "events", "sessions", "first_seen"],
        empty_hint="No MCP servers found in this window. Try a longer --start (e.g. 30d, 90d).",
    )


@mcp_app.command("get")
def get_mcp(
    ctx: typer.Context,
    server_name: str = typer.Argument(
        ...,
        help=(
            "Exact MCP server name as returned by 'aicc mcp list' (the 'name' field), "
            "e.g. 'Globalping MCP'. Quote names containing spaces."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show full details for one MCP server.

    Queries GET /api/v2/aicc/inventory/mcp-servers/{server_name}. Returns
    metadata (category, ccl, cci_score, footprint), a usage summary, and
    top associated identities.

    Examples:
        ntsk aicc mcp get "Globalping MCP"
        ntsk aicc mcp get "DeepWiki MCP" --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _mcp_path(server_name),
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {server_name}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC MCP Server — {server_name}")


@mcp_app.command("identities")
def mcp_identities(
    ctx: typer.Context,
    server_name: str = typer.Argument(..., help="Exact MCP server name, e.g. 'Globalping MCP'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _IdentitySort = typer.Option(
        _IdentitySort.sessions, "--sort-by", help="Sort field: name, events, sessions."
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the identities connecting to an MCP server.

    Queries GET /api/v2/aicc/inventory/mcp-servers/{server_name}/identities.

    Examples:
        ntsk aicc mcp identities "Globalping MCP"
        ntsk aicc mcp identities goskope --sort-by events --all -o json
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
        _mcp_path(server_name, "/identities"),
        params,
        title=f"AICC MCP Identities — {server_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=["name", "type", "sessions", "events", "uploaded_bytes", "downloaded_bytes"],
    )


@mcp_app.command("deployments")
def mcp_deployments(
    ctx: typer.Context,
    server_name: str = typer.Argument(..., help="Exact MCP server name, e.g. 'Globalping MCP'."),
    deployment_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=(
            "Deployment class to list — a footprint key from 'aicc mcp get' "
            "(footprint.types), e.g. endpoint, cloud_web. An unknown type returns an empty list."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List deployment instances of an MCP server (per footprint type).

    Queries GET /api/v2/aicc/inventory/mcp-servers/{server_name}/deployments.
    First run 'aicc mcp get NAME' and check footprint.types for valid --type values.

    Examples:
        ntsk aicc mcp deployments "Globalping MCP" --type endpoint
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "type": deployment_type}
    run_list(
        ctx,
        _mcp_path(server_name, "/deployments"),
        params,
        title=f"AICC MCP Deployments — {server_name} ({deployment_type})",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        empty_hint=(
            "No deployments of this type. Run 'ntsk aicc mcp get' and use one of the footprint.types values as --type."
        ),
    )


@mcp_app.command("trend")
def mcp_trend(
    ctx: typer.Context,
    server_name: str = typer.Argument(..., help="Exact MCP server name, e.g. 'Globalping MCP'."),
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
    """Show a time-bucketed trend for one MCP server.

    Queries GET /api/v2/aicc/inventory/mcp-servers/{server_name}/
    {traffic-trend|identity-trend|risk-trend}.

    Examples:
        ntsk aicc mcp trend "Globalping MCP"
        ntsk aicc mcp trend goskope --kind identity --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    if kind is not _TrendKind.risk:
        params["timezone"] = tz
    response = aicc_get(
        ctx,
        _mcp_path(server_name, f"/{kind.value}-trend"),
        params,
        spinner_text=f"Fetching {kind.value} trend for {server_name}...",
    )
    payload = unwrap_data(response)
    rows = payload.get("data") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        rows if isinstance(rows, list) else payload,
        title=f"AICC MCP {kind.value.title()} Trend — {server_name}",
        empty_hint="No trend data in this window.",
    )


@mcp_app.command("violations")
def mcp_violations(
    ctx: typer.Context,
    server_name: str = typer.Argument(..., help="Exact MCP server name, e.g. 'Globalping MCP'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    status: _ViolationStatus = typer.Option(
        _ViolationStatus.current, "--status", help="Which violations to list: current (default) or dismissed."
    ),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List policy violations triggered by an MCP server's traffic.

    Queries GET /api/v2/aicc/inventory/mcp-servers/{server_name}/violations.
    Rows include policy_name, severity, category, and count.

    Examples:
        ntsk aicc mcp violations "Globalping MCP" --start 30d
        ntsk aicc mcp violations goskope --status dismissed
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "status": status.value}
    run_list(
        ctx,
        _mcp_path(server_name, "/violations"),
        params,
        title=f"AICC MCP Violations — {server_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=["policy_name", "severity", "category", "count"],
        empty_hint="No policy violations for this MCP server in the window.",
    )
