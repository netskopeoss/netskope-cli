"""AICC (AI Command Center) command group.

Discover and govern the AI ecosystem in your traffic: generative-AI
applications, MCP servers, native agents, models, extensions, and the
identities driving usage — with CCI risk scoring, usage analytics, alert
posture, and one-command AI Risk Report data.
"""

from __future__ import annotations

from typing import Optional

import typer

# ---------------------------------------------------------------------------
# Top-level AICC app
# ---------------------------------------------------------------------------
aicc_app = typer.Typer(
    name="aicc",
    help=(
        "AI Command Center — discover and govern AI usage across your organization.\n\n"
        "Inventories every AI application, MCP server, native agent, model, and "
        "extension observed in your traffic, tied to the identities using them, with "
        "Cloud Confidence Index risk scoring, usage analytics, alert posture, and DLP "
        "data-protection views. Start with 'ntsk aicc guide' for the full cheat sheet, "
        "'ntsk aicc overview' for a dashboard summary, or 'ntsk aicc report' to build "
        "an AI Risk Report."
    ),
    no_args_is_help=True,
)

from netskope_cli.commands.aicc._common import (  # noqa: E402
    AICC_BASE,
    HELP_END,
    HELP_START,
    aicc_get,
    build_aicc_client,
    resolve_time_range,
    show_payload,
    unwrap_data,
)
from netskope_cli.commands.aicc.agents_cmd import agents_app  # noqa: E402
from netskope_cli.commands.aicc.analytics_cmd import analytics_app  # noqa: E402
from netskope_cli.commands.aicc.apps_cmd import apps_app  # noqa: E402
from netskope_cli.commands.aicc.dataprot_cmd import dataprot_app  # noqa: E402
from netskope_cli.commands.aicc.extensions_cmd import extensions_app  # noqa: E402
from netskope_cli.commands.aicc.guide_cmd import guide  # noqa: E402
from netskope_cli.commands.aicc.identities_cmd import identities_app  # noqa: E402
from netskope_cli.commands.aicc.mcp_cmd import mcp_app  # noqa: E402
from netskope_cli.commands.aicc.models_cmd import models_app  # noqa: E402
from netskope_cli.commands.aicc.report_cmd import report  # noqa: E402

aicc_app.add_typer(apps_app, name="apps")
aicc_app.add_typer(mcp_app, name="mcp")
aicc_app.add_typer(identities_app, name="identities")
aicc_app.add_typer(models_app, name="models")
aicc_app.add_typer(agents_app, name="agents")
aicc_app.add_typer(extensions_app, name="extensions")
aicc_app.add_typer(analytics_app, name="analytics")
aicc_app.add_typer(dataprot_app, name="data-protection")

aicc_app.command("guide")(guide)
aicc_app.command("report")(report)


# ---------------------------------------------------------------------------
# Top-level convenience commands
# ---------------------------------------------------------------------------
@aicc_app.command("coverage")
def coverage(ctx: typer.Context) -> None:
    """Show the earliest date AICC has data for on this tenant.

    Queries GET /api/v2/aicc/data-coverage. Use this before requesting long
    historical windows — start_time values before data_available_since
    return empty results.

    Examples:
        ntsk aicc coverage
    """
    response = aicc_get(ctx, f"{AICC_BASE}/data-coverage", spinner_text="Checking data coverage...")
    show_payload(ctx, unwrap_data(response), title="AICC — Data Coverage")


@aicc_app.command("overview")
def overview(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """One-call dashboard summary: entity counts, traffic/session KPIs, alerts.

    Combines /analytics/entity-counts, /analytics/sums (traffic + sessions),
    /analytics/counts (alerts), and /data-coverage into a single view — the
    fastest way to answer "what does AI usage look like here?".

    Examples:
        ntsk aicc overview
        ntsk aicc overview --start 30d -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    window = {"start_time": start_iso, "end_time": end_iso}
    client = build_aicc_client(ctx)

    def get(path: str, params: dict, label: str) -> object:
        return unwrap_data(aicc_get(ctx, path, params, spinner_text=f"Fetching {label}...", client=client))

    entity_counts = get(f"{AICC_BASE}/analytics/entity-counts", dict(window), "entity counts")
    traffic = get(f"{AICC_BASE}/analytics/sums", {**window, "type": "traffic", "timezone": "UTC"}, "traffic")
    sessions = get(f"{AICC_BASE}/analytics/sums", {**window, "type": "sessions", "timezone": "UTC"}, "sessions")
    alerts = get(f"{AICC_BASE}/analytics/counts", {**window, "type": "alerts", "timezone": "UTC"}, "alerts")
    cov = get(f"{AICC_BASE}/data-coverage", {}, "coverage")

    def kpi(payload: object) -> dict:
        if not isinstance(payload, dict):
            return {}
        return {k: payload.get(k) for k in ("value", "previous_value", "trend")}

    summary: dict = {
        "time_range": window,
        "entities": (
            {k: v for k, v in (entity_counts or {}).items() if k != "time_range"}
            if isinstance(entity_counts, dict)
            else {}
        ),
        "traffic_bytes": kpi(traffic),
        "sessions": kpi(sessions),
        "alerts": kpi(alerts),
        "data_available_since": cov.get("data_available_since") if isinstance(cov, dict) else None,
    }
    show_payload(ctx, summary, title="AICC — Overview")


__all__ = ["aicc_app"]
