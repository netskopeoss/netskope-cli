"""AICC identity inventory commands (``ntsk aicc identities``)."""

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

identities_app = typer.Typer(
    name="identities",
    help=(
        "Identity inventory — who (and what) is driving AI usage.\n\n"
        "Identities are either 'user' (attributed to a known person) or 'unknown' "
        "(unattributed traffic: unmanaged devices, source IPs, headless scripts). "
        "Each identity row shows the apps, models, agents, and MCP servers it touched "
        "plus traffic volumes. Identity IDs are the 'user_id' field — an email for "
        "users, an IP/hostname for unknown sources. Use 'list --type unknown' to find "
        "your visibility blind spots."
    ),
    no_args_is_help=True,
)


class _SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class _IdentityType(str, Enum):
    user = "user"
    unknown = "unknown"


class _TrendKind(str, Enum):
    traffic = "traffic"
    risk = "risk"


class _SubSort(str, Enum):
    name_ = "name"
    bytes_ = "bytes"


def _identity_path(identity_id: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/identities/{urllib.parse.quote(identity_id, safe='')}{suffix}"


def _sub_resource(
    ctx: typer.Context,
    identity_id: str,
    resource: str,
    *,
    start: Optional[str],
    end: Optional[str],
    search: Optional[str],
    sort_by: _SubSort,
    sort_dir: _SortDir,
    limit: int,
    offset: int,
    fetch_all: bool,
    title: str,
) -> None:
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
        _identity_path(identity_id, f"/{resource}"),
        params,
        title=title,
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
    )


@identities_app.command("list")
def list_identities(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    identity_type: Optional[_IdentityType] = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Identity class: 'user' (known, attributed people) or 'unknown' (unattributed "
            "sources — unmanaged devices, bare IPs). Omit for both."
        ),
    ),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    user_group: Optional[list[str]] = typer.Option(
        None, "--user-group", help="Filter by directory user group (repeatable), e.g. 'Engineering'."
    ),
    ou: Optional[list[str]] = typer.Option(
        None, "--ou", help="Filter by organizational unit (repeatable), e.g. 'R&D'."
    ),
    activity_level: Optional[list[str]] = typer.Option(
        None, "--activity-level", help="Filter by activity level (repeatable)."
    ),
    risk_level: Optional[list[str]] = typer.Option(
        None, "--risk-level", help="Filter by risk level (repeatable), e.g. Low, Medium, High, Critical, Unknown."
    ),
    first_seen_after: Optional[str] = typer.Option(None, "--first-seen-after", help=HELP_FIRST_SEEN_AFTER),
    active_only: bool = typer.Option(False, "--active-only", help=HELP_ACTIVE_ONLY),
    sort_by: Optional[str] = typer.Option(
        None,
        "--sort-by",
        help="Server-side sort field. Valid: bytes, sessions, transactions, apps, risk_level.",
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List identities with their AI usage footprint.

    Queries GET /api/v2/aicc/inventory/identities. Each row includes user_id,
    type (user/unknown), user_groups, ou, apps, models, agents, mcp_servers
    counts, uploaded_bytes, downloaded_bytes, sessions, transactions,
    first_seen, and last_seen.

    Examples:
        ntsk aicc identities list
        ntsk aicc identities list --type user --sort-by bytes --limit 10
        ntsk aicc identities list --type unknown --all -o json     # visibility blind spots
        ntsk aicc identities list --user-group Engineering --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(
        params,
        type=identity_type.value if identity_type else None,
        search=search,
        user_group=user_group,
        ou=ou,
        activity_level=activity_level,
        risk_level=risk_level,
        active_only=active_only,
        sort=build_sort(sort_by, sort_dir.value),
    )
    if first_seen_after:
        params["first_seen_after"] = resolve_single_time(ctx, first_seen_after)

    run_list(
        ctx,
        f"{AICC_BASE}/inventory/identities",
        params,
        title="AICC — Identities",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=[
            "user_id",
            "type",
            "ou",
            "apps",
            "models",
            "agents",
            "mcp_servers",
            "uploaded_bytes",
            "downloaded_bytes",
            "sessions",
        ],
        empty_hint="No identities found in this window. Try a longer --start (e.g. 30d, 90d).",
    )


@identities_app.command("get")
def get_identity(
    ctx: typer.Context,
    identity_id: str = typer.Argument(
        ...,
        help=(
            "Identity ID — the 'user_id' field from 'aicc identities list'. An email "
            "address for users (alice@example.com) or an IP/hostname for unknown sources "
            "(10.0.201.192)."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show full details for one identity.

    Queries GET /api/v2/aicc/inventory/identities/{identity_id}. Returns
    metadata (type, user_groups, ou, last device/hostname/IP), a
    usage_summary, and the associated apps, MCP servers, agents, and models
    with per-entity usage.

    Examples:
        ntsk aicc identities get alice@example.com
        ntsk aicc identities get 10.0.201.192 --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _identity_path(identity_id),
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {identity_id}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC Identity — {identity_id}")


@identities_app.command("trend")
def identity_trend(
    ctx: typer.Context,
    identity_id: str = typer.Argument(..., help="Identity ID (email or IP) from 'aicc identities list'."),
    kind: _TrendKind = typer.Option(
        _TrendKind.traffic,
        "--kind",
        "-k",
        help="Trend to fetch: 'traffic' (bytes/sessions per bucket) or 'risk' (risk score over time).",
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show a time-bucketed trend for one identity.

    Queries GET /api/v2/aicc/inventory/identities/{identity_id}/
    {traffic-trend|risk-trend}.

    Examples:
        ntsk aicc identities trend alice@example.com
        ntsk aicc identities trend alice@example.com --kind risk --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    if kind is not _TrendKind.risk:
        params["timezone"] = tz
    response = aicc_get(
        ctx,
        _identity_path(identity_id, f"/{kind.value}-trend"),
        params,
        spinner_text=f"Fetching {kind.value} trend for {identity_id}...",
    )
    payload = unwrap_data(response)
    rows = payload.get("data") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        rows if isinstance(rows, list) else payload,
        title=f"AICC Identity {kind.value.title()} Trend — {identity_id}",
        empty_hint="No trend data in this window.",
    )


@identities_app.command("models")
def identity_models(
    ctx: typer.Context,
    identity_id: str = typer.Argument(..., help="Identity ID (email or IP) from 'aicc identities list'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _SubSort = typer.Option(_SubSort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the AI models an identity has accessed.

    Queries GET /api/v2/aicc/inventory/identities/{identity_id}/models.

    Examples:
        ntsk aicc identities models alice@example.com
    """
    _sub_resource(
        ctx,
        identity_id,
        "models",
        start=start,
        end=end,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        title=f"AICC Identity Models — {identity_id}",
    )


@identities_app.command("agents")
def identity_agents(
    ctx: typer.Context,
    identity_id: str = typer.Argument(..., help="Identity ID (email or IP) from 'aicc identities list'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _SubSort = typer.Option(_SubSort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the native AI agents an identity has used.

    Queries GET /api/v2/aicc/inventory/identities/{identity_id}/agents.

    Examples:
        ntsk aicc identities agents alice@example.com
    """
    _sub_resource(
        ctx,
        identity_id,
        "agents",
        start=start,
        end=end,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        title=f"AICC Identity Agents — {identity_id}",
    )


@identities_app.command("mcp")
def identity_mcp(
    ctx: typer.Context,
    identity_id: str = typer.Argument(..., help="Identity ID (email or IP) from 'aicc identities list'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _SubSort = typer.Option(_SubSort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the MCP servers an identity has connected to.

    Queries GET /api/v2/aicc/inventory/identities/{identity_id}/mcp-servers.

    Examples:
        ntsk aicc identities mcp alice@example.com
    """
    _sub_resource(
        ctx,
        identity_id,
        "mcp-servers",
        start=start,
        end=end,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        title=f"AICC Identity MCP Servers — {identity_id}",
    )
