"""Intrusion Prevention System commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/ips`` endpoints,
covering IPS feature status, IP allowlist management, and signature
reference listing.  Use these commands to monitor and configure the
network-level threat prevention capabilities of your Netskope tenant.
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
ips_app = typer.Typer(
    name="ips",
    help=("Intrusion Prevention System — view IPS status, manage IP allowlists, " "and browse signature references."),
    no_args_is_help=True,
)

allowlist_app = typer.Typer(
    name="allowlist",
    help="Manage the IPS IP allowlist — list and add trusted IP addresses.",
    no_args_is_help=True,
)

ips_app.add_typer(allowlist_app, name="allowlist")


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
# IPS status command
# ---------------------------------------------------------------------------


@ips_app.command("status")
def status(
    ctx: typer.Context,
) -> None:
    """Show the current IPS feature status for your Netskope tenant.

    Queries the IPS status endpoint to display whether Intrusion Prevention
    is enabled, the current mode (detect or prevent), and the active
    signature database version.  This is useful for verifying that IPS is
    operational before investigating signature hits or adjusting allowlists.

    The IPS feature must be licensed and enabled in your tenant before this
    endpoint will return data.

    EXAMPLES

        # Check IPS status
        netskope ips status

        # Get IPS status as JSON for automation
        netskope -o json ips status

        # Check status on a specific profile
        netskope --profile production ips status
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if not _is_quiet(ctx):
        with spinner("Fetching IPS status...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/ips/status")
    else:
        result = client.request("GET", "/api/v2/ips/status")

    formatter.format_output(result, fmt=fmt, title="IPS Status")


# ---------------------------------------------------------------------------
# Allowlist commands
# ---------------------------------------------------------------------------


@allowlist_app.command("list")
def allowlist_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of allowlist entries to return. "
            "When omitted the API returns all entries. Use this to paginate "
            "through large allowlists or to preview just the first few entries."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of entries to skip before returning results. "
            "Combine with --limit for pagination when the allowlist "
            "contains a large number of IP addresses or CIDR ranges."
        ),
    ),
) -> None:
    """List all IP addresses and CIDR ranges on the IPS allowlist.

    Retrieves the current IPS allowlist entries from the Netskope tenant.
    Allowlisted IPs are excluded from IPS signature inspection, which is
    useful for trusted internal scanners, penetration testing hosts, or
    known-safe services that would otherwise trigger false positives.

    EXAMPLES

        # List all allowlist entries
        netskope ips allowlist list

        # List the first 10 entries
        netskope ips allowlist list --limit 10

        # Paginate through entries
        netskope ips allowlist list --limit 50 --offset 50

        # Output as CSV for spreadsheet import
        netskope -o csv ips allowlist list
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
        with spinner("Fetching IPS allowlist...", no_color=_no_color(ctx)):
            result = client.request("GET", "/api/v2/ips/allowlist", params=params or None)
    else:
        result = client.request("GET", "/api/v2/ips/allowlist", params=params or None)

    formatter.format_output(result, fmt=fmt, title="IPS Allowlist")


@allowlist_app.command("add")
def allowlist_add(
    ctx: typer.Context,
    ip: str = typer.Option(
        ...,
        "--ip",
        help=(
            "IP address or CIDR range to add to the IPS allowlist. "
            "Supports both IPv4 and IPv6 addresses as well as CIDR notation "
            "(e.g. 10.0.0.0/8, 192.168.1.100). Traffic from this address "
            "will bypass IPS signature inspection."
        ),
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help=(
            "Human-readable description explaining why this IP is allowlisted. "
            "Providing a clear reason helps with future audits and makes it "
            "easier to determine whether the entry is still needed."
        ),
    ),
) -> None:
    """Add an IP address or CIDR range to the IPS allowlist.

    Creates a new entry in the IPS allowlist so that traffic from the
    specified IP or range is excluded from intrusion prevention signature
    matching.  This is commonly used for trusted vulnerability scanners,
    penetration testing hosts, or internal services that generate benign
    traffic patterns that resemble known attack signatures.

    Be cautious when adding broad CIDR ranges, as they reduce the
    effective coverage of your IPS deployment.

    EXAMPLES

        # Allowlist a single IP with a description
        netskope ips allowlist add --ip 10.20.30.40 --description "Vuln scanner"

        # Allowlist a CIDR range
        netskope ips allowlist add --ip 172.16.0.0/16 -d "Internal lab network"

        # Allowlist and get JSON confirmation
        netskope -o json ips allowlist add --ip 192.168.1.50
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body: dict[str, object] = {
        "data": {
            "ip": ip,
        }
    }
    if description is not None:
        body["data"]["description"] = description  # type: ignore[index]

    if not _is_quiet(ctx):
        with spinner(f"Adding '{ip}' to IPS allowlist...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/ips/allowlist", json_data=body)
    else:
        result = client.request("POST", "/api/v2/ips/allowlist", json_data=body)

    echo_success(f"IP '{ip}' added to the IPS allowlist.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="Allowlist Entry Added")


# ---------------------------------------------------------------------------
# Signatures command
# ---------------------------------------------------------------------------


@ips_app.command("signatures")
def signatures(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of signature references to return. "
            "The signature database can be very large; use this option to "
            "limit the output to a manageable number of entries."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of signature entries to skip before returning results. "
            "Combine with --limit for pagination when browsing the full "
            "signature reference list."
        ),
    ),
) -> None:
    """List IPS signature references from the Netskope signature database.

    Retrieves the signature reference list which contains metadata about
    the intrusion detection and prevention signatures available in your
    tenant.  Each entry includes the signature ID, name, severity, CVE
    references, and the category of attack it detects.

    Use this command to look up signature details when investigating an
    IPS alert, or to audit which signatures are available in your current
    database version.

    EXAMPLES

        # List all signature references
        netskope ips signatures

        # List the first 20 signatures
        netskope ips signatures --limit 20

        # Paginate through signatures as JSON
        netskope -o json ips signatures --limit 100 --offset 200

        # Export signatures to CSV
        netskope -o csv ips signatures
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
        with spinner("Fetching IPS signature references...", no_color=_no_color(ctx)):
            result = client.request(
                "GET",
                "/api/v2/ips/signaturereferencelist",
                params=params or None,
            )
    else:
        result = client.request(
            "GET",
            "/api/v2/ips/signaturereferencelist",
            params=params or None,
        )

    formatter.format_output(result, fmt=fmt, title="IPS Signature References")
