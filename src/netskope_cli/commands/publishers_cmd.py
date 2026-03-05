"""Publisher management commands for the Netskope CLI.

Provides subcommands to list, create, update, delete publishers, and to view
upgrade profiles and local brokers.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
publishers_app = typer.Typer(
    name="publishers",
    help=(
        "Manage private-access publishers and their infrastructure.\n\n"
        "Publishers are on-premises or cloud-hosted connectors that enable secure "
        "access to private applications through the Netskope Security Cloud. This "
        "command group provides full CRUD for publishers, plus access to upgrade "
        "profiles and local brokers. Use these commands to provision, monitor, and "
        "maintain your publisher infrastructure."
    ),
    no_args_is_help=True,
)

upgrade_profiles_app = typer.Typer(
    name="upgrade-profiles",
    help=(
        "View publisher upgrade profiles.\n\n"
        "Upgrade profiles define software update schedules and policies for "
        "publishers. Use this to check which upgrade profiles are available "
        "and their configuration."
    ),
    no_args_is_help=True,
)
publishers_app.add_typer(upgrade_profiles_app, name="upgrade-profiles")

local_brokers_app = typer.Typer(
    name="local-brokers",
    help=(
        "View local brokers associated with publishers.\n\n"
        "Local brokers handle traffic distribution within a publisher deployment. "
        "Use this to monitor local broker status and configuration."
    ),
    no_args_is_help=True,
)
publishers_app.add_typer(local_brokers_app, name="local-brokers")


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
# Commands — publishers list / get / create / update / delete
# ---------------------------------------------------------------------------


@publishers_app.command("list")
def list_publishers(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help=(
            "Maximum number of publishers to return. Use with --offset for pagination. "
            "Omit to return all publishers."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=("Number of records to skip before returning results. Use with --limit for " "pagination. Defaults to 0."),
    ),
    filter_query: Optional[str] = typer.Option(
        None,
        "--filter",
        "-F",
        help=(
            "Filter expression to narrow results. Filter syntax is API-specific and "
            "supports field comparisons. Omit to return all publishers."
        ),
    ),
) -> None:
    """List all publishers with optional filtering and pagination.

    Queries GET /api/v2/infrastructure/publishers to retrieve publisher records
    including name, status, version, and connectivity information. Use this to
    audit your publisher fleet or find publisher IDs for other operations.

    Examples:
        netskope publishers list
        netskope publishers list --limit 10 --offset 0
        netskope -o json publishers list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter_query is not None:
        params["filter"] = filter_query

    with spinner("Fetching publishers..."):
        data = client.request("GET", "/api/v2/infrastructure/publishers", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="Publishers",
        default_fields=["publisher_name", "publisher_id", "status", "version", "apps_count"],
    )


@publishers_app.command("get")
def get_publisher(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(
        ...,
        help="Numeric publisher ID. Find IDs via 'netskope publishers list'.",
    ),
) -> None:
    """Retrieve detailed information for a specific publisher by ID.

    Queries GET /api/v2/infrastructure/publishers/{id} for the full publisher
    record including name, status, version, connectivity, and configuration.
    Use this to troubleshoot publisher issues or verify deployment state.

    Examples:
        netskope publishers get 42
        netskope -o json publishers get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching publisher {publisher_id}..."):
        data = client.request("GET", f"/api/v2/infrastructure/publishers/{publisher_id}")

    formatter.format_output(data, fmt=fmt, title=f"Publisher {publisher_id}")


@publishers_app.command("create")
def create_publisher(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help=(
            "Display name for the new publisher. Should be descriptive and identify "
            "the deployment location, such as 'AWS-US-East-Publisher' or "
            "'DC-Primary-Publisher'. Must be unique."
        ),
    ),
    lbroker_connect: bool = typer.Option(
        False,
        "--lbroker-connect",
        help=(
            "Enable local broker connectivity for this publisher. When enabled, the "
            "publisher can connect to local brokers for traffic distribution. "
            "Defaults to False (disabled)."
        ),
    ),
) -> None:
    """Create a new publisher in the Netskope infrastructure.

    Sends POST /api/v2/infrastructure/publishers to register a new publisher.
    After creation, deploy the publisher software on your infrastructure and
    configure it to connect to Netskope. The publisher enables secure access
    to private applications.

    Examples:
        netskope publishers create --name "AWS-US-East-Publisher"
        netskope publishers create --name "DC-Primary" --lbroker-connect
        netskope -o json publishers create --name "Cloud-Publisher"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {
        "name": name,
        "lbroker_connect": lbroker_connect,
    }

    with spinner("Creating publisher..."):
        data = client.request("POST", "/api/v2/infrastructure/publishers", json_data=payload)

    echo_success(f"Publisher '{name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created Publisher")


@publishers_app.command("update")
def update_publisher(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(
        ...,
        help="Numeric ID of the publisher to update. Find IDs via 'netskope publishers list'.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help=("New display name for the publisher. Must be unique. " "At least one update field is required."),
    ),
) -> None:
    """Update an existing publisher's configuration.

    Sends PUT /api/v2/infrastructure/publishers/{id} with the provided changes.
    Currently supports renaming the publisher. At least one update field must
    be provided.

    Examples:
        netskope publishers update 42 --name "Renamed-Publisher"
        netskope -o json publishers update 42 --name "DC-Secondary"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {}
    if name is not None:
        payload["name"] = name

    if not payload:
        echo_error("No update fields provided. Use --name to specify a new value.")
        raise typer.Exit(code=1)

    with spinner(f"Updating publisher {publisher_id}..."):
        data = client.request(
            "PUT",
            f"/api/v2/infrastructure/publishers/{publisher_id}",
            json_data=payload,
        )

    echo_success(f"Publisher {publisher_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated Publisher {publisher_id}")


@publishers_app.command("delete")
def delete_publisher(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the publisher to delete. Find IDs via 'netskope publishers list'. "
            "This action cannot be undone."
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
    """Delete a publisher from the Netskope infrastructure.

    Sends DELETE /api/v2/infrastructure/publishers/{id}. This is a destructive
    operation that removes the publisher registration. Any private apps relying
    on this publisher will lose connectivity. Use --yes to skip confirmation.

    Examples:
        netskope publishers delete 42
        netskope publishers delete 42 --yes
    """
    console = _get_console(ctx)

    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete publisher {publisher_id}?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    client = _build_client(ctx)

    with spinner(f"Deleting publisher {publisher_id}..."):
        client.request("DELETE", f"/api/v2/infrastructure/publishers/{publisher_id}")

    echo_success(f"Publisher {publisher_id} deleted.")


# ---------------------------------------------------------------------------
# Commands — upgrade-profiles
# ---------------------------------------------------------------------------


@upgrade_profiles_app.command("list")
def list_upgrade_profiles(
    ctx: typer.Context,
) -> None:
    """List all available publisher upgrade profiles.

    Queries GET /api/v2/infrastructure/publishers/upgradeprofiles to retrieve
    software upgrade schedules and policies for publishers. Use this to check
    which upgrade profiles are available and their maintenance windows.

    Examples:
        netskope publishers upgrade-profiles list
        netskope -o json publishers upgrade-profiles list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching upgrade profiles..."):
        data = client.request("GET", "/api/v2/infrastructure/publishers/upgradeprofiles")

    formatter.format_output(data, fmt=fmt, title="Publisher Upgrade Profiles")


# ---------------------------------------------------------------------------
# Commands — local-brokers
# ---------------------------------------------------------------------------


@local_brokers_app.command("list")
def list_local_brokers(
    ctx: typer.Context,
) -> None:
    """List all local brokers in the publisher infrastructure.

    Queries GET /api/v2/infrastructure/lbrokers to retrieve local broker
    records including status, version, and publisher association. Local brokers
    handle traffic distribution within a publisher deployment.

    Examples:
        netskope publishers local-brokers list
        netskope -o json publishers local-brokers list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching local brokers..."):
        data = client.request("GET", "/api/v2/infrastructure/lbrokers")

    formatter.format_output(data, fmt=fmt, title="Local Brokers")
