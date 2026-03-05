"""IPsec VPN tunnel management commands for the Netskope CLI.

Provides subcommands to list Points of Presence (POPs), and to list, create,
update, and delete IPsec VPN tunnels used for site-to-cloud connectivity.
"""

from __future__ import annotations

import getpass
from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
ipsec_app = typer.Typer(
    name="ipsec",
    help=(
        "Manage IPsec VPN tunnels and Points of Presence.\n\n"
        "IPsec (Internet Protocol Security) tunnels provide encrypted site-to-cloud "
        "connectivity between your on-premises infrastructure and the Netskope Security "
        "Cloud. This command group lets you manage tunnel lifecycle (create, update, "
        "delete), monitor tunnel status, and discover available Points of Presence "
        "(POPs) for tunnel termination."
    ),
    no_args_is_help=True,
)

pops_app = typer.Typer(
    name="pops",
    help=(
        "Discover IPsec Points of Presence (POPs).\n\n"
        "Points of Presence are Netskope data-center locations where IPsec tunnels "
        "terminate. Use this command to find POPs by name, region, or country so you "
        "can select the closest or most appropriate endpoint for your tunnels."
    ),
    no_args_is_help=True,
)
ipsec_app.add_typer(pops_app, name="pops")

tunnels_app = typer.Typer(
    name="tunnels",
    help=(
        "Manage IPsec VPN tunnels.\n\n"
        "IPsec tunnels carry encrypted traffic between your sites and the Netskope "
        "cloud. Use these commands to provision new tunnels, update configuration "
        "such as encryption or bandwidth, monitor tunnel status, and decommission "
        "tunnels that are no longer needed."
    ),
    no_args_is_help=True,
)
ipsec_app.add_typer(tunnels_app, name="tunnels")


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
    return OutputFormatter(no_color=no_color, count_only=count_only)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


# ---------------------------------------------------------------------------
# Bandwidth & encryption choices
# ---------------------------------------------------------------------------
BANDWIDTH_CHOICES = [50, 100, 150, 200, 250, 1000]
ENCRYPTION_CHOICES = ["AES128-CBC", "AES256-CBC", "AES256-GCM"]


# ---------------------------------------------------------------------------
# Commands — pops
# ---------------------------------------------------------------------------


@pops_app.command("list")
def list_pops(
    ctx: typer.Context,
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help=(
            "Filter POPs by name or partial name match. Use this to locate a specific "
            "Point of Presence when you already know its identifier. "
            "Case-insensitive substring match."
        ),
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        "-r",
        help=(
            "Filter POPs by ISO-3166 region code (e.g. 'US', 'EU'). Use this to find "
            "all available tunnel endpoints within a geographic region. "
            "Helps optimize latency by selecting nearby POPs."
        ),
    ),
    country: Optional[str] = typer.Option(
        None,
        "--country",
        "-c",
        help=(
            "Filter POPs by ISO-3166 country code (e.g. 'US', 'DE', 'JP'). Narrows "
            "results to POPs physically located in the specified country. "
            "Useful for data-residency or compliance requirements."
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help=(
            "Maximum number of POP records to return. Defaults to 100. "
            "Use with --offset for pagination through large result sets. "
            "Set to a smaller value for faster responses."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of records to skip before returning results. Use with --limit "
            "for pagination through the full POP list. "
            "Defaults to 0 (start from the first record)."
        ),
    ),
) -> None:
    """List available IPsec Points of Presence (POPs).

    Queries GET /api/v2/steering/ipsec/pops to retrieve the Netskope data-center
    locations where IPsec tunnels can terminate. Each POP has a name, geographic
    region, and country. When creating a tunnel you must specify one or more POP
    names, so use this command first to discover valid targets.

    Points of Presence are the cloud-side endpoints for your IPsec tunnels. Choosing
    a POP close to your site minimizes latency and improves tunnel performance.

    Examples:
        netskope ipsec pops list
        netskope ipsec pops list --region US --limit 20
        netskope -o json ipsec pops list --country DE
        netskope ipsec pops list --name "US-West"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {"limit": limit}
    if name is not None:
        params["name"] = name
    if region is not None:
        params["region"] = region
    if country is not None:
        params["country"] = country
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching IPsec POPs..."):
        data = client.request("GET", "/api/v2/steering/ipsec/pops", params=params)

    formatter.format_output(data, fmt=fmt, title="IPsec Points of Presence")


# ---------------------------------------------------------------------------
# Commands — tunnels list / create / update / delete
# ---------------------------------------------------------------------------


@tunnels_app.command("list")
def list_tunnels(
    ctx: typer.Context,
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help=(
            "Filter tunnels by operational status: 'up' or 'down'. Use this to quickly "
            "identify tunnels that need attention or verify all tunnels are healthy. "
            "Omit to return tunnels in any state."
        ),
    ),
    site: Optional[str] = typer.Option(
        None,
        "--site",
        help=(
            "Filter tunnels by site (tunnel) name. Use this to find tunnels associated "
            "with a particular branch office or data center. "
            "Supports partial name matching."
        ),
    ),
    pop: Optional[str] = typer.Option(
        None,
        "--pop",
        help=(
            "Filter tunnels by the Point of Presence they terminate at. Use this to "
            "see all tunnels landing on a specific POP for capacity planning. "
            "Specify the POP name as shown in 'ipsec pops list'."
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help=(
            "Maximum number of tunnel records to return. Defaults to 100. "
            "Use with --offset for pagination through large tunnel inventories. "
            "Set to a smaller value for faster responses."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of records to skip before returning results. Use with --limit "
            "for pagination through the full tunnel list. "
            "Defaults to 0 (start from the first record)."
        ),
    ),
) -> None:
    """List all IPsec VPN tunnels with optional filtering.

    Queries GET /api/v2/steering/ipsec/tunnels to retrieve tunnel records including
    site name, POP assignment, status, encryption settings, and bandwidth. Use this
    to audit your tunnel fleet, check connectivity status, or find tunnel IDs for
    update and delete operations.

    IPsec tunnels provide encrypted site-to-cloud connectivity. Each tunnel connects
    an on-premises device (router or firewall) to one or more Netskope POPs.

    Examples:
        netskope ipsec tunnels list
        netskope ipsec tunnels list --status up
        netskope -o json ipsec tunnels list --site "HQ-Primary"
        netskope ipsec tunnels list --pop "US-West" --limit 50
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {"limit": limit}
    if status is not None:
        if status.lower() not in ("up", "down"):
            echo_error("--status must be 'up' or 'down'.")
            raise typer.Exit(code=1)
        params["status"] = status.lower()
    if site is not None:
        params["site"] = site
    if pop is not None:
        params["pop"] = pop
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching IPsec tunnels..."):
        data = client.request("GET", "/api/v2/steering/ipsec/tunnels", params=params)

    formatter.format_output(data, fmt=fmt, title="IPsec Tunnels")


@tunnels_app.command("get")
def get_tunnel(
    ctx: typer.Context,
    tunnel_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the IPsec tunnel to retrieve. Find IDs via " "'netskope ipsec tunnels list'."),
    ),
) -> None:
    """Get detailed information about a specific IPsec tunnel.

    Queries GET /api/v2/steering/ipsec/tunnels/{id} to retrieve the full tunnel
    configuration including site name, POP assignment, encryption, bandwidth,
    PSK hash, and current status.

    Examples:
        netskope ipsec tunnels get 42
        netskope -o json ipsec tunnels get 42
        netskope -o yaml ipsec tunnels get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching IPsec tunnel {tunnel_id}..."):
        data = client.request("GET", f"/api/v2/steering/ipsec/tunnels/{tunnel_id}")

    formatter.format_output(data, fmt=fmt, title=f"IPsec Tunnel {tunnel_id}")


@tunnels_app.command("create")
def create_tunnel(
    ctx: typer.Context,
    site: str = typer.Option(
        ...,
        "--site",
        help=(
            "Name for the IPsec tunnel, typically matching the branch or data-center "
            "site it connects. Must be unique across your tenant. "
            "Example: 'NYC-Office-Primary' or 'DC-East-Backup'."
        ),
    ),
    pops: str = typer.Option(
        ...,
        "--pops",
        help=(
            "Comma-separated list of POP names where the tunnel should terminate. "
            "Use 'ipsec pops list' to discover valid POP names. "
            "Specifying multiple POPs enables redundancy across data centers."
        ),
    ),
    psk: Optional[str] = typer.Option(
        None,
        "--psk",
        help=(
            "Pre-shared key for IKE authentication. For security, omit this flag and "
            "the CLI will prompt you interactively so the key does not appear in shell "
            "history. Must meet your organization's password complexity requirements."
        ),
        hidden=True,
    ),
    srcidentity: str = typer.Option(
        ...,
        "--srcidentity",
        help=(
            "IKE identity (source identity) used during Phase 1 negotiation. This is "
            "typically a FQDN or email-style identifier configured on your on-premises "
            "VPN device. Must match the identity your CPE presents."
        ),
    ),
    bandwidth: int = typer.Option(
        100,
        "--bandwidth",
        "-b",
        help=(
            "Maximum bandwidth for the tunnel in Mbps. Valid choices: 50, 100, 150, "
            "200, 250, 1000. Defaults to 100 Mbps. Choose based on your site's uplink "
            "capacity and expected traffic volume."
        ),
    ),
    encryption: str = typer.Option(
        "AES256-CBC",
        "--encryption",
        "-e",
        help=(
            "Encryption algorithm for the IPsec tunnel. Valid choices: AES128-CBC, "
            "AES256-CBC, AES256-GCM. Defaults to AES256-CBC. AES256-GCM offers "
            "authenticated encryption with better performance on modern hardware."
        ),
    ),
    enable: Optional[bool] = typer.Option(
        None,
        "--enable/--disable",
        help=(
            "Enable or disable the tunnel after creation. Defaults to enabled. "
            "Use --disable to create the tunnel in a disabled state for staged "
            "rollouts or maintenance preparation."
        ),
    ),
    vendor: Optional[str] = typer.Option(
        None,
        "--vendor",
        help=(
            "CPE vendor name for documentation and support purposes. Specify the "
            "manufacturer of the on-premises VPN device (e.g. 'Cisco', 'Palo Alto', "
            "'Fortinet'). Optional but recommended for operational visibility."
        ),
    ),
    notes: Optional[str] = typer.Option(
        None,
        "--notes",
        help=(
            "Free-text notes or description attached to the tunnel. Use this for "
            "change-management references, contact info, or deployment context. "
            "Visible in tunnel listings and detail views."
        ),
    ),
) -> None:
    """Create a new IPsec VPN tunnel.

    Sends POST /api/v2/steering/ipsec/tunnels to provision an encrypted
    site-to-cloud tunnel. You must specify the site name, at least one POP for
    tunnel termination, a pre-shared key (PSK) for IKE authentication, and a
    source identity.

    The pre-shared key is collected interactively via a secure prompt so that it
    never appears in your shell history or process listing. If you supply --psk
    on the command line it will be used directly (useful for automation), but
    interactive prompting is strongly recommended for human operators.

    After the tunnel is created, configure your on-premises VPN device with the
    returned tunnel endpoint addresses and the same PSK to bring the tunnel up.

    Examples:
        netskope ipsec tunnels create --site "NYC-Office" --pops "US-East1,US-East2" \\
            --srcidentity vpn@example.com
        netskope ipsec tunnels create --site "London-DC" --pops "EU-West1" \\
            --srcidentity london@corp.net --bandwidth 250 --encryption AES256-GCM
        netskope ipsec tunnels create --site "Lab" --pops "US-West1" \\
            --srcidentity lab@test.com --disable --notes "Testing only"
    """
    # Validate bandwidth
    if bandwidth not in BANDWIDTH_CHOICES:
        echo_error(
            f"Invalid bandwidth '{bandwidth}'. " f"Valid choices: {', '.join(str(b) for b in BANDWIDTH_CHOICES)}."
        )
        raise typer.Exit(code=1)

    # Validate encryption
    if encryption not in ENCRYPTION_CHOICES:
        echo_error(f"Invalid encryption '{encryption}'. " f"Valid choices: {', '.join(ENCRYPTION_CHOICES)}.")
        raise typer.Exit(code=1)

    # Securely collect the pre-shared key
    if psk is None:
        psk = getpass.getpass("Enter pre-shared key (PSK): ")
        if not psk:
            echo_error("Pre-shared key cannot be empty.")
            raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    pop_list = [p.strip() for p in pops.split(",") if p.strip()]
    if not pop_list:
        echo_error("--pops must contain at least one POP name.")
        raise typer.Exit(code=1)

    payload: dict[str, object] = {
        "site": site,
        "pops": pop_list,
        "psk": psk,
        "srcidentity": srcidentity,
        "bandwidth": bandwidth,
        "encryption": encryption,
    }

    if enable is not None:
        payload["enabled"] = enable
    else:
        payload["enabled"] = True

    if vendor is not None:
        payload["vendor"] = vendor
    if notes is not None:
        payload["notes"] = notes

    with spinner("Creating IPsec tunnel..."):
        data = client.request("POST", "/api/v2/steering/ipsec/tunnels", json_data=payload)

    echo_success(f"IPsec tunnel '{site}' created.")
    formatter.format_output(data, fmt=fmt, title="Created IPsec Tunnel")


@tunnels_app.command("update")
def update_tunnel(
    ctx: typer.Context,
    tunnel_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the IPsec tunnel to update. Find IDs via "
            "'netskope ipsec tunnels list'. This identifies the specific tunnel "
            "whose configuration will be modified."
        ),
    ),
    site: Optional[str] = typer.Option(
        None,
        "--site",
        help=(
            "New name for the tunnel. Must be unique across your tenant. "
            "Use this to rename the tunnel after a site relocation or "
            "naming-convention change."
        ),
    ),
    pops: Optional[str] = typer.Option(
        None,
        "--pops",
        help=(
            "Comma-separated list of POP names to reassign the tunnel to. "
            "Use 'ipsec pops list' to discover valid POP names. "
            "Changing POPs may briefly disrupt the tunnel during re-negotiation."
        ),
    ),
    psk: Optional[str] = typer.Option(
        None,
        "--psk",
        help=(
            "New pre-shared key for IKE authentication. For security, omit this flag "
            "and the CLI will prompt you interactively. After rotation, update your "
            "on-premises VPN device with the new key to restore connectivity."
        ),
        hidden=True,
    ),
    bandwidth: Optional[int] = typer.Option(
        None,
        "--bandwidth",
        "-b",
        help=(
            "New maximum bandwidth in Mbps. Valid choices: 50, 100, 150, 200, 250, "
            "1000. Adjust when site capacity changes or traffic patterns shift. "
            "Takes effect after the next IKE re-key."
        ),
    ),
    encryption: Optional[str] = typer.Option(
        None,
        "--encryption",
        "-e",
        help=(
            "New encryption algorithm. Valid choices: AES128-CBC, AES256-CBC, "
            "AES256-GCM. Changing encryption requires the on-premises device to "
            "support the new algorithm. Takes effect after the next IKE re-key."
        ),
    ),
    enable: Optional[bool] = typer.Option(
        None,
        "--enable/--disable",
        help=(
            "Enable or disable the tunnel. Use --disable for planned maintenance "
            "without deleting the configuration. Use --enable to bring a disabled "
            "tunnel back online."
        ),
    ),
    notes: Optional[str] = typer.Option(
        None,
        "--notes",
        help=(
            "Updated free-text notes or description for the tunnel. Useful for "
            "recording maintenance history or updated contact information. "
            "Replaces the existing notes value."
        ),
    ),
) -> None:
    """Update an existing IPsec VPN tunnel's configuration.

    Sends PATCH /api/v2/steering/ipsec/tunnels/{tunnel_id} with the provided
    changes. Only the fields you specify are modified; all other settings are
    preserved. At least one update field must be provided.

    If you supply --psk without a value on the command line, the CLI prompts
    interactively so the new key never appears in shell history. After rotating
    the PSK, remember to update your on-premises VPN device as well.

    Examples:
        netskope ipsec tunnels update 42 --bandwidth 250
        netskope ipsec tunnels update 42 --encryption AES256-GCM --notes "Upgraded"
        netskope ipsec tunnels update 42 --disable
        netskope -o json ipsec tunnels update 42 --pops "US-East1,US-East2"
    """
    # Validate optional bandwidth
    if bandwidth is not None and bandwidth not in BANDWIDTH_CHOICES:
        echo_error(
            f"Invalid bandwidth '{bandwidth}'. " f"Valid choices: {', '.join(str(b) for b in BANDWIDTH_CHOICES)}."
        )
        raise typer.Exit(code=1)

    # Validate optional encryption
    if encryption is not None and encryption not in ENCRYPTION_CHOICES:
        echo_error(f"Invalid encryption '{encryption}'. " f"Valid choices: {', '.join(ENCRYPTION_CHOICES)}.")
        raise typer.Exit(code=1)

    payload: dict[str, object] = {}

    if site is not None:
        payload["site"] = site
    if pops is not None:
        pop_list = [p.strip() for p in pops.split(",") if p.strip()]
        if not pop_list:
            echo_error("--pops must contain at least one POP name.")
            raise typer.Exit(code=1)
        payload["pops"] = pop_list
    if psk is not None:
        payload["psk"] = psk
    if bandwidth is not None:
        payload["bandwidth"] = bandwidth
    if encryption is not None:
        payload["encryption"] = encryption
    if enable is not None:
        payload["enabled"] = enable
    if notes is not None:
        payload["notes"] = notes

    if not payload:
        echo_error(
            "No update fields provided. Specify at least one of: --site, --pops, "
            "--psk, --bandwidth, --encryption, --enable/--disable, --notes."
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Updating IPsec tunnel {tunnel_id}..."):
        data = client.request(
            "PATCH",
            f"/api/v2/steering/ipsec/tunnels/{tunnel_id}",
            json_data=payload,
        )

    echo_success(f"IPsec tunnel {tunnel_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated IPsec Tunnel {tunnel_id}")


@tunnels_app.command("delete")
def delete_tunnel(
    ctx: typer.Context,
    tunnel_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the IPsec tunnel to delete. Find IDs via "
            "'netskope ipsec tunnels list'. This action permanently removes the "
            "tunnel configuration and cannot be undone."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and proceed with deletion. "
            "Required for non-interactive use (scripts, CI/CD, AI agents). "
            "Defaults to False (prompt for confirmation)."
        ),
    ),
) -> None:
    """Delete an IPsec VPN tunnel from the Netskope configuration.

    Sends DELETE /api/v2/steering/ipsec/tunnels/{tunnel_id}. This is a destructive
    operation that removes the tunnel registration and terminates the IPsec session.
    Any traffic routed through this tunnel will be disrupted immediately. Consider
    using --disable on the update command instead if you only need a temporary
    outage.

    Use --yes to skip the confirmation prompt for scripted or automated workflows.

    Examples:
        netskope ipsec tunnels delete 42
        netskope ipsec tunnels delete 42 --yes
    """
    console = _get_console(ctx)

    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete IPsec tunnel {tunnel_id}?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    client = _build_client(ctx)

    with spinner(f"Deleting IPsec tunnel {tunnel_id}..."):
        client.request("DELETE", f"/api/v2/steering/ipsec/tunnels/{tunnel_id}")

    echo_success(f"IPsec tunnel {tunnel_id} deleted.")
