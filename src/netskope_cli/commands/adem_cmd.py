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

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, spinner

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
