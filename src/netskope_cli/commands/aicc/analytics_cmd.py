"""AICC analytics commands (``ntsk aicc analytics``).

These endpoints power the AI Command Center dashboard: KPI counts and sums
with time series, per-entity-type totals, dimension breakdowns (the pie/bar
charts), and the alert triage matrix.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, TypedDict

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_END,
    HELP_START,
    HELP_TIMEZONE,
    add_filters,
    aicc_get,
    get_console,
    resolve_time_range,
    show_payload,
    unwrap_data,
)

analytics_app = typer.Typer(
    name="analytics",
    help=(
        "Aggregated AI-usage analytics — KPIs, breakdowns, and alert matrices.\n\n"
        "Use 'entities' for headline counts (apps, MCP servers, agents, models, users, "
        "unknown), 'counts'/'sums' for KPI time series with trend-vs-prior-window, "
        "'breakdown' for dimension charts (e.g. apps by status, identities by user "
        "group), and 'alerts-matrix'/'alert-policies' for the alert triage view."
    ),
    no_args_is_help=True,
)


class _CountType(str, Enum):
    identities = "identities"
    assets = "assets"
    alerts = "alerts"


class _SumType(str, Enum):
    traffic = "traffic"
    sessions = "sessions"


class _BreakdownEntity(str, Enum):
    apps = "apps"
    mcp = "mcp"
    identities = "identities"
    models = "models"
    agents = "agents"


class _AlertAsset(str, Enum):
    ai_app = "AI App"
    mcp_server = "MCP Server"


# Per-entity valid dimensions and metrics, straight from the API spec.
class _Breakdown(TypedDict):
    path: str
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]


_BREAKDOWN_CONFIG: dict[str, _Breakdown] = {
    "apps": {
        "path": f"{AICC_BASE}/analytics/ai-applications",
        "dimensions": ("category", "status", "ccl"),
        "metrics": ("count", "bytes", "sessions", "transactions"),
    },
    "mcp": {
        "path": f"{AICC_BASE}/analytics/mcp-servers",
        "dimensions": ("category", "ccl"),
        "metrics": ("count", "sessions", "transactions"),
    },
    "identities": {
        "path": f"{AICC_BASE}/analytics/identities",
        "dimensions": ("user_group", "ou", "activity_level"),
        "metrics": ("count", "bytes", "sessions", "transactions"),
    },
    "models": {
        "path": f"{AICC_BASE}/analytics/models",
        "dimensions": ("footprint", "provider"),
        "metrics": ("count", "bytes", "identities"),
    },
    "agents": {
        "path": f"{AICC_BASE}/analytics/agents",
        "dimensions": ("category", "framework"),
        "metrics": ("count", "bytes", "sessions", "identities"),
    },
}


@analytics_app.command("entities")
def entity_counts(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    active_only: bool = typer.Option(
        False, "--active-only", help="Only count entities with activity inside the window."
    ),
) -> None:
    """Show headline entity counts — the executive-summary numbers.

    Queries GET /api/v2/aicc/analytics/entity-counts. Returns applications,
    mcp_servers, agents, models, users, nhi (non-human identities), and
    unknown (unattributed sources) counts for the window.

    Examples:
        ntsk aicc analytics entities
        ntsk aicc analytics entities --start 2026-06-01 --end 2026-06-30 -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(params, active_only=active_only)
    response = aicc_get(ctx, f"{AICC_BASE}/analytics/entity-counts", params, spinner_text="Fetching entity counts...")
    show_payload(ctx, unwrap_data(response), title="AICC — Entity Counts")


@analytics_app.command("counts")
def counts(
    ctx: typer.Context,
    count_type: _CountType = typer.Argument(
        ..., help="What to count: identities, assets (apps + MCP servers + agents + models), or alerts."
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show a distinct-count KPI with trend and time series.

    Queries GET /api/v2/aicc/analytics/counts. Returns value (the count),
    previous_value and trend (%) versus the prior comparable window, and a
    bucketed time series under 'data'.

    Examples:
        ntsk aicc analytics counts identities
        ntsk aicc analytics counts alerts --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        f"{AICC_BASE}/analytics/counts",
        {"type": count_type.value, "start_time": start_iso, "end_time": end_iso, "timezone": tz},
        spinner_text=f"Counting {count_type.value}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC — {count_type.value.title()} Count")


@analytics_app.command("sums")
def sums(
    ctx: typer.Context,
    sum_type: _SumType = typer.Argument(..., help="What to sum: traffic (bytes) or sessions."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show a summed KPI (total traffic or sessions) with trend and time series.

    Queries GET /api/v2/aicc/analytics/sums. Returns value, previous_value,
    trend (%) versus the prior window, and a bucketed time series.

    Examples:
        ntsk aicc analytics sums traffic
        ntsk aicc analytics sums sessions --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        f"{AICC_BASE}/analytics/sums",
        {"type": sum_type.value, "start_time": start_iso, "end_time": end_iso, "timezone": tz},
        spinner_text=f"Summing {sum_type.value}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC — Total {sum_type.value.title()}")


@analytics_app.command("breakdown")
def breakdown(
    ctx: typer.Context,
    entity: _BreakdownEntity = typer.Argument(
        ..., help="Entity to break down: apps, mcp, identities, models, or agents."
    ),
    dimension: str = typer.Option(
        ...,
        "--dimension",
        "-d",
        help=(
            "Dimension to group by. Valid per entity — apps: category|status|ccl; "
            "mcp: category|ccl; identities: user_group|ou|activity_level; "
            "models: footprint|provider; agents: category|framework."
        ),
    ),
    metric: str = typer.Option(
        "count",
        "--metric",
        "-m",
        help=(
            "Metric to aggregate. Valid per entity — apps: count|bytes|sessions|transactions; "
            "mcp: count|sessions|transactions; identities: count|bytes|sessions|transactions; "
            "models: count|bytes|identities; agents: count|bytes|sessions|identities. Default: count."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Break an entity population down by a dimension (the dashboard charts).

    Queries GET /api/v2/aicc/analytics/{ai-applications|mcp-servers|
    identities|models|agents}. Returns 'segments' rows with label and value.
    Also the best way to discover valid filter values for the list commands
    (e.g. run '--dimension category' to see every category in your tenant).

    Examples:
        ntsk aicc analytics breakdown apps --dimension status
        ntsk aicc analytics breakdown apps --dimension ccl --metric bytes
        ntsk aicc analytics breakdown identities --dimension user_group
        ntsk aicc analytics breakdown models --dimension provider
    """
    config = _BREAKDOWN_CONFIG[entity.value]
    dimensions = config["dimensions"]
    metrics = config["metrics"]
    if dimension not in dimensions:
        raise typer.BadParameter(f"Invalid dimension {dimension!r} for {entity.value}. Valid: {', '.join(dimensions)}")
    if metric not in metrics:
        raise typer.BadParameter(f"Invalid metric {metric!r} for {entity.value}. Valid: {', '.join(metrics)}")

    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"dimension": dimension, "metric": metric, "start_time": start_iso, "end_time": end_iso}
    response = aicc_get(
        ctx,
        str(config["path"]),
        params,
        spinner_text=f"Fetching {entity.value} by {dimension}...",
    )
    payload = unwrap_data(response)
    segments = payload.get("segments") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        segments if isinstance(segments, list) else payload,
        title=f"AICC — {entity.value.title()} by {dimension}",
        empty_hint="No data for this breakdown in the window.",
    )


@analytics_app.command("alerts-matrix")
def alerts_matrix(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    detection: Optional[str] = typer.Option(None, "--detection", help="Filter to one detection type, e.g. DLP."),
    asset: Optional[_AlertAsset] = typer.Option(
        None, "--asset", help="Filter to one asset class: 'AI App' or 'MCP Server'."
    ),
) -> None:
    """Show the alert triage heatmap — alert counts by asset class and detection type.

    Queries GET /api/v2/aicc/analytics/alerts/matrix. Rows are (asset,
    detection, count) triples, e.g. ('AI App', 'DLP', 42). Use the detection
    values you see here as --detection for 'alert-policies'.

    Examples:
        ntsk aicc analytics alerts-matrix --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(params, detection=detection, asset=asset.value if asset else None)
    response = aicc_get(ctx, f"{AICC_BASE}/analytics/alerts/matrix", params, spinner_text="Fetching alert matrix...")
    payload = unwrap_data(response)
    items = payload.get("items") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        items if isinstance(items, list) else payload,
        title="AICC — Alerts Matrix",
        empty_hint="No alerts in the window.",
    )


@analytics_app.command("alert-policies")
def alert_policies(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    detection: Optional[str] = typer.Option(
        None, "--detection", help="Filter to one detection type from the alerts matrix, e.g. DLP."
    ),
    asset: Optional[_AlertAsset] = typer.Option(
        None, "--asset", help="Filter to one asset class: 'AI App' or 'MCP Server'."
    ),
) -> None:
    """Show which policies generated AI-related alerts, with severity and counts.

    Queries GET /api/v2/aicc/analytics/alerts/policies. Returns total_alerts
    plus rows of (policy, severity, count).

    Examples:
        ntsk aicc analytics alert-policies --start 30d
        ntsk aicc analytics alert-policies --detection DLP -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(params, detection=detection, asset=asset.value if asset else None)
    response = aicc_get(
        ctx, f"{AICC_BASE}/analytics/alerts/policies", params, spinner_text="Fetching alert policies..."
    )
    payload = unwrap_data(response)
    items = payload.get("items") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and payload.get("total_alerts") is not None:
        get_console(ctx).print(f"[dim]Total alerts: {payload['total_alerts']}[/dim]")
    show_payload(
        ctx,
        items if isinstance(items, list) else payload,
        title="AICC — Alert Policies",
        empty_hint="No alerts in the window.",
    )
