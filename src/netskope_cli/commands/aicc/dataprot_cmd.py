"""AICC provider data-protection commands (``ntsk aicc data-protection``)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_ALL,
    HELP_END,
    HELP_FIELDS,
    HELP_LIMIT,
    HELP_OFFSET,
    HELP_START,
    add_filters,
    aicc_get,
    resolve_time_range,
    run_list,
    show_payload,
    unwrap_data,
)

dataprot_app = typer.Typer(
    name="data-protection",
    help=(
        "Per-provider DLP posture for major AI platforms.\n\n"
        "Shows the DLP violations detected in traffic to a specific AI provider "
        "(anthropic, mscopilot, or chatgpt) — summarised by object type and severity, "
        "or as a detailed violations table with user, resource, and timestamp."
    ),
    no_args_is_help=True,
)


class _Provider(str, Enum):
    anthropic = "anthropic"
    mscopilot = "mscopilot"
    chatgpt = "chatgpt"


_PROVIDER_HELP = "AI provider: anthropic, mscopilot, or chatgpt."


@dataprot_app.command("summary")
def dp_summary(
    ctx: typer.Context,
    provider: _Provider = typer.Argument(..., help=_PROVIDER_HELP),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show DLP violation counts by object type and severity for a provider.

    Queries GET /api/v2/aicc/provider/{provider}/data-protection/summary.
    Returns a 'breakdown' with one row per object type (AI Response, File,
    Prompt, ...) and critical/high/medium/low counts.

    Examples:
        ntsk aicc data-protection summary anthropic --start 30d
        ntsk aicc data-protection summary chatgpt -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        f"{AICC_BASE}/provider/{provider.value}/data-protection/summary",
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {provider.value} data-protection summary...",
    )
    payload = unwrap_data(response)
    breakdown = payload.get("breakdown") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        breakdown if isinstance(breakdown, list) else payload,
        title=f"AICC Data Protection — {provider.value}",
        empty_hint="No DLP violations for this provider in the window.",
    )


@dataprot_app.command("violations")
def dp_violations(
    ctx: typer.Context,
    provider: _Provider = typer.Argument(..., help=_PROVIDER_HELP),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    severity: Optional[str] = typer.Option(
        None, "--severity", help="Filter by severity: critical, high, medium, or low."
    ),
    object_type: Optional[str] = typer.Option(
        None,
        "--object-type",
        help="Filter by object type from the summary breakdown, e.g. File, Prompt, 'AI Response'.",
    ),
    user: Optional[str] = typer.Option(None, "--user", help="Filter to one user (email)."),
    search: Optional[str] = typer.Option(None, "--search", help="Free-text search across violations."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=HELP_FIELDS),
) -> None:
    """List individual DLP violations for a provider.

    Queries GET /api/v2/aicc/provider/{provider}/data-protection/violations.
    Rows include severity, violation (the DLP profile), object_type, user,
    resource (file/prompt name), timestamp, and status. Totals can be large
    (tens of thousands) — filter before using --all.

    Examples:
        ntsk aicc data-protection violations anthropic --severity critical --start 30d
        ntsk aicc data-protection violations chatgpt --user alice@example.com -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(params, severity=severity, object_type=object_type, user=user, search=search)
    run_list(
        ctx,
        f"{AICC_BASE}/provider/{provider.value}/data-protection/violations",
        params,
        title=f"AICC DLP Violations — {provider.value}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        fields=fields,
        default_fields=["severity", "violation", "object_type", "user", "resource", "timestamp", "status"],
        empty_hint="No DLP violations for this provider in the window.",
    )
