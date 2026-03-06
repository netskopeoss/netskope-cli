"""Alert commands for the Netskope CLI.

Provides subcommands to query alerts from the Netskope events/datasearch API
and to list known alert types.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, spinner

# ---------------------------------------------------------------------------
# Known alert types
# ---------------------------------------------------------------------------
_ALERT_TYPES: list[dict[str, str]] = [
    {"type": "DLP", "description": "Data Loss Prevention policy violations"},
    {"type": "malware", "description": "Malware detection alerts"},
    {"type": "anomaly", "description": "Anomalous user or entity behaviour"},
    {"type": "compromised", "description": "Compromised credential alerts"},
    {"type": "policy", "description": "Security policy violation alerts"},
    {"type": "Legal Hold", "description": "Legal hold notification alerts"},
    {"type": "quarantine", "description": "File quarantine alerts"},
    {"type": "remediation", "description": "Automated remediation action alerts"},
    {"type": "uba", "description": "User Behaviour Analytics alerts"},
    {"type": "ctep", "description": "Client Threat Endpoint Protection alerts"},
    {"type": "watchlist", "description": "Watchlist match alerts"},
    {"type": "security_assessment", "description": "Security assessment finding alerts"},
]

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
alerts_app = typer.Typer(
    name="alerts",
    help=(
        "List and filter security alerts from the Netskope platform.\n\n"
        "This command group provides access to security alerts via the events "
        "datasearch API. Use 'list' to query alerts with optional filters for "
        "severity, type, time range, and custom queries. Use 'types' to view "
        "the known alert types (DLP, malware, anomaly, compromised, etc.) "
        "as a local reference."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_console(ctx: typer.Context) -> Console:
    """Build a Console, respecting the global --no-color flag."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Build an OutputFormatter from the current context."""
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


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@alerts_app.command("get")
def get_alert(
    ctx: typer.Context,
    id: Optional[str] = typer.Argument(
        None,
        help="Alert ID (_id) to look up. If provided, other filters are ignored.",
    ),
    user: Optional[str] = typer.Option(
        None,
        "--user",
        "-u",
        help="Filter by user email address (exact match).",
    ),
    app: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        help="Filter by application name (exact match).",
    ),
    alert_name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Filter by alert name (exact match).",
    ),
    alert_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by alert type (e.g. DLP, malware, anomaly).",
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help="Filter by severity level (e.g. high, medium, low, critical).",
    ),
    activity: Optional[str] = typer.Option(
        None,
        "--activity",
        help="Filter by activity type (e.g. 'Login Attempt', 'Upload').",
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "--since",
        "-s",
        help="Start of time range. Relative offset (24h, 7d) or epoch.",
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help="End of time range. Relative offset or epoch.",
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help="Maximum number of alerts to return (ignored when looking up by ID).",
    ),
) -> None:
    """Look up alerts by ID, user, app, name, or other fields.

    When an ID is provided as a positional argument, fetches that single alert.
    Otherwise, filters alerts by the provided options and returns matches.

    Examples:
        ntsk alerts get f1c18fd0065a21e4ace54efb
        ntsk alerts get --user alice@example.com --since 7d
        ntsk alerts get --app Slack --type DLP
        ntsk alerts get --severity high --since 24h
        ntsk alerts get --name "ShinyHunters: cargurus.com Breach"
        ntsk alerts get --activity "Login Attempt" --user bob@example.com
    """
    import re

    if id is None and all(v is None for v in [user, app, alert_name, alert_type, severity, activity]):
        from netskope_cli.core.output import echo_error

        echo_error(
            "Provide an alert ID or at least one filter" " (--user, --app, --name, --type, --severity, --activity)."
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj

    # Build JQL query from the provided filters.
    clauses: list[str] = []

    def _safe_value(name: str, value: str) -> str:
        """Allow printable chars but reject quotes that would break JQL."""
        if '"' in value or "'" in value:
            from netskope_cli.core.output import echo_error

            echo_error(f"Invalid --{name} value: quotes are not allowed.")
            raise typer.Exit(code=1)
        return value

    if id is not None:
        if not re.match(r"^[a-fA-F0-9]+$", id):
            from netskope_cli.core.output import echo_error

            echo_error(f"Invalid alert ID: {id!r}. Expected a hex string.")
            raise typer.Exit(code=1)
        clauses.append(f'_id eq "{id}"')
    else:
        if user is not None:
            clauses.append(f'user eq "{_safe_value("user", user)}"')
        if app is not None:
            clauses.append(f'app eq "{_safe_value("app", app)}"')
        if alert_name is not None:
            clauses.append(f'alert_name eq "{_safe_value("name", alert_name)}"')
        if alert_type is not None:
            clauses.append(f'alert_type eq "{_safe_value("type", alert_type)}"')
        if severity is not None:
            clauses.append(f'severity eq "{_safe_value("severity", severity)}"')
        if activity is not None:
            clauses.append(f'activity eq "{_safe_value("activity", activity)}"')

    query = " AND ".join(clauses)
    params: dict[str, object] = {"query": query}

    if start is not None or end is not None:
        from netskope_cli.utils.helpers import validate_time_range

        effective_start = start or "24h"
        unix_start, unix_end = validate_time_range(effective_start, end)
        params["starttime"] = unix_start
        params["endtime"] = unix_end

    params["limit"] = 1 if id is not None else limit

    quiet = getattr(state, "quiet", False) if state else False
    with spinner("Fetching alert...", quiet=quiet):
        data = client.request("GET", "/api/v2/events/datasearch/alert", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="Alert" if id is not None else "Alerts",
        default_fields=["_id", "alert_name", "alert_type", "severity", "user", "app", "activity", "timestamp"],
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@alerts_app.command("list")
def list_alerts(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=(
            "JQL query string to filter alerts. Supports field comparisons and logical "
            'operators. For example: \'alert_type eq "DLP"\' or \'severity eq "high" '
            'AND user eq "alice@example.com"\'. Omit to return all alerts.'
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=(
            "Comma-separated list of field names to include in the response. Reduces "
            "payload size and focuses on relevant data. For example: "
            "'alert_name,severity,user,timestamp'. Omit to return all fields."
        ),
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "--since",
        "-s",
        help=(
            "Start of the time range. Accepts a Unix epoch timestamp (seconds) or a "
            "relative offset like '24h', '7d', '1h'. Only alerts after this time are "
            "returned. Omit to use the API default time range."
        ),
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=(
            "End of the time range. Accepts a Unix epoch timestamp or relative offset. "
            "Defaults to the current time when omitted. Must be later than --start."
        ),
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=(
            "Maximum number of alerts to return. Use smaller values for quick lookups "
            "and larger values for bulk exports. Defaults to 25."
        ),
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        "--by",
        help=(
            "Field name to group (aggregate) results by, such as 'alert_type', "
            "'severity', or 'user'. Returns aggregated counts per unique value. "
            "Omit for ungrouped results."
        ),
    ),
    alert_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Filter by alert type (e.g. 'DLP', 'malware', 'anomaly'). "
            "Shortcut for --query 'alert_type eq \"VALUE\"'. If both --type "
            "and --query are provided, they are combined with AND."
        ),
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=(
            "Field name to sort results by. For example: 'timestamp' to sort "
            "chronologically. Combine with --desc or --asc to control direction. "
            "Omit to use the API default sort order."
        ),
    ),
    descending: bool = typer.Option(
        False,
        "--desc",
        help="Sort in descending order (newest/highest first). Use with --order-by.",
    ),
    ascending: bool = typer.Option(
        False,
        "--asc",
        help="Sort in ascending order (oldest/lowest first). Use with --order-by.",
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help="Print only the total count of matching alerts.",
    ),
) -> None:
    """List security alerts from the Netskope events datasearch API.

    This is a convenience alias for 'netskope events alerts'. Both commands
    hit the same API endpoint.

    Queries GET /api/v2/events/datasearch/alert with optional filtering,
    time ranges, field selection, grouping, and sorting. Use this for alert
    triage, security monitoring dashboards, and automated alert processing.

    Examples:
        ntsk alerts list
        ntsk alerts list --since 7d --limit 50
        ntsk alerts list --query 'alert_type eq "DLP"' --limit 50
        ntsk -o json alerts list --query 'severity eq "critical"' --since 24h
        ntsk alerts list --count
    """
    # Validate limit
    if limit <= 0:
        from netskope_cli.core.output import echo_error

        echo_error(f"Invalid --limit value: {limit}. Must be a positive integer.")
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj
    # Merge local --count flag with global --count
    count = count or (getattr(state, "count", False) if state else False)

    params: dict[str, object] = {}

    # Build the effective query, combining --type and --query if both given.
    effective_query = query
    if alert_type is not None:
        # Sanitise the value to prevent JQL injection — reject characters
        # that could break out of the quoted string or alter query logic.
        import re

        if not re.match(r"^[a-zA-Z0-9_ -]+$", alert_type):
            from netskope_cli.core.output import echo_error

            echo_error(
                f"Invalid --type value: {alert_type!r}. "
                "Only letters, digits, spaces, hyphens and underscores are allowed."
            )
            raise typer.Exit(code=1)
        type_filter = f'alert_type eq "{alert_type}"'
        if effective_query:
            effective_query = f"{effective_query} AND {type_filter}"
        else:
            effective_query = type_filter

    if effective_query is not None:
        params["query"] = effective_query
    if fields is not None:
        params["fields"] = fields
    if start is not None or end is not None:
        from netskope_cli.utils.helpers import validate_time_range

        effective_start = start or "24h"
        unix_start, unix_end = validate_time_range(effective_start, end)
        params["starttime"] = unix_start
        params["endtime"] = unix_end
    params["limit"] = 10000 if count else limit
    if group_by is not None:
        params["groupbys"] = group_by
    if order_by is not None:
        direction = ""
        if descending:
            direction = " DESC"
        elif ascending:
            direction = " ASC"
        params["orderby"] = f"{order_by}{direction}"

    quiet = getattr(state, "quiet", False) if state else False
    with spinner("Fetching alerts...", quiet=quiet):
        data = client.request("GET", "/api/v2/events/datasearch/alert", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="Alerts",
        default_fields=["alert_name", "alert_type", "severity", "user", "app", "timestamp"],
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@alerts_app.command("summary")
def alert_summary(
    ctx: typer.Context,
    by: str = typer.Option(
        "alert_type",
        "--by",
        "--group-by",
        "-b",
        help="Field to group by (e.g. alert_type, severity, user, app).",
    ),
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help="JQL query string to filter alerts before aggregating.",
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "--since",
        "-s",
        help="Start of time range. Relative offset (24h, 7d) or epoch.",
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help="End of time range. Relative offset or epoch.",
    ),
) -> None:
    """Summarise alerts by a grouping field (e.g. type, severity, user).

    Fetches alerts and aggregates counts per unique value of the chosen field.
    Defaults to grouping by alert_type over the last 24 hours.

    Examples:
        ntsk alerts summary
        ntsk alerts summary --by severity
        ntsk alerts summary --group-by user --since 7d
        ntsk -o json alerts summary --by app --query 'severity eq "high"'
    """
    from collections import Counter

    from netskope_cli.utils.helpers import validate_time_range

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj

    params: dict[str, object] = {"limit": 10000}

    if query is not None:
        params["query"] = query

    effective_start = start or "24h"
    unix_start, unix_end = validate_time_range(effective_start, end)
    params["starttime"] = unix_start
    params["endtime"] = unix_end

    quiet = getattr(state, "quiet", False) if state else False
    with spinner(f"Summarising alerts by {by}...", quiet=quiet):
        data = client.request("GET", "/api/v2/events/datasearch/alert", params=params)

    # Unwrap the API envelope to get the list of records, then aggregate locally.
    from netskope_cli.core.output import unwrap_api_response

    records, _meta = unwrap_api_response(data)

    if isinstance(records, list) and records:
        counts = Counter(str(row.get(by, "unknown")) if isinstance(row, dict) else "unknown" for row in records)
        summary_data = [{by: value, "count": count} for value, count in counts.most_common()]
    else:
        summary_data = []

    formatter.format_output(
        summary_data,
        fmt=fmt,
        title=f"Alert Summary by {by}",
        unwrap=False,
        empty_hint=(
            f"No alerts found for grouping by '{by}'. "
            "This can happen when the grouping field doesn't exist in the matching alerts. "
            "Try a different field (e.g. --by severity, --by user) or use 'alerts list' "
            "to see individual records."
        ),
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=False,
    )


@alerts_app.command("types")
def list_alert_types(
    ctx: typer.Context,
) -> None:
    """List all known Netskope alert types with descriptions.

    Displays a local reference table of common alert types (DLP, malware,
    anomaly, compromised, policy, quarantine, uba, etc.) and their descriptions.
    This command does NOT call the API -- it shows a built-in reference. Use the
    type values shown here as filter values for 'netskope alerts list --query'.

    Examples:
        netskope alerts types
        netskope -o json alerts types
    """
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    formatter.format_output(_ALERT_TYPES, fmt=fmt, title="Known Alert Types")
