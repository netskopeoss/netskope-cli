"""Digital Experience Management commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/dem`` endpoints,
covering application probes, network probes, and DEM alert rules.  Use
these commands to monitor and manage the probes that measure end-user
digital experience across your Netskope-protected applications and
network paths.
"""

from __future__ import annotations

import logging
from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
dem_app = typer.Typer(
    name="dem",
    help=("Digital Experience Management — manage application probes, " "network probes, and DEM alert rules."),
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
