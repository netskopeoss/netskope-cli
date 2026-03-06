"""NPA publisher management commands.

Provides subcommands to list, create, update, delete publishers, manage
registration tokens, view releases, and trigger bulk upgrades.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_console,
    _get_formatter,
    _get_output_format,
    _parse_comma_sep_ints,
)
from netskope_cli.commands.npa.local_brokers_cmd import local_brokers_app
from netskope_cli.commands.npa.upgrade_profiles_cmd import upgrade_profiles_app
from netskope_cli.core.output import echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
publishers_app = typer.Typer(
    name="publishers",
    help=(
        "Manage NPA publishers and their infrastructure.\n\n"
        "Publishers are on-premises or cloud-hosted connectors that enable secure "
        "access to private applications through the Netskope Security Cloud.\n\n"
        "Also available as the top-level shortcut 'netskope publishers' (with "
        "basic CRUD commands only)."
    ),
    no_args_is_help=True,
)

publishers_app.add_typer(upgrade_profiles_app, name="upgrade-profiles")
publishers_app.add_typer(local_brokers_app, name="local-brokers")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@publishers_app.command("list")
def list_publishers(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of publishers to return. Omit to return all.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Number of records to skip before returning results. Defaults to 0.",
    ),
    filter_query: Optional[str] = typer.Option(
        None,
        "--filter",
        "-F",
        help="Filter expression to narrow results (API-specific syntax).",
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        help="Comma-separated list of fields to include in the output.",
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help="Return only the total count of matching records.",
    ),
) -> None:
    """List all publishers with optional filtering and pagination.

    Queries GET /api/v2/infrastructure/publishers to retrieve publisher records.

    Examples:
        netskope npa publishers list
        netskope npa publishers list --limit 10 --offset 0
        netskope -o json npa publishers list
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
    if fields is not None:
        params["fields"] = fields

    with spinner("Fetching publishers..."):
        data = client.request("GET", "/api/v2/infrastructure/publishers", params=params or None)

    if count:
        formatter.format_output(data, fmt=fmt, title="Publishers", count=True)
    else:
        formatter.format_output(
            data,
            fmt=fmt,
            title="Publishers",
            default_fields=["publisher_name", "publisher_id", "status", "version", "apps_count"],
        )


@publishers_app.command("get")
def get_publisher(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(..., help="Numeric publisher ID."),
) -> None:
    """Retrieve detailed information for a specific publisher.

    Queries GET /api/v2/infrastructure/publishers/{id}.

    Examples:
        netskope npa publishers get 42
        netskope -o json npa publishers get 42
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
        help="Display name for the new publisher. Must be unique.",
    ),
    lbroker_connect: bool = typer.Option(
        False,
        "--lbroker-connect",
        help="Enable local broker connectivity for this publisher. Defaults to False.",
    ),
) -> None:
    """Create a new publisher.

    Sends POST /api/v2/infrastructure/publishers.

    Examples:
        netskope npa publishers create --name "AWS-US-East-Publisher"
        netskope npa publishers create --name "DC-Primary" --lbroker-connect
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
    publisher_id: int = typer.Argument(..., help="Numeric ID of the publisher to update."),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="New display name for the publisher.",
    ),
) -> None:
    """Update an existing publisher's configuration.

    Sends PATCH /api/v2/infrastructure/publishers/{id}.

    Examples:
        netskope npa publishers update 42 --name "Renamed-Publisher"
    """
    from netskope_cli.core.output import echo_error

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
            "PATCH",
            f"/api/v2/infrastructure/publishers/{publisher_id}",
            json_data=payload,
        )

    echo_success(f"Publisher {publisher_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated Publisher {publisher_id}")


@publishers_app.command("delete")
def delete_publisher(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(..., help="Numeric ID of the publisher to delete."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt. Required for non-interactive use.",
    ),
) -> None:
    """Delete a publisher from the Netskope infrastructure.

    Sends DELETE /api/v2/infrastructure/publishers/{id}. This is a destructive
    operation. Use --yes to skip confirmation.

    Examples:
        netskope npa publishers delete 42
        netskope npa publishers delete 42 --yes
    """
    _confirm_delete("publisher", publisher_id, yes, ctx)

    client = _build_client(ctx)

    with spinner(f"Deleting publisher {publisher_id}..."):
        client.request("DELETE", f"/api/v2/infrastructure/publishers/{publisher_id}")

    echo_success(f"Publisher {publisher_id} deleted.")


@publishers_app.command("apps")
def publisher_apps(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(..., help="Numeric publisher ID to list apps for."),
) -> None:
    """List private apps associated with a publisher.

    Queries GET /api/v2/infrastructure/publishers/{id}/apps.

    Examples:
        netskope npa publishers apps 42
        netskope -o json npa publishers apps 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching apps for publisher {publisher_id}..."):
        data = client.request("GET", f"/api/v2/infrastructure/publishers/{publisher_id}/apps")

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"Apps for Publisher {publisher_id}",
        default_fields=["app_name", "app_id", "host", "protocol"],
    )


@publishers_app.command("registration-token")
def registration_token(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(..., help="Numeric publisher ID to generate a registration token for."),
) -> None:
    """Generate a registration token for a publisher.

    Sends POST /api/v2/infrastructure/publishers/{id}/registration_token.

    Examples:
        netskope npa publishers registration-token 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Generating registration token for publisher {publisher_id}..."):
        data = client.request("POST", f"/api/v2/infrastructure/publishers/{publisher_id}/registration_token")

    echo_success(f"Registration token generated for publisher {publisher_id}.")
    formatter.format_output(data, fmt=fmt, title=f"Registration Token (Publisher {publisher_id})")


@publishers_app.command("releases")
def list_releases(
    ctx: typer.Context,
) -> None:
    """List available publisher software releases.

    Queries GET /api/v2/infrastructure/publishers/releases.

    Examples:
        netskope npa publishers releases
        netskope -o json npa publishers releases
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching publisher releases..."):
        data = client.request("GET", "/api/v2/infrastructure/publishers/releases")

    formatter.format_output(
        data,
        fmt=fmt,
        title="Publisher Releases",
        default_fields=["version", "docker_tag", "release_type", "is_recommended"],
    )


@publishers_app.command("upgrade")
def upgrade_publishers(
    ctx: typer.Context,
    publisher_ids: str = typer.Option(
        ...,
        "--publisher-ids",
        help="Comma-separated list of publisher IDs to upgrade.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt. Required for non-interactive use.",
    ),
) -> None:
    """Trigger a bulk upgrade for one or more publishers.

    Sends PUT /api/v2/infrastructure/publishers/bulk with an upgrade request
    for the specified publisher IDs.

    Examples:
        netskope npa publishers upgrade --publisher-ids 1,2,3 --yes
    """
    ids = _parse_comma_sep_ints(publisher_ids)
    if not ids:
        from netskope_cli.core.output import echo_error

        echo_error("No publisher IDs provided.")
        raise typer.Exit(code=1)

    console = _get_console(ctx)
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to upgrade publishers {ids}?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {
        "publishers": {
            "apply": {"upgrade_request": True},
            "id": ids,
        }
    }

    with spinner("Triggering publisher upgrade..."):
        data = client.request("PUT", "/api/v2/infrastructure/publishers/bulk", json_data=payload)

    echo_success(f"Upgrade triggered for publishers {ids}.")
    formatter.format_output(data, fmt=fmt, title="Publisher Upgrade")
