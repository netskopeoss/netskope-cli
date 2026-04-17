"""ADEM user/device telemetry commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/adem/users``
endpoints, covering per-user and per-device digital experience telemetry
including device health (CPU, memory, disk), network metrics, experience
scores, root cause analysis, and traceroute data.
"""

from __future__ import annotations

import logging
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_warning, spinner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------

adem_users_app = typer.Typer(
    name="users",
    help=(
        "ADEM user/device telemetry — device health, experience scores, "
        "root cause analysis, network metrics, and traceroutes."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    state = ctx.obj
    return state.output.value if state is not None else "table"


def _is_quiet(ctx: typer.Context) -> bool:
    state = ctx.obj
    return state.quiet if state is not None else False


def _no_color(ctx: typer.Context) -> bool:
    state = ctx.obj
    return state.no_color if state is not None else False


def _build_user_body(
    start_time: int,
    end_time: int,
    user: str | None = None,
    device_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the common ADEM request body."""
    body: dict[str, Any] = {"starttime": start_time, "endtime": end_time}
    if user is not None:
        body["user"] = user
    if device_id is not None:
        body["deviceId"] = device_id
    body.update(extra)
    return body


# ---------------------------------------------------------------------------
# devices — /api/v2/adem/users/device/getlist
# ---------------------------------------------------------------------------


@adem_users_app.command("devices")
def users_devices(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
) -> None:
    """List devices for a user with experience scores.

    Returns device IDs, names, operating systems, and experience scores
    for the specified user within the given time window.  Use the device
    ID from this output as the ``--device-id`` parameter for other
    ``dem users`` commands.

    EXAMPLES

        netskope dem users devices \\
            --user alice@example.com \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users devices \\
            --user alice@example.com \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, userLocation=[])

    if not _is_quiet(ctx):
        with spinner("Fetching user devices...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/getlist", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/getlist", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM User Devices")


# ---------------------------------------------------------------------------
# device-details — /api/v2/adem/users/device/getdetails
# ---------------------------------------------------------------------------


@adem_users_app.command("device-details")
def users_device_details(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """Get detailed device information including hardware, software, and location.

    Returns comprehensive device data: client status and version, CPU and
    memory specs, device classification (managed/unmanaged), OS, geographic
    location (city/country/coordinates), gateway, POP, public and private
    IPs, and NPA connectivity details.

    EXAMPLES

        netskope dem users device-details \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users device-details \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching device details...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/getdetails", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/getdetails", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Device Details")


# ---------------------------------------------------------------------------
# info — /api/v2/adem/users/getinfo
# ---------------------------------------------------------------------------


@adem_users_app.command("info")
def users_info(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
) -> None:
    """Get user info summary including experience score and location.

    Returns the user's device list, overall experience score, last
    activity timestamp, and location (city, country, coordinates).

    EXAMPLES

        netskope dem users info \\
            --user alice@example.com \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user)

    if not _is_quiet(ctx):
        with spinner("Fetching user info...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/getinfo", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/getinfo", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM User Info")


# ---------------------------------------------------------------------------
# applications — /api/v2/adem/users/getapplications
# ---------------------------------------------------------------------------


@adem_users_app.command("applications")
def users_applications(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """List applications on a device with per-app experience scores.

    Returns every application accessed on the specified device within the
    time window, with each app's average experience score.  Use this to
    identify which applications are causing poor digital experience.

    ``--device-id`` is required: without it the API returns only a 1-2 app
    subset instead of the full per-device list.  Run ``dem users devices``
    first to enumerate device IDs for the user.

    EXAMPLES

        netskope dem users applications \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users applications \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching user applications...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/getapplications", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/getapplications", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM User Applications")


# ---------------------------------------------------------------------------
# locations — /api/v2/adem/users/getlocations
# ---------------------------------------------------------------------------


@adem_users_app.command("locations")
def users_locations(
    ctx: typer.Context,
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
) -> None:
    """Get all user locations.

    Returns an array of locations with city, country, and geographic
    coordinates for all users within the given time window.

    EXAMPLES

        netskope dem users locations \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users locations \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time)

    if not _is_quiet(ctx):
        with spinner("Fetching user locations...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/getlocations", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/getlocations", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM User Locations")


# ---------------------------------------------------------------------------
# scores — /api/v2/adem/users/device/getaggregatedscores
# ---------------------------------------------------------------------------


@adem_users_app.command("scores")
def users_scores(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
    aggregation_type: str = typer.Option(
        "avg",
        "--aggregation-type",
        help="Aggregation type: avg, min, or max.",
    ),
) -> None:
    """Get aggregated experience scores for a device.

    Returns aggregated scores across five dimensions: application,
    device, experience, network, and NPA host.

    EXAMPLES

        netskope dem users scores \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users scores \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400 \\
            --aggregation-type min
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id, aggregationType=aggregation_type)

    if not _is_quiet(ctx):
        with spinner("Fetching aggregated scores...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/getaggregatedscores", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/getaggregatedscores", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Aggregated Scores")


# ---------------------------------------------------------------------------
# exp-score — /api/v2/adem/users/metrics/getexpscore
# ---------------------------------------------------------------------------


@adem_users_app.command("exp-score")
def users_exp_score(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """Get experience score timeseries for a device.

    Returns time-series experience score data points for the specified
    user and device within the given time window.

    EXAMPLES

        netskope dem users exp-score \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching experience scores...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/metrics/getexpscore", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/metrics/getexpscore", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Experience Score")


# ---------------------------------------------------------------------------
# rca — /api/v2/adem/users/device/getrca
# ---------------------------------------------------------------------------


@adem_users_app.command("rca")
def users_rca(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """Root cause analysis for a device — CPU, memory, and disk telemetry.

    Returns detailed device health data including CPU utilization and
    top processes, disk usage and utilization, and memory scores.  This
    is the primary command for investigating device performance issues.

    EXAMPLES

        netskope dem users rca \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users rca \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching root cause analysis...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/getrca", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/getrca", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Root Cause Analysis")


# ---------------------------------------------------------------------------
# network — /api/v2/adem/users/metrics/getnetwork
# ---------------------------------------------------------------------------


@adem_users_app.command("network")
def users_network(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
    metric_type: str = typer.Option(
        "all",
        "--metric-type",
        help="Metric type to retrieve (default: all).",
    ),
) -> None:
    """Get network metrics timeseries for a device.

    Returns latency and packet loss time-series data for the specified
    user and device within the given time window.

    EXAMPLES

        netskope dem users network \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users network \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400 \\
            --metric-type all
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id, metricType=metric_type)

    if not _is_quiet(ctx):
        with spinner("Fetching network metrics...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/metrics/getnetwork", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/metrics/getnetwork", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Network Metrics")


# ---------------------------------------------------------------------------
# npa-hosts — /api/v2/adem/users/npa/getnpahosts
# ---------------------------------------------------------------------------


@adem_users_app.command("npa-hosts")
def users_npa_hosts(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """Get NPA hosts for a user and device.

    Returns Netskope Private Access hosts with experience scores,
    applications, host IPs, and ports for the specified user and device.

    EXAMPLES

        netskope dem users npa-hosts \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching NPA hosts...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/npa/getnpahosts", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/npa/getnpahosts", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM NPA Hosts")


# ---------------------------------------------------------------------------
# npa-network-paths — /api/v2/adem/users/npa/getnetworkpaths
# ---------------------------------------------------------------------------


@adem_users_app.command("npa-network-paths")
def users_npa_network_paths(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
    npa_host: str = typer.Option(..., "--npa-host", help="NPA host IP or hostname (from 'dem users npa-hosts')."),
) -> None:
    """Get NPA network path graph for a specific host.

    Returns the network path between the user's device and an NPA host
    as a graph of nodes and edges.  Nodes represent network elements
    (DEVICE, GATEWAY, STITCHER, PUBLISHER, HOST) with location data.
    Edges carry average and median latency plus session counts.

    Use ``dem users npa-hosts`` first to discover available NPA hosts,
    then pass the host IP to ``--npa-host``.

    EXAMPLES

        netskope dem users npa-network-paths \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --npa-host 10.100.12.4 \\
            --start-time 1710000000 --end-time 1710086400

        netskope -o json dem users npa-network-paths \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --npa-host 10.100.12.4 \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id, npaHost=npa_host)

    if not _is_quiet(ctx):
        with spinner("Fetching NPA network paths...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/npa/getnetworkpaths", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/npa/getnetworkpaths", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM NPA Network Paths")


# ---------------------------------------------------------------------------
# traceroute-ts — /api/v2/adem/users/device/gettraceroutetimestamps
# ---------------------------------------------------------------------------


@adem_users_app.command("traceroute-ts")
def users_traceroute_ts(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """List available traceroute timestamps for a device.

    Returns an array of timestamps at which traceroute data is available.
    Use these timestamps with ``dem users traceroute`` to fetch the
    detailed path data for a specific point in time.

    EXAMPLES

        netskope dem users traceroute-ts \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching traceroute timestamps...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/gettraceroutetimestamps", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/gettraceroutetimestamps", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Traceroute Timestamps")


# ---------------------------------------------------------------------------
# traceroute — /api/v2/adem/users/device/gettraceroute
# ---------------------------------------------------------------------------


@adem_users_app.command("traceroute")
def users_traceroute(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(..., "--device-id", "-d", help="Device ID (from 'dem users devices')."),
) -> None:
    """Get detailed traceroute path data for a device.

    Returns hop-by-hop network path data including latencies, ASN info,
    device details, and geographic location.  Use ``dem users traceroute-ts``
    first to find available timestamps, then pass a specific timestamp as
    both ``--start-time`` and ``--end-time``.

    EXAMPLES

        # Get traceroute for a specific timestamp
        netskope dem users traceroute \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710050000 --end-time 1710050000

        netskope -o json dem users traceroute \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710050000 --end-time 1710050000
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = _build_user_body(start_time, end_time, user=user, device_id=device_id)

    if not _is_quiet(ctx):
        with spinner("Fetching traceroute data...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/adem/users/device/gettraceroute", json_data=body)
    else:
        result = client.request("POST", "/api/v2/adem/users/device/gettraceroute", json_data=body)

    formatter.format_output(result, fmt=fmt, title="ADEM Traceroute")


# ---------------------------------------------------------------------------
# diagnose — composite command (multiple API calls)
# ---------------------------------------------------------------------------


def _safe_request(
    client: NetskopeClient,
    method: str,
    path: str,
    *,
    json_data: dict[str, Any] | None = None,
    label: str = "",
    no_color: bool = False,
) -> Any:
    """Make an API request, returning *None* on failure instead of raising."""
    try:
        return client.request(method, path, json_data=json_data)
    except Exception as exc:  # noqa: BLE001
        echo_warning(f"{label or path}: {exc}", no_color=no_color)
        return None


def _score_style(score: Any) -> str:
    """Return a Rich style string for a 0-100 score."""
    if not isinstance(score, (int, float)):
        return "dim"
    if score < 30:
        return "bold red"
    if score < 70:
        return "bold yellow"
    return "bold green"


def _render_diagnose(diag: dict[str, Any], no_color: bool = False) -> None:
    """Render the diagnostic report as a Rich dashboard."""
    console = Console(no_color=no_color, stderr=True)

    # --- User info header ---
    user_info = diag.get("user_info") or {}
    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()

    header.add_row("User", Text(str(user_info.get("user", "N/A")), style="bold cyan"))
    exp = user_info.get("expScore")
    header.add_row("Experience Score", Text(str(exp) if exp is not None else "N/A", style=_score_style(exp)))
    header.add_row("Location", Text(str(user_info.get("lastKnownLocation", "N/A"))))
    header.add_row("Org Unit", Text(str(user_info.get("organizationUnit", "N/A"))))
    header.add_row("User Group", Text(str(user_info.get("userGroup", "N/A"))))

    console.print(Panel(header, title="[bold]User Summary[/bold]", border_style="blue", expand=False, padding=(1, 2)))

    # --- Per-device sections ---
    for dev in diag.get("devices", []):
        details = dev.get("details") or {}
        scores_data = dev.get("scores") or {}
        metrics = scores_data.get("metrics", scores_data)
        rca = dev.get("rca")

        dev_name = details.get("deviceName") or dev.get("device_id", "Unknown")
        dev_os = details.get("deviceOs", "")
        client_ver = details.get("clientVersion", "")
        geo = details.get("geo") or {}
        geo_str = ", ".join(filter(None, [geo.get("city"), geo.get("region"), geo.get("country")]))

        # Device info grid
        dev_grid = Table.grid(padding=(0, 2))
        dev_grid.add_column()
        dev_grid.add_column()
        dev_grid.add_row("Device ID", Text(str(dev.get("device_id", "N/A")), style="dim"))
        if dev_os:
            dev_grid.add_row("OS", Text(dev_os))
        if client_ver:
            dev_grid.add_row("Client Version", Text(client_ver))
        if details.get("clientStatus"):
            dev_grid.add_row("Client Status", Text(details["clientStatus"]))
        if geo_str:
            dev_grid.add_row("Location", Text(geo_str))
        if details.get("publicIp"):
            dev_grid.add_row("Public IP", Text(details["publicIp"]))
        if details.get("pop"):
            dev_grid.add_row("POP", Text(details["pop"]))

        # Scores table
        scores_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
        scores_table.add_column("Dimension", style="bold", min_width=16)
        scores_table.add_column("Score", justify="right")
        score_labels = [
            ("expScore", "Experience"),
            ("deviceScore", "Device"),
            ("networkScore", "Network"),
            ("appScore", "Application"),
            ("npaHostScore", "NPA Host"),
        ]
        for key, label in score_labels:
            sc = metrics.get(key)
            scores_table.add_row(label, Text(str(sc) if sc is not None else "N/A", style=_score_style(sc)))

        # RCA highlights
        rca_lines: list[Text] = []
        if rca and isinstance(rca, dict):
            for category_key, category_data in rca.items():
                if not isinstance(category_data, dict):
                    continue
                cat_score = category_data.get("score")
                if cat_score is not None and isinstance(cat_score, (int, float)) and cat_score < 70:
                    line = Text()
                    line.append(f"  {category_key}: ", style="bold")
                    line.append(f"score {cat_score}", style=_score_style(cat_score))
                    util = category_data.get("utilization")
                    if util is not None:
                        line.append(f"  (utilization: {util}%)")
                    rca_lines.append(line)

        # Assemble device panel
        dev_output = Table.grid(padding=(1, 0))
        dev_output.add_row(dev_grid)
        dev_output.add_row(Text("Scores", style="bold magenta"))
        dev_output.add_row(scores_table)

        # Applications on this device
        apps = dev.get("applications")
        if apps is not None:
            app_list = apps if isinstance(apps, list) else apps.get("applications", apps.get("data", []))
            if isinstance(app_list, list) and app_list:
                app_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
                app_table.add_column("Application", style="bold", min_width=24)
                app_table.add_column("Score", justify="right")
                for a in app_list:
                    name = a.get("appName") or a.get("applicationName") or a.get("name", "?")
                    sc = a.get("expScore") or a.get("score")
                    app_table.add_row(str(name), Text(str(sc) if sc is not None else "N/A", style=_score_style(sc)))
                dev_output.add_row(Text("Applications", style="bold magenta"))
                dev_output.add_row(app_table)

        if rca_lines:
            dev_output.add_row(Text("RCA Issues", style="bold magenta"))
            for line in rca_lines:
                dev_output.add_row(line)

        # NPA section
        npa = dev.get("npa")
        if npa:
            hosts = npa.get("hosts") or {}
            host_list = hosts.get("npaHosts", hosts) if isinstance(hosts, dict) else hosts
            if host_list and isinstance(host_list, list):
                npa_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
                npa_table.add_column("NPA Host", style="bold", min_width=16)
                npa_table.add_column("Score", justify="right")
                npa_table.add_column("Applications")
                for h in host_list:
                    sc = h.get("expScore")
                    apps_list = h.get("npaApplications", [])
                    apps_str = ", ".join(str(a) for a in apps_list[:3])
                    if len(apps_list) > 3:
                        apps_str += f" (+{len(apps_list) - 3} more)"
                    npa_table.add_row(
                        str(h.get("npaHost", "?")),
                        Text(str(sc) if sc is not None else "N/A", style=_score_style(sc)),
                        apps_str,
                    )
                dev_output.add_row(Text("NPA Hosts", style="bold magenta"))
                dev_output.add_row(npa_table)

        title = f"[bold]Device: {dev_name}[/bold]"
        if dev_os:
            title += f" [dim]({dev_os})[/dim]"
        console.print(Panel(dev_output, title=title, border_style="blue", expand=False, padding=(1, 2)))


@adem_users_app.command("diagnose")
def users_diagnose(
    ctx: typer.Context,
    user: str = typer.Option(..., "--user", "-u", help="User email address."),
    start_time: int = typer.Option(..., "--start-time", help="Start time in Unix epoch seconds."),
    end_time: int = typer.Option(..., "--end-time", help="End time in Unix epoch seconds."),
    device_id: str = typer.Option(None, "--device-id", "-d", help="Specific device ID (default: all devices)."),
    application: str = typer.Option(None, "--application", "-a", help="Application name to focus on."),
    include_npa: bool = typer.Option(False, "--include-npa", help="Include NPA host and network path analysis."),
) -> None:
    """One-shot diagnostic report for a user's digital experience.

    Combines multiple ADEM API calls into a single diagnostic view.
    Given a user email and time range (from a support ticket), this
    command gathers user info, applications, device details, aggregated
    scores, and root cause analysis to surface performance issues.

    Without ``--device-id``, automatically discovers all devices for the
    user and reports on each.  Use ``--application`` to highlight a
    specific application.  Use ``--include-npa`` to add NPA host and
    network path analysis (adds extra API calls).

    EXAMPLES

        # Basic diagnosis from ticket info
        netskope dem users diagnose \\
            --user alice@example.com \\
            --start-time 1710000000 --end-time 1710086400

        # Diagnose a specific device with NPA analysis
        netskope dem users diagnose \\
            --user alice@example.com \\
            --device-id DEVICE-UUID \\
            --start-time 1710000000 --end-time 1710086400 \\
            --include-npa

        # Focus on a specific application (JSON output)
        netskope -o json dem users diagnose \\
            --user alice@example.com \\
            --start-time 1710000000 --end-time 1710086400 \\
            --application "Google Gmail"
    """
    client = _build_client(ctx)
    fmt = _get_output_format(ctx)
    quiet = _is_quiet(ctx)
    no_color = _no_color(ctx)

    base_body = _build_user_body(start_time, end_time, user=user)
    diag: dict[str, Any] = {"user_info": None, "devices": []}

    # Phase 1 — user-level data
    if not quiet:
        with spinner("Fetching user info...", no_color=no_color):
            diag["user_info"] = _safe_request(
                client, "POST", "/api/v2/adem/users/getinfo", json_data=base_body, label="getinfo", no_color=no_color
            )
    else:
        diag["user_info"] = _safe_request(
            client, "POST", "/api/v2/adem/users/getinfo", json_data=base_body, label="getinfo", no_color=no_color
        )

    # Resolve device list
    if device_id is not None:
        device_ids = [device_id]
    else:
        devices_body = _build_user_body(start_time, end_time, user=user, userLocation=[])
        device_list_result = _safe_request(
            client,
            "POST",
            "/api/v2/adem/users/device/getlist",
            json_data=devices_body,
            label="device/getlist",
            no_color=no_color,
        )
        if device_list_result is None:
            device_ids = []
        elif isinstance(device_list_result, list):
            device_ids = [d.get("deviceId") for d in device_list_result if d.get("deviceId")]
        else:
            items = device_list_result.get("data", device_list_result.get("devices", []))
            device_ids = [d.get("deviceId") for d in items if d.get("deviceId")]

    # Phase 2 — per-device data
    for did in device_ids:
        dev_body = _build_user_body(start_time, end_time, user=user, device_id=did)
        dev_entry: dict[str, Any] = {"device_id": did}

        if not quiet:
            with spinner(f"Fetching device data ({did[:12]}...)...", no_color=no_color):
                dev_entry["details"] = _safe_request(
                    client,
                    "POST",
                    "/api/v2/adem/users/device/getdetails",
                    json_data=dev_body,
                    label="device/getdetails",
                    no_color=no_color,
                )
                dev_entry["applications"] = _safe_request(
                    client,
                    "POST",
                    "/api/v2/adem/users/getapplications",
                    json_data=dev_body,
                    label="getapplications",
                    no_color=no_color,
                )
                dev_entry["scores"] = _safe_request(
                    client,
                    "POST",
                    "/api/v2/adem/users/device/getaggregatedscores",
                    json_data={**dev_body, "aggregationType": "avg"},
                    label="device/getaggregatedscores",
                    no_color=no_color,
                )
                dev_entry["rca"] = _safe_request(
                    client,
                    "POST",
                    "/api/v2/adem/users/device/getrca",
                    json_data=dev_body,
                    label="device/getrca",
                    no_color=no_color,
                )
        else:
            dev_entry["details"] = _safe_request(
                client,
                "POST",
                "/api/v2/adem/users/device/getdetails",
                json_data=dev_body,
                label="device/getdetails",
                no_color=no_color,
            )
            dev_entry["applications"] = _safe_request(
                client,
                "POST",
                "/api/v2/adem/users/getapplications",
                json_data=dev_body,
                label="getapplications",
                no_color=no_color,
            )
            dev_entry["scores"] = _safe_request(
                client,
                "POST",
                "/api/v2/adem/users/device/getaggregatedscores",
                json_data={**dev_body, "aggregationType": "avg"},
                label="device/getaggregatedscores",
                no_color=no_color,
            )
            dev_entry["rca"] = _safe_request(
                client,
                "POST",
                "/api/v2/adem/users/device/getrca",
                json_data=dev_body,
                label="device/getrca",
                no_color=no_color,
            )

        # Phase 3 — NPA (optional)
        if include_npa:
            npa_data: dict[str, Any] = {}
            npa_data["hosts"] = _safe_request(
                client,
                "POST",
                "/api/v2/adem/users/npa/getnpahosts",
                json_data=dev_body,
                label="npa/getnpahosts",
                no_color=no_color,
            )
            npa_hosts_result = npa_data["hosts"]
            npa_host_list = []
            if npa_hosts_result:
                if isinstance(npa_hosts_result, dict):
                    npa_host_list = npa_hosts_result.get("npaHosts", [])
                elif isinstance(npa_hosts_result, list):
                    npa_host_list = npa_hosts_result

            paths = []
            for h in npa_host_list:
                host_ip = h.get("npaHost")
                if host_ip:
                    path_body = _build_user_body(start_time, end_time, user=user, device_id=did, npaHost=host_ip)
                    path_result = _safe_request(
                        client,
                        "POST",
                        "/api/v2/adem/users/npa/getnetworkpaths",
                        json_data=path_body,
                        label=f"npa/getnetworkpaths ({host_ip})",
                        no_color=no_color,
                    )
                    if path_result:
                        paths.append({"npaHost": host_ip, "path": path_result})
            npa_data["network_paths"] = paths
            dev_entry["npa"] = npa_data

        diag["devices"].append(dev_entry)

    # Filter by application if specified
    if application:
        needle = application.lower()
        for dev_entry in diag["devices"]:
            app_data = dev_entry.get("applications")
            if not app_data:
                continue
            app_items: Any
            if isinstance(app_data, list):
                app_items = app_data
            elif isinstance(app_data, dict):
                app_items = app_data.get("applications", app_data.get("data", []))
            else:
                continue
            if not isinstance(app_items, list):
                continue
            filtered = [
                a
                for a in app_items
                if needle in str(a.get("appName", a.get("applicationName", a.get("name", "")))).lower()
            ]
            if filtered:
                dev_entry["applications"] = filtered

    # Render output
    if fmt in ("json", "jsonl", "csv", "yaml"):
        formatter = _get_formatter(ctx)
        formatter.format_output(diag, fmt=fmt, title="ADEM Diagnosis", unwrap=False)
    else:
        _render_diagnose(diag, no_color=no_color)
