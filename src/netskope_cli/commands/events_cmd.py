"""Event query commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/events`` endpoints,
covering alerts, application, network, page, incident, audit, infrastructure,
client-status, endpoint DLP, and transaction event types.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import NetskopeError
from netskope_cli.core.output import OutputFormatter, spinner
from netskope_cli.utils.helpers import validate_time_range

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
events_app = typer.Typer(
    name="events",
    help=(
        "Query and stream security events from the Netskope platform.\n\n"
        "This command group provides access to all Netskope event types through the "
        "/api/v2/events endpoints. Each subcommand maps to a specific event category: "
        "alerts, application, network, page, incident, audit, infrastructure, "
        "client-status, epdlp (endpoint DLP), and transaction.\n\n"
        "All subcommands support JQL query filtering, field selection, time ranges, "
        "pagination, grouping, and sorting. Use -o json (before the subcommand) for programmatic "
        "consumption by scripts and AI agents."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Shared help strings (kept short enough for the 120-char line limit)
# ---------------------------------------------------------------------------
_HELP_QUERY = (
    "JQL (JSON Query Language) filter string to narrow results. Supports field comparisons, "
    "logical operators (AND, OR), and wildcards. For example: 'alert_type eq \"DLP\"' or "
    '\'user eq "alice@example.com" AND action eq "block"\'. Omit to return all events. '
    "Run 'netskope docs jql' for full JQL syntax reference."
)
_HELP_FIELDS = (
    "Comma-separated list of field names to include in the response. Use this to reduce "
    "payload size and focus on relevant data. For example: 'timestamp,user,action,app'. "
    "Omit to return all available fields."
)
_HELP_START = (
    "Start of the time range for the query. Accepts a Unix epoch timestamp (seconds) or a "
    "relative offset such as '24h' (last 24 hours), '7d' (last 7 days), or '1h' (last hour). "
    "Defaults to no time filter when omitted."
)
_HELP_END = (
    "End of the time range for the query. Accepts a Unix epoch timestamp (seconds) or a "
    "relative offset. Defaults to the current time ('now') when omitted. Must be later "
    "than --start."
)
_HELP_LIMIT = (
    "Maximum number of event records to return. Use smaller values for quick lookups and "
    "larger values for bulk exports. Defaults to 25. The API may enforce an upper bound."
)
_HELP_GROUP_BY = (
    "Field name to group (aggregate) results by, such as 'user', 'app', or 'action'. "
    "Returns aggregated counts per unique value of the specified field. "
    "Omit for ungrouped results."
)
_HELP_ORDER_BY = (
    "Sort field and optional direction for ordering results. Format: 'field_name ASC' or "
    "'field_name DESC'. For example: 'timestamp DESC' to get newest events first. "
    "Omit to use the API default sort order."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _parse_time_params(
    start: str | None,
    end: str | None,
) -> dict[str, int]:
    """Return ``starttime`` / ``endtime`` query-param dict.

    If *start* is ``None`` and *end* is set, *start* defaults to ``24h``.
    Returns an empty dict when neither value is provided.
    """
    if not start and not end:
        return {}

    effective_start = start or "24h"
    try:
        unix_start, unix_end = validate_time_range(effective_start, end)
    except ValueError as exc:
        raise NetskopeError(
            f"Invalid time range: {exc}",
            suggestion=("Use a Unix timestamp or relative offset " "(e.g. 24h, 7d)."),
        ) from exc
    return {"starttime": unix_start, "endtime": unix_end}


def _run_event_query(
    ctx: typer.Context,
    endpoint: str,
    *,
    query: str | None = None,
    fields: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 25,
    group_by: str | None = None,
    order_by: str | None = None,
    title: str = "Events",
    default_fields: list[str] | None = None,
    count_only: bool = False,
) -> None:
    """Execute a GET request against a Netskope events endpoint.

    Builds query parameters from the caller-supplied options, fires the
    request through :class:`NetskopeClient`, and renders the response
    using :class:`OutputFormatter`.
    """
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    output_fmt = state.output.value if state is not None else "table"
    quiet = state.quiet if state is not None else False
    count_only = count_only or (getattr(state, "count", False) if state is not None else False)

    # Validate limit
    if limit is not None and limit <= 0:
        raise NetskopeError(
            f"Invalid --limit value: {limit}. Must be a positive integer.",
            suggestion="Use --limit with a value greater than 0.",
        )

    client = _build_client(ctx)

    # -- Build query params ------------------------------------------------
    params: dict[str, Any] = {}

    if query:
        params["query"] = query
    if limit:
        params["limit"] = limit
    if group_by:
        params["groupbys"] = group_by
    if order_by:
        params["sortby"] = order_by

    params.update(_parse_time_params(start, end))

    # Field selection sent to the API
    selected_fields: list[str] | None = None
    if fields:
        selected_fields = [f.strip() for f in fields.split(",") if f.strip()]
        params["fields"] = ",".join(selected_fields)

    # -- Execute request ---------------------------------------------------
    if not quiet:
        with spinner("Querying events...", no_color=no_color):
            data = client.request("GET", endpoint, params=params)
    else:
        data = client.request("GET", endpoint, params=params)

    # -- Process and render ------------------------------------------------
    _render_event_response(
        data,
        title=title,
        output_fmt=output_fmt,
        no_color=no_color,
        selected_fields=selected_fields,
        default_fields=default_fields,
        count_only=count_only,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


def _run_audit_query(
    ctx: typer.Context,
    *,
    audit_type: str | None = None,
    fields: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 25,
    group_by: str | None = None,
    order_by: str | None = None,
) -> None:
    """Execute a GET against the audit events endpoint.

    The audit endpoint (``/api/v2/events/data/audit``) differs from the
    datasearch endpoints in that it uses a ``type`` parameter instead of
    ``query``.
    """
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    output_fmt = state.output.value if state is not None else "table"
    quiet = state.quiet if state is not None else False

    client = _build_client(ctx)

    # -- Build query params ------------------------------------------------
    params: dict[str, Any] = {}

    if audit_type:
        params["type"] = audit_type
    if limit:
        params["limit"] = limit
    if group_by:
        params["groupbys"] = group_by
    if order_by:
        params["sortby"] = order_by

    params.update(_parse_time_params(start, end))

    selected_fields: list[str] | None = None
    if fields:
        selected_fields = [f.strip() for f in fields.split(",") if f.strip()]
        params["fields"] = ",".join(selected_fields)

    # -- Execute request ---------------------------------------------------
    endpoint = "/api/v2/events/data/audit"

    if not quiet:
        with spinner("Querying audit events...", no_color=no_color):
            data = client.request("GET", endpoint, params=params)
    else:
        data = client.request("GET", endpoint, params=params)

    # -- Process and render ------------------------------------------------
    global_count = getattr(state, "count", False) if state is not None else False
    _render_event_response(
        data,
        title="Audit Events",
        output_fmt=output_fmt,
        no_color=no_color,
        selected_fields=selected_fields,
        default_fields=["audit_log_event", "timestamp", "severity_level", "user", "count"],
        count_only=global_count,
    )


def _render_event_response(
    data: Any,
    *,
    title: str,
    output_fmt: str,
    no_color: bool,
    selected_fields: list[str] | None,
    default_fields: list[str] | None = None,
    count_only: bool = False,
    strip_internal: bool = True,
    add_iso_timestamps: bool = True,
) -> None:
    """Validate and render an events API response."""
    if not isinstance(data, dict):
        raise NetskopeError(
            "Unexpected response format from the API.",
            details={"response": data},
        )

    ok = data.get("ok")
    if ok is not None and not ok:
        msg = data.get("message") or data.get("error") or "Unknown API error"
        raise NetskopeError(f"API returned an error: {msg}", details=data)

    if count_only:
        total = data.get("total", len(data.get("result", [])))
        print(total)
        return

    results = data.get("result", [])
    total = data.get("total")

    formatter = OutputFormatter(no_color=no_color, count_only=count_only)

    display_title = title
    if total is not None:
        display_title = f"{title} ({total} total, showing {len(results)})"

    formatter.format_output(
        results,
        fmt=output_fmt,
        fields=selected_fields,
        default_fields=default_fields,
        title=display_title,
        strip_internal=strip_internal,
        add_iso_timestamps=add_iso_timestamps,
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unified "events list --type" command
# ---------------------------------------------------------------------------

_EVENT_TYPE_MAP: dict[str, tuple[str, str, list[str]]] = {
    "alert": (
        "/api/v2/events/datasearch/alert",
        "Alert Events",
        ["alert_name", "alert_type", "severity", "user", "app", "timestamp"],
    ),
    "application": (
        "/api/v2/events/datasearch/application",
        "Application Events",
        ["_id", "user", "app", "action", "type", "timestamp"],
    ),
    "network": (
        "/api/v2/events/datasearch/network",
        "Network Events",
        ["_id", "srcip", "dstip", "dstport", "action", "app", "user", "timestamp"],
    ),
    "page": (
        "/api/v2/events/datasearch/page",
        "Page Events",
        ["_id", "user", "url", "category", "action", "app", "timestamp"],
    ),
    "incident": (
        "/api/v2/events/datasearch/incident",
        "Incident Events",
        ["_id", "incident_id", "user", "severity", "status", "timestamp"],
    ),
    "infrastructure": (
        "/api/v2/events/datasearch/infrastructure",
        "Infrastructure Events",
        ["_id", "name", "status", "type", "timestamp"],
    ),
    "client-status": (
        "/api/v2/events/datasearch/clientstatus",
        "Client Status Events",
        ["_id", "device_id", "client_version", "hostname", "os", "user", "status", "timestamp"],
    ),
    "epdlp": (
        "/api/v2/events/datasearch/epdlp",
        "Endpoint DLP Events",
        ["_id", "user", "file_name", "action", "dlp_rule", "timestamp"],
    ),
    "transaction": (
        "/api/v2/events/datasearch/transaction",
        "Transaction Events",
        ["_id", "user", "app", "action", "url", "timestamp"],
    ),
}

_VALID_EVENT_TYPES = ", ".join(sorted(_EVENT_TYPE_MAP.keys())) + ", audit"


@events_app.command("list")
def events_list(
    ctx: typer.Context,
    event_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=(
            f"Event type to query. Valid values: {_VALID_EVENT_TYPES}. "
            "This is equivalent to running the individual subcommand "
            "(e.g. 'events list --type application' == 'events application')."
        ),
    ),
    query: Optional[str] = typer.Option(None, "--query", help=_HELP_QUERY),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help=_HELP_FIELDS),
    start: Optional[str] = typer.Option(None, "--start", "-s", help=_HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=_HELP_END),
    limit: int = typer.Option(25, "--limit", "-l", help=_HELP_LIMIT),
    group_by: Optional[str] = typer.Option(None, "--group-by", help=_HELP_GROUP_BY),
    order_by: Optional[str] = typer.Option(None, "--order-by", help=_HELP_ORDER_BY),
    count: bool = typer.Option(False, "--count", help="Print only the total count of matching records."),
) -> None:
    """Query events by type using a unified interface.

    A single entry point for all event types. Use --type to select which
    event category to query. Supports the same filters as individual
    event subcommands.

    Examples:
        netskope events list --type application --start 24h
        netskope events list --type alert --query 'severity eq "high"' --limit 50
        netskope events list --type network --count
    """
    normalized = event_type.lower().strip()

    if normalized == "audit":
        _run_audit_query(
            ctx,
            audit_type=None,
            fields=fields,
            start=start or "24h",
            end=end,
            limit=limit,
            group_by=group_by,
            order_by=order_by,
        )
        return

    if normalized not in _EVENT_TYPE_MAP:
        raise NetskopeError(
            f"Unknown event type '{event_type}'.",
            suggestion=f"Valid types: {_VALID_EVENT_TYPES}",
        )

    endpoint, title, default_fields = _EVENT_TYPE_MAP[normalized]

    if count:
        # Fetch minimal data just to get the total count.
        _run_event_query_with_count(ctx, endpoint, query=query, start=start, end=end)
        return

    _run_event_query(
        ctx,
        endpoint,
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title=title,
        default_fields=default_fields,
    )


def _run_event_query_with_count(
    ctx: typer.Context,
    endpoint: str,
    *,
    query: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> None:
    """Fetch and count events for an endpoint."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    quiet = state.quiet if state is not None else False
    client = _build_client(ctx)

    # Use a high limit to get an accurate count, since the events API
    # doesn't return a separate 'total' field.
    params: dict[str, Any] = {"limit": 10000}
    if query:
        params["query"] = query
    params.update(_parse_time_params(start, end))

    if not quiet:
        with spinner("Counting events...", no_color=no_color):
            data = client.request("GET", endpoint, params=params)
    else:
        data = client.request("GET", endpoint, params=params)

    if isinstance(data, dict):
        total = data.get("total")
        if total is not None:
            print(total)
            return
        result = data.get("result", [])
        print(len(result))
    else:
        print(0)


# ---------------------------------------------------------------------------
# Individual event-type subcommands
# ---------------------------------------------------------------------------


@events_app.command("alerts")
def alerts(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query alert events from the Netskope platform.

    Searches the /api/v2/events/datasearch/alert endpoint for security alert
    events such as DLP violations, malware detections, policy violations, and
    anomalous behaviour. Use JQL queries to filter by severity, alert type, user,
    or any other alert field.

    Tip: 'netskope alerts list' provides a shorthand for this command.

    Examples:
        netskope events alerts --query 'alert_type eq "DLP"' --start 24h
        netskope events alerts --query 'severity eq "high"' --limit 50 --fields timestamp,user,alert_name
        netskope -o json events alerts --start 7d --order-by "timestamp DESC"
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/alert",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Alert Events",
        default_fields=["alert_name", "alert_type", "severity", "user", "app", "timestamp"],
    )


@events_app.command("application")
def application(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query application events from the Netskope platform.

    Searches the /api/v2/events/datasearch/application endpoint for SaaS and cloud
    application activity events. Use this to monitor which cloud apps users are
    accessing, track uploads/downloads, and identify shadow IT usage.

    Examples:
        netskope events application --query 'app eq "Dropbox"' --start 24h
        netskope events application --query 'user eq "alice@example.com"' --fields app,action,timestamp
        netskope -o json events application --start 7d --group-by app
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/application",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Application Events",
        default_fields=["_id", "user", "app", "action", "type", "timestamp"],
    )


@events_app.command("network")
def network(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query network events from the Netskope platform.

    Searches the /api/v2/events/datasearch/network endpoint for network-layer
    events including firewall activity, connection logs, and traffic flow data.
    Use this to investigate network anomalies, blocked connections, and traffic
    patterns across your environment.

    Examples:
        netskope events network --query 'dstip eq "10.0.0.1"' --start 1h
        netskope events network --query 'action eq "block"' --start 24h --limit 100
        netskope -o json events network --start 7d --group-by srcip
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/network",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Network Events",
        default_fields=["_id", "srcip", "dstip", "dstport", "action", "app", "user", "timestamp"],
    )


@events_app.command("page")
def page(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query page events from the Netskope platform.

    Searches the /api/v2/events/datasearch/page endpoint for web page access
    events. Page events track user browsing activity including visited URLs,
    categories, and any policy actions taken. Use this for web activity
    monitoring and acceptable-use policy enforcement.

    Examples:
        netskope events page --query 'url_category eq "Gambling"' --start 24h
        netskope events page --query 'user eq "bob@example.com"' --fields url,category,action,timestamp
        netskope events page --start 7d --limit 200 --order-by "timestamp DESC"
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/page",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Page Events",
        default_fields=["_id", "user", "url", "category", "action", "app", "timestamp"],
    )


@events_app.command("incident")
def incident(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query incident events from the Netskope platform.

    Searches the /api/v2/events/datasearch/incident endpoint for security incident
    events. Incidents represent correlated security findings that may require
    investigation. Use this to track DLP incidents, compromised credentials, and
    other security issues that need analyst attention.

    Examples:
        netskope events incident --query 'severity eq "critical"' --start 24h
        netskope events incident --query 'status eq "open"' --fields incident_id,user,severity,timestamp
        netskope -o json events incident --start 30d --group-by severity
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/incident",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Incident Events",
        default_fields=["_id", "incident_id", "user", "severity", "status", "timestamp"],
    )


@events_app.command("audit")
def audit(
    ctx: typer.Context,
    audit_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Audit event type to filter by. Common values include 'admin' for administrator "
            "actions and 'user' for user login/logout events. This replaces --query for the "
            "audit endpoint. Omit to return all audit event types."
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        "24h",
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query audit trail events from the Netskope platform.

    Searches the /api/v2/events/data/audit endpoint for administrative audit
    trail events. Unlike other event subcommands, audit uses --type instead of
    --query for filtering. Audit events track admin actions, configuration
    changes, and user login activity. Defaults to the last 24 hours.

    Examples:
        netskope events audit --type admin --start 7d
        netskope events audit --type user --fields timestamp,user,action --limit 50
        netskope -o json events audit --start 24h --order-by "timestamp DESC"
    """
    _run_audit_query(
        ctx,
        audit_type=audit_type,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
    )


@events_app.command("infrastructure")
def infrastructure(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query infrastructure events from the Netskope platform.

    Searches the /api/v2/events/datasearch/infrastructure endpoint for
    infrastructure-level events including publisher connectivity, tunnel status,
    and platform health metrics. Use this to monitor the health and availability
    of your Netskope infrastructure components.

    Examples:
        netskope events infrastructure --start 24h --limit 50
        netskope events infrastructure --query 'status eq "down"' --fields name,status,timestamp
        netskope -o json events infrastructure --start 7d --group-by status
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/infrastructure",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Infrastructure Events",
        default_fields=["_id", "name", "status", "type", "timestamp"],
    )


@events_app.command("client-status")
def client_status(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query Netskope Client status events.

    Searches the /api/v2/events/datasearch/clientstatus endpoint for events
    related to the Netskope Client agent installed on endpoints. Use this to
    monitor client connectivity, version status, and enrollment state across
    your fleet of managed devices.

    Examples:
        netskope events client-status --start 24h --limit 100
        netskope events client-status --query 'device_os eq "Windows"' --fields user,device,status
        netskope -o json events client-status --start 7d --group-by status
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/clientstatus",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Client Status Events",
        default_fields=["_id", "device_id", "client_version", "hostname", "os", "user", "status", "timestamp"],
    )


@events_app.command("epdlp")
def epdlp(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query endpoint DLP (Data Loss Prevention) events.

    Searches the /api/v2/events/datasearch/epdlp endpoint for data loss
    prevention events detected on endpoints. These events are generated when
    the Netskope Client detects sensitive data being moved, copied, or shared
    on managed devices. Use this for endpoint-level DLP monitoring and forensics.

    Examples:
        netskope events epdlp --query 'policy eq "PCI"' --start 24h
        netskope events epdlp --start 7d --fields user,file_name,action,dlp_rule --limit 50
        netskope -o json events epdlp --start 30d --group-by dlp_rule
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/epdlp",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Endpoint DLP Events",
        default_fields=["_id", "user", "file_name", "action", "dlp_rule", "timestamp"],
    )


@events_app.command("transaction")
def transaction(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help=_HELP_QUERY,
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=_HELP_FIELDS,
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        "-s",
        help=_HELP_START,
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=_HELP_END,
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=_HELP_LIMIT,
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "--group-by",
        help=_HELP_GROUP_BY,
    ),
    order_by: Optional[str] = typer.Option(
        None,
        "--order-by",
        help=_HELP_ORDER_BY,
    ),
) -> None:
    """Query transaction events from the Netskope platform.

    Searches the /api/v2/events/datasearch/transaction endpoint for detailed
    transaction-level events. Transactions represent individual HTTP/HTTPS
    requests flowing through the Netskope proxy, providing the most granular
    view of user activity including request/response details.

    Examples:
        netskope events transaction --query 'app eq "Slack"' --start 1h
        netskope events transaction --query 'user eq "alice@example.com"' --start 24h --limit 200
        netskope -o json events transaction --start 7d --group-by app
    """
    _run_event_query(
        ctx,
        "/api/v2/events/datasearch/transaction",
        query=query,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        group_by=group_by,
        order_by=order_by,
        title="Transaction Events",
        default_fields=["_id", "user", "app", "action", "url", "timestamp"],
    )
