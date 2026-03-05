"""Device management commands for the Netskope CLI.

Provides subcommands for listing managed devices, managing device tags,
and querying supported operating systems.  These commands help
administrators inventory their endpoint fleet, organise devices with
tags, and verify platform compatibility before rolling out the
Netskope Client.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

devices_app = typer.Typer(
    name="devices",
    help="Device Management — list devices, manage tags, and check OS support.",
    no_args_is_help=True,
)

_tags_app = typer.Typer(
    name="tags",
    help="Create, list, and delete device tags.",
    no_args_is_help=True,
)

devices_app.add_typer(_tags_app, name="tags")


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
    return OutputFormatter(no_color=no_color, count_only=count_only)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


# ---------------------------------------------------------------------------
# Device commands
# ---------------------------------------------------------------------------


@devices_app.command("list")
def devices_list(
    ctx: typer.Context,
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=(
            "Maximum number of devices to return. Defaults to 25. "
            "Increase for larger exports or decrease for quick lookups."
        ),
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help=(
            "Number of records to skip for pagination. Combine with --limit " "to page through results. Defaults to 0."
        ),
    ),
) -> None:
    """List managed devices enrolled in your Netskope tenant.

    Queries GET /api/v2/steering/devices to retrieve device records
    including hostname, OS version, Netskope Client version, user
    association, and last-seen timestamp.  Use this command for fleet
    inventory, compliance checks, or to identify devices that have
    not checked in recently.

    Note: If the steering/devices endpoint is not available on your
    tenant, use 'netskope events client-status' to query device
    connectivity events instead.

    Examples:
        # List all devices as a table
        netskope devices list

        # Output as JSON for integration with a CMDB
        netskope -o json devices list

        # Export as CSV for a spreadsheet
        netskope -o csv devices list

        # Paginate through results
        netskope devices list --limit 50 --offset 100
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False
    console = _get_console(ctx)

    params: dict[str, object] = {"limit": limit, "offset": offset}

    try:
        with spinner("Fetching devices...", no_color=no_color):
            data = client.request("GET", "/api/v2/steering/devices", params=params)
    except Exception as exc:
        err_msg = str(exc)
        if "404" in err_msg or "Not Found" in err_msg:
            console.print(
                "[yellow]The devices list endpoint is not available on this tenant.[/yellow]\n"
                "Use [bold]'netskope events client-status'[/bold] to view device information."
            )
            raise typer.Exit(code=1)
        raise

    formatter.format_output(data, fmt=_get_output_format(ctx), title="Managed Devices")


# ---------------------------------------------------------------------------
# Tags commands
# ---------------------------------------------------------------------------


@_tags_app.command("list")
def tags_list(ctx: typer.Context) -> None:
    """List all device tags defined in your Netskope tenant.

    Queries GET /api/v2/devices/tags and returns every device tag
    including its name, type, and the number of devices associated
    with it.  Device tags are used to group endpoints for steering
    policies and conditional access rules.

    Examples:
        # List all device tags
        netskope devices tags list

        # Output as JSON
        netskope -o json devices tags list

        # List tags from a specific profile
        netskope --profile staging devices tags list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching device tags...", no_color=no_color):
        data = client.request("GET", "/api/v2/devices/tags")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="Device Tags")


@_tags_app.command("get")
def tags_get(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the device tag to retrieve. "
            "Run 'netskope devices tags list' to find tag IDs."
        ),
    ),
) -> None:
    """Get details of a specific device tag by ID.

    Queries GET /api/v2/devices/tags/{id} and returns the tag definition
    including its name, type, and associated devices.

    Examples:
        netskope devices tags get 15
        netskope -o json devices tags get 15
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching device tag {tag_id}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/devices/tags/{tag_id}")

    formatter.format_output(data, fmt=_get_output_format(ctx), title=f"Device Tag {tag_id}")


@_tags_app.command("create")
def tags_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        help=(
            "Name for the new device tag.  Choose a clear, descriptive name "
            "such as 'engineering-laptops' or 'vpn-exempt'.  The name must "
            "be unique within the tenant."
        ),
    ),
    type: str = typer.Option(
        ...,
        "--type",
        help=(
            "Classification type for the tag.  This categorises the tag for "
            "filtering and policy assignment.  Common values include 'custom', "
            "'department', or 'location' depending on your tagging strategy."
        ),
    ),
) -> None:
    """Create a new device tag for organising managed endpoints.

    Sends POST /api/v2/devices/tags to create a tag.  Device tags let
    you logically group endpoints so you can apply steering policies,
    conditional access rules, or reporting filters to specific subsets
    of your device fleet.

    Examples:
        # Create a custom tag for engineering laptops
        netskope devices tags create --name "engineering-laptops" --type "custom"

        # Create a department tag
        netskope devices tags create --name "finance-desktops" --type "department"

        # Create a tag and view the JSON response
        netskope -o json devices tags create --name "contractors" --type "custom"
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    body: dict[str, object] = {
        "name": name,
        "type": type,
    }

    with spinner("Creating device tag...", no_color=no_color):
        data = client.request("POST", "/api/v2/devices/tags", json_data=body)

    echo_success(f"Device tag '{name}' created.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title="Created Device Tag")


@_tags_app.command("update")
def tags_update(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the device tag to update. "
            "Run 'netskope devices tags list' to find tag IDs."
        ),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="New name for the device tag.",
    ),
    type: Optional[str] = typer.Option(
        None,
        "--type",
        help="New classification type for the tag.",
    ),
) -> None:
    """Update a device tag's name or type.

    Sends PUT /api/v2/devices/tags/{id} with the provided changes. At least
    one of --name or --type must be specified.

    Examples:
        netskope devices tags update 15 --name "new-tag-name"
        netskope devices tags update 15 --type "department"
        netskope devices tags update 15 --name "eng-laptops" --type "custom"
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    body: dict[str, object] = {}
    if name is not None:
        body["name"] = name
    if type is not None:
        body["type"] = type

    if not body:
        typer.echo("Nothing to update. Provide --name and/or --type.", err=True)
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _build_formatter(ctx)

    with spinner(f"Updating device tag {tag_id}...", no_color=no_color):
        data = client.request("PUT", f"/api/v2/devices/tags/{tag_id}", json_data=body)

    echo_success(f"Device tag {tag_id} updated.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title=f"Updated Device Tag {tag_id}")


@_tags_app.command("delete")
def tags_delete(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the device tag to delete.  Run "
            "'netskope devices tags list' to find tag IDs.  Deleting a tag "
            "removes it from all associated devices."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and immediately delete "
            "the tag.  Useful for scripted or CI/CD workflows where no "
            "terminal is available for user input."
        ),
    ),
) -> None:
    """Delete a device tag by its ID.

    Sends DELETE /api/v2/devices/tags/{id} to permanently remove the
    tag.  Any devices currently associated with the tag will have it
    removed from their tag list.  Steering policies or rules that
    reference this tag may need to be updated afterwards.

    Examples:
        # Delete tag 15 (will prompt for confirmation)
        netskope devices tags delete 15

        # Delete tag 15 without confirmation
        netskope devices tags delete 15 --yes

        # Delete from a specific profile
        netskope --profile staging devices tags delete 8 -y
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if not yes:
        typer.confirm(
            f"Are you sure you want to delete device tag {tag_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    with spinner(f"Deleting device tag {tag_id}...", no_color=no_color):
        client.request("DELETE", f"/api/v2/devices/tags/{tag_id}")

    echo_success(f"Device tag {tag_id} deleted.", no_color=no_color)


# ---------------------------------------------------------------------------
# Supported OS command
# ---------------------------------------------------------------------------


@devices_app.command("supported-os")
def supported_os(ctx: typer.Context) -> None:
    """List operating systems supported by the Netskope Client.

    Queries GET /api/v2/devices/supportedos and returns the full list
    of operating systems and versions that the Netskope Client can be
    installed on.  Use this command before a rollout to confirm that
    your fleet's OS versions are compatible, or to check whether a
    newly released OS has been added to the supported list.

    Examples:
        # List supported operating systems
        netskope devices supported-os

        # Output as JSON for programmatic checks
        netskope -o json devices supported-os

        # Output as YAML for readability
        netskope -o yaml devices supported-os
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching supported operating systems...", no_color=no_color):
        data = client.request("GET", "/api/v2/devices/supportedos")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="Supported Operating Systems")
