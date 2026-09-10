"""AICC native AI agent inventory commands (``ntsk aicc agents``)."""

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

agents_app = typer.Typer(
    name="agents",
    help=(
        "AI agent inventory — native agent applications installed on endpoints.\n\n"
        "Agents are desktop/endpoint AI assistants and autonomous tools (e.g. 'Claude "
        "(Anthropic)', 'Microsoft Copilot') discovered on managed devices. Each row "
        "includes category, framework, footprint (installation counts), and the number "
        "of identities using it."
    ),
    no_args_is_help=True,
)


class _SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class _IdentitySort(str, Enum):
    name_ = "name"
    bytes_ = "bytes"


def _agent_path(agent_name: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/agents/{urllib.parse.quote(agent_name, safe='')}{suffix}"


@agents_app.command("list")
def list_agents(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    category: Optional[list[str]] = typer.Option(
        None,
        "--category",
        help=(
            "Filter by agent category (repeatable), e.g. 'Generative AI Assistant'. Discover "
            "values with 'ntsk aicc analytics breakdown agents --dimension category'."
        ),
    ),
    framework: Optional[list[str]] = typer.Option(
        None, "--framework", help="Filter by agent framework (repeatable), e.g. LangChain, Unknown."
    ),
    first_seen_after: Optional[str] = typer.Option(None, "--first-seen-after", help=HELP_FIRST_SEEN_AFTER),
    active_only: bool = typer.Option(False, "--active-only", help=HELP_ACTIVE_ONLY),
    sort_by: Optional[str] = typer.Option(
        None, "--sort-by", help="Server-side sort field. Valid: bytes, sessions, identities."
    ),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List discovered native AI agents.

    Queries GET /api/v2/aicc/inventory/agents. Each row includes name,
    category, framework, footprint (endpoint installations), identities,
    first_seen, and last_seen.

    Examples:
        ntsk aicc agents list
        ntsk aicc agents list --sort-by identities --limit 10
        ntsk aicc agents list --start 30d --all -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(
        params,
        search=search,
        category=category,
        framework=framework,
        active_only=active_only,
        sort=build_sort(sort_by, sort_dir.value),
    )
    if first_seen_after:
        params["first_seen_after"] = resolve_single_time(ctx, first_seen_after)

    run_list(
        ctx,
        f"{AICC_BASE}/inventory/agents",
        params,
        title="AICC — Agents",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=["name", "category", "framework", "identities", "first_seen", "last_seen"],
        empty_hint="No agents found in this window. Try a longer --start (e.g. 30d, 90d).",
    )


@agents_app.command("get")
def get_agent(
    ctx: typer.Context,
    agent_name: str = typer.Argument(
        ...,
        help=(
            "Exact agent name as returned by 'aicc agents list' (the 'name' field), "
            "e.g. 'Claude (Anthropic)'. Quote names containing spaces or parentheses."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show full details for one agent.

    Queries GET /api/v2/aicc/inventory/agents/{agent_name}.

    Examples:
        ntsk aicc agents get "Claude (Anthropic)"
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _agent_path(agent_name),
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {agent_name}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC Agent — {agent_name}")


@agents_app.command("identities")
def agent_identities(
    ctx: typer.Context,
    agent_name: str = typer.Argument(..., help="Exact agent name, e.g. 'Claude (Anthropic)'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _IdentitySort = typer.Option(_IdentitySort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the identities using an agent.

    Queries GET /api/v2/aicc/inventory/agents/{agent_name}/identities.

    Examples:
        ntsk aicc agents identities "Claude (Anthropic)"
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
        _agent_path(agent_name, "/identities"),
        params,
        title=f"AICC Agent Identities — {agent_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
    )


@agents_app.command("deployments")
def agent_deployments(
    ctx: typer.Context,
    agent_name: str = typer.Argument(..., help="Exact agent name, e.g. 'Claude (Anthropic)'."),
    deployment_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=(
            "Deployment class to list — a footprint key from 'aicc agents get' "
            "(footprint.types), e.g. endpoint. An unknown type returns an empty list."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List deployment instances of an agent (per footprint type).

    Queries GET /api/v2/aicc/inventory/agents/{agent_name}/deployments.
    First run 'aicc agents get NAME' and check footprint.types for valid
    --type values (usually 'endpoint' — device installations).

    Examples:
        ntsk aicc agents deployments "Claude (Anthropic)" --type endpoint
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "type": deployment_type}
    add_filters(params, search=search)
    run_list(
        ctx,
        _agent_path(agent_name, "/deployments"),
        params,
        title=f"AICC Agent Deployments — {agent_name} ({deployment_type})",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        empty_hint=(
            "No deployments of this type. Run 'ntsk aicc agents get' and use one of the "
            "footprint.types values as --type."
        ),
    )


@agents_app.command("trend")
def agent_trend(
    ctx: typer.Context,
    agent_name: str = typer.Argument(..., help="Exact agent name, e.g. 'Claude (Anthropic)'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show the traffic trend for one agent (bytes/sessions per bucket).

    Queries GET /api/v2/aicc/inventory/agents/{agent_name}/traffic-trend.

    Examples:
        ntsk aicc agents trend "Claude (Anthropic)" --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _agent_path(agent_name, "/traffic-trend"),
        {"start_time": start_iso, "end_time": end_iso, "timezone": tz},
        spinner_text=f"Fetching traffic trend for {agent_name}...",
    )
    payload = unwrap_data(response)
    rows = payload.get("data") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        rows if isinstance(rows, list) else payload,
        title=f"AICC Agent Traffic Trend — {agent_name}",
        empty_hint="No trend data in this window.",
    )
