"""SaaS Security Posture Management (SPM) commands for the Netskope CLI.

Provides subcommands for querying SaaS application posture scores,
browsing app inventories, listing posture rules, and reviewing recent
configuration changes.  Use these commands to monitor your SaaS security
posture, identify misconfigured applications, and track drift over time.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import NotFoundError
from netskope_cli.core.output import OutputFormatter, echo_error, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

spm_app = typer.Typer(
    name="spm",
    help="SaaS Security Posture Management — posture scores, rules, and inventory.",
    no_args_is_help=True,
)

_apps_app = typer.Typer(
    name="apps",
    help="List and inspect monitored SaaS applications.",
    no_args_is_help=True,
)

_rules_app = typer.Typer(
    name="rules",
    help="List and inspect posture policy rules.",
    no_args_is_help=True,
)

spm_app.add_typer(_apps_app, name="apps")
spm_app.add_typer(_rules_app, name="rules")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_console(ctx: typer.Context) -> Console:
    """Build a Console, respecting the global --no-color flag."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _build_formatter(ctx: typer.Context) -> OutputFormatter:
    """Create an OutputFormatter respecting global flags."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


# ---------------------------------------------------------------------------
# Apps commands
# ---------------------------------------------------------------------------


@_apps_app.command("list")
def apps_list(ctx: typer.Context) -> None:
    """List all SaaS applications monitored by Netskope SPM.

    Queries GET /api/v2/spm/apps and returns every connected SaaS
    application along with its current posture score, number of passing
    and failing checks, and the date of the last assessment.  Use this
    command for a quick overview of your SaaS security posture across
    all monitored apps.

    Examples:
        # List all monitored SaaS apps
        netskope spm apps list

        # Output as JSON for downstream processing
        netskope -o json spm apps list

        # Export as CSV for a compliance report
        netskope -o csv spm apps list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching SPM apps...", no_color=no_color):
        data = client.request("GET", "/api/v2/spm/apps")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="SPM Applications")


@_apps_app.command("get")
def apps_get(
    ctx: typer.Context,
    app_name: str = typer.Argument(
        ...,
        help=(
            "Name of the SaaS application to retrieve details for, exactly as "
            "it appears in the SPM dashboard (e.g. 'Microsoft 365', 'Salesforce', "
            "'Slack').  Run 'netskope spm apps list' to see available names."
        ),
    ),
) -> None:
    """Get detailed posture information for a specific SaaS application.

    Queries GET /api/v2/spm/apps/{name} and returns the full posture
    report including the overall score, individual check results, risk
    categories, and remediation recommendations.  Use this to drill
    into a specific app after spotting a low score in the list view.

    Examples:
        # Get posture details for Microsoft 365
        netskope spm apps get "Microsoft 365"

        # Get details for Salesforce as YAML
        netskope -o yaml spm apps get Salesforce

        # Get details for Slack as JSON
        netskope -o json spm apps get Slack
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching details for {app_name}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/spm/apps/{urllib.parse.quote(app_name, safe='')}")

    formatter.format_output(data, fmt=_get_output_format(ctx), title=f"SPM — {app_name}")


# ---------------------------------------------------------------------------
# Inventory command
# ---------------------------------------------------------------------------


@spm_app.command("inventory")
def inventory(
    ctx: typer.Context,
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "JSON filter expression to narrow the inventory query.  The filter "
            "is passed directly to the API and supports field-level matching. "
            'Example: \'{"app_name": "Slack"}\' to return only Slack entries.'
        ),
    ),
) -> None:
    """Query the SaaS application inventory with optional filters.

    Sends POST /api/v2/spm/inventory to search the full inventory of
    SaaS applications discovered or connected in your tenant.  Unlike
    'spm apps list' which only shows monitored apps, the inventory
    includes all discovered SaaS usage.  Use the --filter flag to
    narrow results by app name, category, or other fields.

    Examples:
        # Query the full SaaS inventory
        netskope spm inventory

        # Filter by app name
        netskope spm inventory --filter '{"app_name": "Slack"}'

        # Output as JSON for scripting
        netskope -o json spm inventory
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    body: dict[str, object] = {}
    if filter is not None:
        body["filter"] = filter

    try:
        with spinner("Querying SPM inventory...", no_color=no_color):
            data = client.request("POST", "/api/v2/spm/inventory", json_data=body or None)
    except NotFoundError:
        echo_error(
            "This endpoint may not be available on your tenant (HTTP 404).",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    formatter.format_output(data, fmt=_get_output_format(ctx), title="SPM Inventory")


# ---------------------------------------------------------------------------
# Posture score command
# ---------------------------------------------------------------------------


@spm_app.command("posture-score")
def posture_score(ctx: typer.Context) -> None:
    """Get the overall SaaS security posture score for your tenant.

    Queries GET /api/v2/spm/saas_posture_score and returns the
    aggregated posture score across all monitored SaaS applications.
    The score reflects how well your SaaS configurations align with
    security best practices.  Use this command for executive dashboards
    or to track posture improvements over time.

    Examples:
        # Get the overall posture score
        netskope spm posture-score

        # Output as JSON for a monitoring integration
        netskope -o json spm posture-score

        # Output as YAML for readability
        netskope -o yaml spm posture-score
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    try:
        with spinner("Fetching posture score...", no_color=no_color):
            data = client.request("GET", "/api/v2/spm/saas_posture_score")
    except NotFoundError:
        echo_error(
            "This endpoint may not be available on your tenant (HTTP 404).",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    formatter.format_output(data, fmt=_get_output_format(ctx), title="SPM Posture Score")


# ---------------------------------------------------------------------------
# Rules commands
# ---------------------------------------------------------------------------


@_rules_app.command("list")
def rules_list(ctx: typer.Context) -> None:
    """List all posture policy rules configured in Netskope SPM.

    Queries GET /api/v2/spm/policy/rules and returns every posture
    rule including its name, severity, target application, check type,
    and current pass/fail status.  Posture rules define the security
    checks that SPM runs against your SaaS configurations.  Use this
    command to audit which rules are active and identify gaps in
    coverage.

    Examples:
        # List all posture rules
        netskope spm rules list

        # Output as JSON for automation
        netskope -o json spm rules list

        # Export rules as CSV for a compliance audit
        netskope -o csv spm rules list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching posture rules...", no_color=no_color):
        data = client.request("GET", "/api/v2/spm/policy/rules")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="SPM Posture Rules")


# ---------------------------------------------------------------------------
# Recent changes command
# ---------------------------------------------------------------------------


@spm_app.command("changes")
def changes(ctx: typer.Context) -> None:
    """Get statistics on recent SaaS configuration changes.

    Queries GET /api/v2/spm/apps/recentchanges/getstats and returns a
    summary of configuration changes detected across your monitored
    SaaS applications.  This helps you identify drift, unexpected
    modifications, or shadow-IT configuration changes that could
    weaken your security posture.

    Examples:
        # View recent change statistics
        netskope spm changes

        # Output as JSON for a drift-detection pipeline
        netskope -o json spm changes

        # View changes from a specific profile
        netskope --profile prod spm changes
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching recent changes...", no_color=no_color):
        data = client.request("GET", "/api/v2/spm/apps/recentchanges/getstats")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="SPM Recent Changes")
