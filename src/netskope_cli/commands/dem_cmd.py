"""Digital Experience Management commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/dem`` endpoints,
covering application probes, network probes, and DEM alert rules.  Use
these commands to monitor and manage the probes that measure end-user
digital experience across your Netskope-protected applications and
network paths.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any, Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import ValidationError
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data source constants
# ---------------------------------------------------------------------------

QUERY_DATA_SOURCES = [
    "ux_score",
    "rum_steered",
    "rum_bypassed",
    "traceroute_pop",
    "traceroute_bypassed",
    "traceroute_all",
    "http_steered",
    "http_bypassed",
    "http_all",
    "http",
    "rum_ux_score_all",
    "rum_ux_score_steered",
    "rum_ux_score_bypassed",
    "npa_gateway",
    "npa_metric",
    "npa_stitcher",
    "agent_status",
    "client_status",
]

STATE_DATA_SOURCES = ["agent_status", "client_status"]

TRACEROUTE_DATA_SOURCES = ["traceroute_pop", "traceroute_bypassed"]

MAX_ENTITIES_WINDOW = 48 * 3600  # 48 hours in seconds

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
dem_app = typer.Typer(
    name="dem",
    help=(
        "Digital Experience Management — probes, metrics, entities, "
        "states, traceroutes, experience alerts, and monitored apps."
    ),
    no_args_is_help=True,
)

probes_app = typer.Typer(
    name="probes",
    help="Manage DEM application probes that measure end-user experience.",
    no_args_is_help=True,
)

network_probes_app = typer.Typer(
    name="network-probes",
    help="Manage DEM network probes that measure network path quality.",
    no_args_is_help=True,
)

alerts_sub_app = typer.Typer(
    name="alerts",
    help="Manage DEM alert rules for experience degradation notifications.",
    no_args_is_help=True,
)

dem_app.add_typer(probes_app, name="probes")
dem_app.add_typer(network_probes_app, name="network-probes")
dem_app.add_typer(alerts_sub_app, name="alerts")

metrics_app = typer.Typer(
    name="metrics",
    help="Query DEM experience metrics from various data sources.",
    no_args_is_help=True,
)

entities_app = typer.Typer(
    name="entities",
    help="Query DEM user/device entities with experience scores.",
    no_args_is_help=True,
)

states_app = typer.Typer(
    name="states",
    help="Query current agent or client connection states.",
    no_args_is_help=True,
)

traceroute_app = typer.Typer(
    name="traceroute",
    help="Query DEM traceroute path data.",
    no_args_is_help=True,
)

fields_app = typer.Typer(
    name="fields",
    help="List available DEM field definitions for query building.",
    no_args_is_help=True,
)

experience_alerts_app = typer.Typer(
    name="experience-alerts",
    help="Search and inspect DEM experience alerts (triggered alert instances).",
    no_args_is_help=True,
)

apps_app = typer.Typer(
    name="apps",
    help="List DEM-monitored applications.",
    no_args_is_help=True,
)

dem_app.add_typer(metrics_app, name="metrics")
dem_app.add_typer(entities_app, name="entities")
dem_app.add_typer(states_app, name="states")
dem_app.add_typer(traceroute_app, name="traceroute")
dem_app.add_typer(fields_app, name="fields")
dem_app.add_typer(experience_alerts_app, name="experience-alerts")
dem_app.add_typer(apps_app, name="apps")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an OutputFormatter respecting the current state."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from state."""
    state = ctx.obj
    return state.output.value if state is not None else "table"


def _is_quiet(ctx: typer.Context) -> bool:
    """Return whether quiet mode is enabled."""
    state = ctx.obj
    return state.quiet if state is not None else False


def _no_color(ctx: typer.Context) -> bool:
    """Return the no-color flag from global state."""
    state = ctx.obj
    return state.no_color if state is not None else False


def _parse_json_option(value: str | None, option_name: str) -> Any | None:
    """Parse a CLI option that expects a JSON string."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Invalid JSON for --{option_name}: {exc}",
            suggestion=f'Provide valid JSON. Example: --{option_name} \'["field1", "field2"]\'',
        ) from exc


def _csv_to_list(value: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, or return None."""
    if value is None:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Application Probes commands
# ---------------------------------------------------------------------------


@probes_app.command("list")
def probes_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of application probes to return. "
            "When omitted the API returns all configured probes. Use this "
            "to limit output when you have a large number of monitored apps."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of probe entries to skip before returning results. "
            "Combine with --limit to paginate through a large set of "
            "application probes."
        ),
    ),
) -> None:
    """List all DEM application probes configured in your tenant.

    Retrieves the application probes that Netskope uses to measure
    end-user digital experience when accessing SaaS applications and
    private apps.  Each probe defines a target application, the test
    type (HTTP, HTTPS, TCP), test frequency, and the set of locations
    or devices from which the tests are executed.

    Application probes help you detect latency spikes, availability
    issues, and degraded user experience before end users file support
    tickets.

    EXAMPLES

        # List all application probes
        netskope dem probes list

        # List the first 10 probes
        netskope dem probes list --limit 10

        # Paginate through probes
        netskope dem probes list --limit 50 --offset 50

        # Output as JSON for automation
        netskope -o json dem probes list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    if not _is_quiet(ctx):
        with spinner("Fetching application probes...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/dem/appprobes", params=params or None)
    else:
        result = client.request("GET", "/api/v2/dem/appprobes", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DEM Application Probes")


@probes_app.command("create")
def probes_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help=(
            "A descriptive name for the application probe. "
            "Choose a name that clearly identifies the target application "
            "and the purpose of the probe, e.g. 'Salesforce-US-East-HTTP'."
        ),
    ),
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help=(
            "The target URL or hostname to probe. "
            "This is the application endpoint that will be tested. "
            "Provide a full URL for HTTP/HTTPS probes (e.g. https://app.example.com) "
            "or a hostname:port for TCP probes."
        ),
    ),
    protocol: str = typer.Option(
        "https",
        "--protocol",
        "-p",
        help=(
            "The protocol to use for the probe test. "
            "Supported values are 'http', 'https', and 'tcp'. "
            "HTTPS is recommended for web application monitoring; use TCP "
            "for non-HTTP services like databases or custom protocols."
        ),
    ),
    interval: Optional[int] = typer.Option(
        None,
        "--interval",
        "-i",
        help=(
            "Probe execution interval in seconds. "
            "Controls how frequently the probe runs its test against the "
            "target application. Lower intervals provide faster detection "
            "but consume more resources. Typical values are 60, 300, or 900."
        ),
    ),
) -> None:
    """Create a new DEM application probe.

    Configures a new application probe that will periodically test
    connectivity, response time, and availability of the specified target
    application.  Once created, the probe begins collecting digital
    experience metrics that appear in the DEM dashboard and can trigger
    alert rules.

    Use this command when onboarding a new SaaS application that you want
    to monitor, or when you need to add visibility into a specific
    application endpoint that is critical to your users.

    EXAMPLES

        # Create an HTTPS probe for a SaaS app
        netskope dem probes create \\
            --name "Office365-Login" \\
            --target "https://login.microsoftonline.com" \\
            --protocol https

        # Create a TCP probe with a custom interval
        netskope dem probes create \\
            --name "Internal-DB" \\
            --target "db.internal.corp:5432" \\
            --protocol tcp \\
            --interval 300

        # Create and output the result as JSON
        netskope -o json dem probes create \\
            --name "GitHub-Probe" \\
            --target "https://github.com"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    data: dict[str, object] = {
        "name": name,
        "target": target,
        "protocol": protocol,
    }
    if interval is not None:
        data["interval"] = interval

    body = {"data": data}

    if not _is_quiet(ctx):
        with spinner(f"Creating application probe '{name}'...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/appprobes", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/appprobes", json_data=body)

    echo_success(f"Application probe '{name}' created.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="Created Application Probe")


# ---------------------------------------------------------------------------
# Network Probes commands
# ---------------------------------------------------------------------------


@network_probes_app.command("list")
def network_probes_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of network probes to return. "
            "When omitted the API returns all configured network probes. "
            "Use this to limit output in tenants with many monitored paths."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of network probe entries to skip before returning results. "
            "Combine with --limit for pagination when browsing a large set "
            "of network probes."
        ),
    ),
) -> None:
    """List all DEM network probes configured in your tenant.

    Retrieves the network probes that measure path quality metrics such
    as latency, jitter, and packet loss across the network segments
    between end-user devices, Netskope PoPs, and destination services.
    Network probes complement application probes by providing visibility
    into the underlying network conditions that affect user experience.

    Use this command to audit your network probe configuration or to
    export the list for documentation and compliance purposes.

    EXAMPLES

        # List all network probes
        netskope dem network-probes list

        # List the first 5 network probes
        netskope dem network-probes list --limit 5

        # Output as YAML
        netskope -o yaml dem network-probes list

        # Export as CSV for a spreadsheet
        netskope -o csv dem network-probes list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    if not _is_quiet(ctx):
        with spinner("Fetching network probes...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/dem/networkprobes", params=params or None)
    else:
        result = client.request("GET", "/api/v2/dem/networkprobes", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DEM Network Probes")


# ---------------------------------------------------------------------------
# DEM Alert Rules commands
# ---------------------------------------------------------------------------


@alerts_sub_app.command("list")
def alerts_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of alert rules to return. "
            "When omitted the API returns all configured DEM alert rules. "
            "Use this to limit output in tenants with many alert definitions."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of alert rule entries to skip before returning results. "
            "Combine with --limit for pagination when you have a large "
            "number of DEM alert rules."
        ),
    ),
) -> None:
    """List all DEM alert rules configured in your tenant.

    Retrieves the alert rules that define when DEM should generate
    notifications based on experience degradation thresholds.  Each rule
    specifies the metric to monitor (e.g. response time, packet loss),
    the threshold value, the probe or probe group it applies to, and the
    notification channels (email, webhook, SIEM).

    Use this command to audit your alerting configuration, verify that
    critical applications have alert coverage, or export rules for
    change-management documentation.

    EXAMPLES

        # List all DEM alert rules
        netskope dem alerts list

        # List the first 10 alert rules
        netskope dem alerts list --limit 10

        # Output as JSON for automation
        netskope -o json dem alerts list

        # Paginate through alert rules
        netskope dem alerts list --limit 25 --offset 25
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    if not _is_quiet(ctx):
        with spinner("Fetching DEM alert rules...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/dem/alert/rules", params=params or None)
    else:
        result = client.request("GET", "/api/v2/dem/alert/rules", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DEM Alert Rules")


@alerts_sub_app.command("create")
def alerts_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help=(
            "A descriptive name for the alert rule. "
            "Choose a name that identifies the metric, threshold, and scope, "
            "e.g. 'High-Latency-Office365' or 'PacketLoss-VPN-Gateway'."
        ),
    ),
    metric: str = typer.Option(
        ...,
        "--metric",
        "-m",
        help=(
            "The DEM metric that this alert rule monitors. "
            "Common metrics include 'response_time', 'availability', "
            "'packet_loss', and 'jitter'. The metric must match one of the "
            "metrics collected by your configured probes."
        ),
    ),
    threshold: float = typer.Option(
        ...,
        "--threshold",
        "-t",
        help=(
            "The threshold value that triggers the alert. "
            "When the monitored metric exceeds this value the alert fires. "
            "Units depend on the metric: milliseconds for response_time, "
            "percentage for packet_loss and availability."
        ),
    ),
    probe_id: Optional[str] = typer.Option(
        None,
        "--probe-id",
        "-p",
        help=(
            "The ID of the probe this alert rule applies to. "
            "When omitted, the rule applies to all probes that collect the "
            "specified metric. Use 'netskope dem probes list' to find probe IDs."
        ),
    ),
    severity: str = typer.Option(
        "medium",
        "--severity",
        "-s",
        help=(
            "The severity level assigned to alerts generated by this rule. "
            "Supported values are 'low', 'medium', 'high', and 'critical'. "
            "Severity affects how the alert is displayed in the dashboard "
            "and can be used for routing in notification integrations."
        ),
    ),
) -> None:
    """Create a new DEM alert rule for experience degradation monitoring.

    Configures a new alert rule that fires when a specified digital
    experience metric crosses the defined threshold.  Alert rules are
    evaluated continuously against the probe data collected by your DEM
    application and network probes.

    Use this command when you want to be notified proactively about
    experience issues, for example when response time to a critical SaaS
    application exceeds an acceptable level, or when packet loss on a
    key network path spikes above normal.

    EXAMPLES

        # Alert when Office 365 response time exceeds 2 seconds
        netskope dem alerts create \\
            --name "O365-Slow-Response" \\
            --metric response_time \\
            --threshold 2000 \\
            --severity high

        # Alert on packet loss for a specific probe
        netskope dem alerts create \\
            --name "VPN-PacketLoss" \\
            --metric packet_loss \\
            --threshold 5.0 \\
            --probe-id probe-abc123 \\
            --severity critical

        # Create a low-severity availability alert
        netskope -o json dem alerts create \\
            --name "App-Availability-Check" \\
            --metric availability \\
            --threshold 99.5 \\
            --severity low
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    data: dict[str, object] = {
        "name": name,
        "metric": metric,
        "threshold": threshold,
        "severity": severity,
    }
    if probe_id is not None:
        data["probe_id"] = probe_id

    body = {"data": data}

    if not _is_quiet(ctx):
        with spinner(f"Creating DEM alert rule '{name}'...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/alert/rules", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/alert/rules", json_data=body)

    echo_success(f"DEM alert rule '{name}' created.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="Created DEM Alert Rule")


# ---------------------------------------------------------------------------
# Metrics commands
# ---------------------------------------------------------------------------


@metrics_app.command("query")
def metrics_query(
    ctx: typer.Context,
    data_source: str = typer.Option(
        ...,
        "--data-source",
        "-d",
        help=(
            "Data source to query. Valid values: ux_score, rum_steered, "
            "rum_bypassed, traceroute_pop, traceroute_bypassed, traceroute_all, "
            "http_steered, http_bypassed, http_all, http, rum_ux_score_all, "
            "rum_ux_score_steered, rum_ux_score_bypassed, npa_gateway, "
            "npa_metric, npa_stitcher, agent_status, client_status."
        ),
    ),
    select: str = typer.Option(
        ...,
        "--select",
        "-s",
        help=(
            "JSON array of fields/aggregations to select. Metric fields require "
            'aggregation: \'{"alias": ["avg", "metric"]}\'. '
            'Example: \'["user_id", {"avg_score": ["avg", "score"]}]\''
        ),
    ),
    begin: int = typer.Option(
        ...,
        "--begin",
        "-b",
        help="Start time in epoch milliseconds.",
    ),
    end: int = typer.Option(
        ...,
        "--end",
        "-e",
        help="End time in epoch milliseconds.",
    ),
    where: Optional[str] = typer.Option(
        None,
        "--where",
        "-w",
        help=("JSON where clause (operator-first format). " 'Example: \'["=", "user_id", ["$", "john@example.com"]]\''),
    ),
    groupby: Optional[str] = typer.Option(
        None,
        "--groupby",
        "-g",
        help="Comma-separated list of fields to group by. Example: user_id,hostname",
    ),
    orderby: Optional[str] = typer.Option(
        None,
        "--orderby",
        help='JSON orderby clause. Example: \'[["avg_score", "asc"]]\'',
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum rows to return (max 50000)."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of rows to skip."),
) -> None:
    """Query DEM experience metrics from various data sources.

    Queries RUM, traceroute, HTTP, and UX score metrics from 17 available
    data sources.  Supports aggregation, filtering, grouping, and ordering.

    Metric fields in --select require aggregation functions with aliases:
    '{"alias": ["avg", "metric_name"]}'.  Key fields (like user_id) can
    be used directly.

    The --where clause uses operator-first format with ["$", "value"]
    for string literals.

    EXAMPLES

        # Query average UX scores per user (last 24h)
        netskope dem metrics query \\
            --data-source ux_score \\
            --select '["user_id", {"avg_score": ["avg", "score"]}]' \\
            --groupby user_id \\
            --begin 1711929600000 --end 1712016000000 \\
            --limit 25

        # Query RUM steered traffic with a where filter
        netskope dem metrics query \\
            --data-source rum_steered \\
            --select '["user_id", "application_name"]' \\
            --where '["=", "user_id", ["$", "john@example.com"]]' \\
            --begin 1711929600000 --end 1712016000000

        # Output as JSON
        netskope -o json dem metrics query \\
            --data-source ux_score \\
            --select '["user_id"]' \\
            --begin 1711929600000 --end 1712016000000
    """
    if data_source not in QUERY_DATA_SOURCES:
        raise ValidationError(
            f"Invalid data source: '{data_source}'",
            suggestion=f"Valid data sources: {', '.join(QUERY_DATA_SOURCES)}",
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    select_parsed = _parse_json_option(select, "select")
    where_parsed = _parse_json_option(where, "where")
    orderby_parsed = _parse_json_option(orderby, "orderby")
    groupby_parsed = _csv_to_list(groupby)

    body: dict[str, Any] = {"from": data_source, "select": select_parsed}
    if groupby_parsed:
        body["groupby"] = groupby_parsed
    if where_parsed is not None:
        body["where"] = where_parsed
    if orderby_parsed is not None:
        body["orderby"] = orderby_parsed
    body["begin"] = begin
    body["end"] = end
    if limit is not None:
        body["limit"] = min(limit, 50000)
    if offset is not None:
        body["offset"] = offset

    if not _is_quiet(ctx):
        with spinner(f"Querying {data_source} metrics...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/query/getdata", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/query/getdata", json_data=body)

    formatter.format_output(result, fmt=fmt, title=f"DEM Metrics — {data_source}")


# ---------------------------------------------------------------------------
# Entities commands
# ---------------------------------------------------------------------------


@entities_app.command("list")
def entities_list(
    ctx: typer.Context,
    start_time: int = typer.Option(
        ...,
        "--start-time",
        help="Start time in Unix epoch seconds.",
    ),
    end_time: int = typer.Option(
        ...,
        "--end-time",
        help="End time in Unix epoch seconds.",
    ),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Filter by user email."),
    application: Optional[str] = typer.Option(None, "--application", help="Filter by single application name."),
    applications: Optional[str] = typer.Option(
        None,
        "--applications",
        help="Comma-separated application names to filter by.",
    ),
    device_os: Optional[str] = typer.Option(
        None,
        "--device-os",
        help="Comma-separated OS filters. Valid: Windows, MacOS, Android, IOS, ChromeOS, Linux.",
    ),
    monitoring: Optional[str] = typer.Option(
        None,
        "--monitoring",
        help="Monitoring type: all, synthetic, or proactive.",
    ),
    exp_score: Optional[str] = typer.Option(
        None,
        "--exp-score",
        help="Comma-separated score ranges as 'min~max'. Example: '0~30,31~70'",
    ),
    pop: Optional[str] = typer.Option(None, "--pop", help="Comma-separated POP location codes."),
    source_ip: Optional[str] = typer.Option(None, "--source-ip", help="Filter by source IP address."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum entities to return (max 100)."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of entities to skip."),
    sort_order: Optional[str] = typer.Option(None, "--sort-order", help="Sort order: asc or desc."),
) -> None:
    """List users with experience scores and device information.

    Queries DEM user/device entities within a time window (max 48 hours).
    Returns user experience scores, device details, and location data.

    Time parameters are Unix epoch SECONDS (not milliseconds).  The
    maximum time window is 48 hours.

    EXAMPLES

        # List all entities in a 24-hour window
        netskope dem entities list \\
            --start-time 1710000000 --end-time 1710086400

        # Filter by user and score range
        netskope dem entities list \\
            --start-time 1710000000 --end-time 1710086400 \\
            --user john@example.com \\
            --exp-score '0~30'

        # Filter by application and output as JSON
        netskope -o json dem entities list \\
            --start-time 1710000000 --end-time 1710086400 \\
            --applications 'Google Gmail,Twitter' \\
            --limit 25
    """
    window = end_time - start_time
    if window > MAX_ENTITIES_WINDOW:
        raise ValidationError(
            f"Time range too large: {window / 3600:.1f} hours (max 48 hours).",
            suggestion=f"Reduce the time range. Example: --start-time {end_time - 86400} --end-time {end_time}",
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = min(limit, 100)
    if offset is not None:
        params["offset"] = offset
    if sort_order is not None:
        params["sortorder"] = sort_order

    body: dict[str, Any] = {
        "starttime": start_time,
        "endtime": end_time,
    }
    if user:
        body["user"] = user
    if application:
        body["application"] = application
    if applications:
        body["applications"] = _csv_to_list(applications)
    if device_os:
        body["deviceOs"] = _csv_to_list(device_os)
    if monitoring:
        body["monitoring"] = monitoring
    if exp_score:
        body["expScore"] = _csv_to_list(exp_score)
    if pop:
        body["pop"] = _csv_to_list(pop)
    if source_ip:
        body["sourceIp"] = source_ip

    if not _is_quiet(ctx):
        with spinner("Fetching DEM entities...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/query/getentities", params=params or None, json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/query/getentities", params=params or None, json_data=body)

    formatter.format_output(result, fmt=fmt, title="DEM Entities")


# ---------------------------------------------------------------------------
# States commands
# ---------------------------------------------------------------------------


@states_app.command("query")
def states_query(
    ctx: typer.Context,
    data_source: str = typer.Option(
        ...,
        "--data-source",
        "-d",
        help="Data source to query. Valid: agent_status, client_status.",
    ),
    select: str = typer.Option(
        ...,
        "--select",
        "-s",
        help='JSON array of fields to select. Example: \'["user_id", "status"]\'',
    ),
    where: Optional[str] = typer.Option(
        None,
        "--where",
        "-w",
        help="JSON where clause (operator-first format).",
    ),
    groupby: Optional[str] = typer.Option(
        None,
        "--groupby",
        "-g",
        help="Comma-separated list of fields to group by.",
    ),
    orderby: Optional[str] = typer.Option(
        None,
        "--orderby",
        help="JSON orderby clause.",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum rows to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of rows to skip."),
) -> None:
    """Query current agent or client connection states.

    Queries current device/agent state — does NOT accept time ranges.
    Only 'agent_status' and 'client_status' data sources are valid.

    EXAMPLES

        # List all connected agents
        netskope dem states query \\
            --data-source agent_status \\
            --select '["user_id", "status", "agent_version"]' \\
            --limit 100

        # Query client status with a filter
        netskope dem states query \\
            --data-source client_status \\
            --select '["user_id"]' \\
            --where '["=", "user_id", ["$", "john@example.com"]]'
    """
    if data_source not in STATE_DATA_SOURCES:
        raise ValidationError(
            f"Invalid data source for states: '{data_source}'",
            suggestion=f"Only {', '.join(STATE_DATA_SOURCES)} are valid. "
            f"Use 'dem metrics query' for other data sources.",
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    select_parsed = _parse_json_option(select, "select")
    where_parsed = _parse_json_option(where, "where")
    orderby_parsed = _parse_json_option(orderby, "orderby")
    groupby_parsed = _csv_to_list(groupby)

    body: dict[str, Any] = {"from": data_source, "select": select_parsed}
    if groupby_parsed:
        body["groupby"] = groupby_parsed
    if where_parsed is not None:
        body["where"] = where_parsed
    if orderby_parsed is not None:
        body["orderby"] = orderby_parsed
    if limit is not None:
        body["limit"] = limit
    if offset is not None:
        body["offset"] = offset

    if not _is_quiet(ctx):
        with spinner(f"Querying {data_source} states...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/query/getstates", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/query/getstates", json_data=body)

    formatter.format_output(result, fmt=fmt, title=f"DEM States — {data_source}")


# ---------------------------------------------------------------------------
# Traceroute commands
# ---------------------------------------------------------------------------


@traceroute_app.command("query")
def traceroute_query(
    ctx: typer.Context,
    data_source: str = typer.Option(
        ...,
        "--data-source",
        "-d",
        help="Data source. Valid: traceroute_pop, traceroute_bypassed.",
    ),
    begin: int = typer.Option(
        ...,
        "--begin",
        "-b",
        help="Start time in epoch milliseconds.",
    ),
    end: int = typer.Option(
        ...,
        "--end",
        "-e",
        help="End time in epoch milliseconds.",
    ),
    where: Optional[str] = typer.Option(
        None,
        "--where",
        "-w",
        help="JSON where clause (operator-first format).",
    ),
    orderby: Optional[str] = typer.Option(
        None,
        "--orderby",
        help="JSON orderby clause.",
    ),
) -> None:
    """Query DEM traceroute network path data.

    Returns hop-by-hop network path graph data.  The traceroute API does
    NOT support a limit parameter; use --where filters and short time
    ranges to control response size.

    EXAMPLES

        # Query traceroute data for a specific user
        netskope dem traceroute query \\
            --data-source traceroute_pop \\
            --where '["=", "user_id", ["$", "john@example.com"]]' \\
            --begin 1711929600000 --end 1712016000000

        # Query bypassed traceroute data
        netskope -o json dem traceroute query \\
            --data-source traceroute_bypassed \\
            --begin 1711929600000 --end 1712016000000
    """
    if data_source not in TRACEROUTE_DATA_SOURCES:
        raise ValidationError(
            f"Invalid data source for traceroute: '{data_source}'",
            suggestion=f"Only {', '.join(TRACEROUTE_DATA_SOURCES)} are valid.",
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    where_parsed = _parse_json_option(where, "where")
    orderby_parsed = _parse_json_option(orderby, "orderby")

    body: dict[str, Any] = {"from": data_source, "begin": begin, "end": end}
    if where_parsed is not None:
        body["where"] = where_parsed
    if orderby_parsed is not None:
        body["orderby"] = orderby_parsed

    if not _is_quiet(ctx):
        with spinner(f"Querying {data_source} traceroute...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/query/gettraceroute", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/query/gettraceroute", json_data=body)

    formatter.format_output(result, fmt=fmt, title=f"DEM Traceroute — {data_source}")


# ---------------------------------------------------------------------------
# Fields commands
# ---------------------------------------------------------------------------


@fields_app.command("list")
def fields_list(
    ctx: typer.Context,
    source: Optional[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Optional data source to filter definitions. If omitted, returns all.",
    ),
) -> None:
    """List available DEM field definitions for query building.

    Discover which fields, metrics, and aggregation functions are
    available for each data source.  Use this before constructing
    metrics queries to find the correct field names.

    EXAMPLES

        # List all field definitions
        netskope dem fields list

        # List fields for a specific data source
        netskope dem fields list --source rum_steered

        # Output as JSON
        netskope -o json dem fields list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, str] = {}
    if source:
        params["source"] = source

    if not _is_quiet(ctx):
        with spinner("Fetching field definitions...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/dem/query/definitions", params=params or None)
    else:
        result = client.request("GET", "/api/v2/dem/query/definitions", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DEM Field Definitions")


# ---------------------------------------------------------------------------
# Experience Alerts commands (triggered alert instances)
# ---------------------------------------------------------------------------


@experience_alerts_app.command("search")
def experience_alerts_search(
    ctx: typer.Context,
    alert_category: Optional[str] = typer.Option(
        None,
        "--alert-category",
        help="Comma-separated alert categories: Network, Platform, Private Apps, User Experience, Site.",
    ),
    alert_type: Optional[str] = typer.Option(
        None,
        "--alert-type",
        help="Comma-separated alert types: Tunnel Status, Experience Score, etc.",
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help="Comma-separated severities: info, low, medium, high, critical.",
    ),
    open_time: Optional[int] = typer.Option(
        None,
        "--open-time",
        help="Filter alerts opened after this Unix epoch second.",
    ),
    sort_field: Optional[str] = typer.Option(None, "--sort-field", help="Field name to sort by."),
    sort_desc: bool = typer.Option(True, "--sort-desc/--sort-asc", help="Sort descending (default) or ascending."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum alerts to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of alerts to skip."),
) -> None:
    """Search DEM experience alerts with filters.

    Searches triggered DEM alert instances (not alert rules).  Filter by
    category, type, and severity to find active or historical alerts.

    NOTE: This searches alert instances.  To manage alert rules
    (create/list), use 'netskope dem alerts' instead.

    EXAMPLES

        # Search for critical and high severity alerts
        netskope dem experience-alerts search \\
            --severity critical,high --limit 10

        # Search by category
        netskope dem experience-alerts search \\
            --alert-category 'Network,User Experience'

        # Output as JSON sorted ascending
        netskope -o json dem experience-alerts search \\
            --severity critical --sort-asc
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body: dict[str, Any] = {}
    category_list = _csv_to_list(alert_category)
    if category_list:
        body["alertCategory"] = category_list
    type_list = _csv_to_list(alert_type)
    if type_list:
        body["alertType"] = type_list
    severity_list = _csv_to_list(severity)
    if severity_list:
        body["severity"] = severity_list
    if limit is not None:
        body["limit"] = limit
    else:
        body["limit"] = 10
    if offset is not None:
        body["offset"] = offset
    if open_time is not None:
        body["openTime"] = open_time
    if sort_field:
        body["sortBy"] = {"field": sort_field, "desc": sort_desc}

    if not _is_quiet(ctx):
        with spinner("Searching DEM experience alerts...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/dem/alerts/getalerts", json_data=body)
    else:
        result = client.request("POST", "/api/v2/dem/alerts/getalerts", json_data=body)

    formatter.format_output(result, fmt=fmt, title="DEM Experience Alerts")


@experience_alerts_app.command("get")
def experience_alerts_get(
    ctx: typer.Context,
    alert_id: str = typer.Argument(..., help="The alert ID to retrieve."),
) -> None:
    """Get full details for a specific DEM experience alert.

    Retrieves detailed information about a triggered alert instance
    including its category, severity, affected metrics, and timeline.

    Use 'netskope dem experience-alerts search' to find alert IDs.

    EXAMPLES

        # Get alert details
        netskope dem experience-alerts get abc123

        # Output as JSON
        netskope -o json dem experience-alerts get abc123
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if not _is_quiet(ctx):
        with spinner(f"Fetching alert {alert_id}...", no_color=_no_color(ctx)):
            result = client.request("GET", f"/api/v2/dem/alerts/{urllib.parse.quote(alert_id, safe='')}")
    else:
        result = client.request("GET", f"/api/v2/dem/alerts/{urllib.parse.quote(alert_id, safe='')}")

    formatter.format_output(result, fmt=fmt, title=f"DEM Alert — {alert_id}")


@experience_alerts_app.command("entities")
def experience_alerts_entities(
    ctx: typer.Context,
    alert_id: str = typer.Argument(..., help="The alert ID whose impacted entities to list."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum entities to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of entities to skip."),
    sortby: Optional[str] = typer.Option(None, "--sortby", help="Field to sort by."),
    sort_order: Optional[str] = typer.Option(None, "--sort-order", help="Sort order: asc or desc."),
) -> None:
    """Get users and devices impacted by a DEM alert.

    Lists the entities (users, devices) affected by a specific
    triggered alert instance.

    EXAMPLES

        # List impacted entities
        netskope dem experience-alerts entities abc123

        # With pagination
        netskope dem experience-alerts entities abc123 --limit 25 --offset 0

        # Output as JSON
        netskope -o json dem experience-alerts entities abc123
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if sortby:
        params["sortby"] = sortby
    if sort_order:
        params["sortorder"] = sort_order

    alert_path = f"/api/v2/dem/alerts/{urllib.parse.quote(alert_id, safe='')}/entities"

    if not _is_quiet(ctx):
        with spinner(f"Fetching entities for alert {alert_id}...", no_color=_no_color(ctx)):
            result = client.request("GET", alert_path, params=params or None)
    else:
        result = client.request("GET", alert_path, params=params or None)

    formatter.format_output(result, fmt=fmt, title=f"DEM Alert Entities — {alert_id}")


# ---------------------------------------------------------------------------
# Monitored Apps commands
# ---------------------------------------------------------------------------


@apps_app.command("list")
def apps_list(
    ctx: typer.Context,
    app_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by app type: custom or predefined.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Filter by application name.",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum apps to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of apps to skip."),
) -> None:
    """List applications monitored by DEM.

    Retrieves the applications that DEM is actively monitoring,
    including both predefined (built-in) and custom applications.

    EXAMPLES

        # List all monitored apps
        netskope dem apps list

        # List only predefined apps
        netskope dem apps list --type predefined

        # Search by name
        netskope dem apps list --name Gmail

        # Output as JSON with limit
        netskope -o json dem apps list --limit 50
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, Any] = {}
    if app_type:
        params["type"] = app_type
    if name:
        params["name"] = name
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    if not _is_quiet(ctx):
        with spinner("Fetching monitored apps...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/dem/apps", params=params or None)
    else:
        result = client.request("GET", "/api/v2/dem/apps", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DEM Monitored Apps")
