"""Device enrollment commands for the Netskope CLI.

Provides subcommands to list, create, and delete enrollment token sets
via the Netskope enrollment API. Enrollment tokens are used by the
Netskope Client to authenticate devices during initial registration.
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
enrollment_app = typer.Typer(
    name="enrollment",
    help="Manage device enrollment tokens.",
    no_args_is_help=True,
)

_tokens_app = typer.Typer(
    name="tokens",
    help="Manage enrollment token sets.",
    no_args_is_help=True,
)
enrollment_app.add_typer(_tokens_app, name="tokens")


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
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


# ---------------------------------------------------------------------------
# Commands — tokens list / create / delete
# ---------------------------------------------------------------------------


@_tokens_app.command("list")
def list_tokens(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of token sets to return.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Offset for pagination (number of records to skip).",
    ),
) -> None:
    """List all enrollment token sets.

    Retrieves the enrollment token sets configured for the tenant via
    GET /api/v2/enrollment/tokenset. Enrollment tokens are used by the
    Netskope Client during device registration to authenticate and
    associate the device with the correct tenant and organization unit.

    Each token set includes a name, creation date, usage count, and the
    maximum number of devices that can be enrolled using the token.

    Results can be paginated using --limit and --offset.

    Examples:

        # List all enrollment token sets
        netskope enrollment tokens list

        # List the first 5 token sets
        netskope enrollment tokens list --limit 5

        # Paginate through results
        netskope enrollment tokens list --limit 10 --offset 10

        # Output as JSON for scripting
        netskope -o json enrollment tokens list

        # Output as CSV for spreadsheet import
        netskope -o csv enrollment tokens list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching enrollment token sets..."):
        data = client.request("GET", "/api/v2/enrollment/tokenset", params=params or None)

    formatter.format_output(data, fmt=fmt, title="Enrollment Token Sets")


@_tokens_app.command("create")
def create_token(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Display name for the new enrollment token set.",
    ),
    max_devices: Optional[int] = typer.Option(
        None,
        "--max-devices",
        "-m",
        help="Maximum number of devices that can enroll using this token set. " "Omit for unlimited enrollments.",
    ),
) -> None:
    """Create a new enrollment token set.

    Creates an enrollment token set via POST /api/v2/enrollment/tokenset.
    The token set is used by the Netskope Client during device enrollment.
    Each token set has a name and an optional maximum device limit that
    controls how many devices can register using the token.

    The --name option is required. Use --max-devices to cap the number
    of devices that can enroll with this token; omit it for unlimited
    enrollments.

    Examples:

        # Create a token set with no device limit
        netskope enrollment tokens create --name "Engineering Team"

        # Create a token set limited to 100 devices
        netskope enrollment tokens create --name "Contractors" --max-devices 100

        # Create a token set with short flags
        netskope enrollment tokens create -n "Sales Org" -m 50

        # Output the created token set as JSON
        netskope -o json enrollment tokens create --name "QA Lab" --max-devices 25
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {
        "name": name,
    }
    if max_devices is not None:
        payload["max_devices"] = max_devices

    with spinner("Creating enrollment token set..."):
        data = client.request("POST", "/api/v2/enrollment/tokenset", json_data=payload)

    echo_success(f"Enrollment token set '{name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created Enrollment Token Set")


@_tokens_app.command("delete")
def delete_token(
    ctx: typer.Context,
    token_id: int = typer.Argument(
        ...,
        help="The unique identifier of the enrollment token set to delete.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt and delete immediately.",
    ),
) -> None:
    """Delete an enrollment token set.

    Permanently removes an enrollment token set by its ID via
    DELETE /api/v2/enrollment/tokenset/{id}. Devices that were already
    enrolled using this token will not be affected, but no new devices
    can enroll with the deleted token.

    A confirmation prompt is shown unless --yes is provided.

    Examples:

        # Delete token set 7 (with confirmation prompt)
        netskope enrollment tokens delete 7

        # Delete token set 7 without confirmation
        netskope enrollment tokens delete 7 --yes

        # Delete using short flag
        netskope enrollment tokens delete 15 -y
    """
    console = _get_console(ctx)

    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete enrollment token set {token_id}?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    client = _build_client(ctx)

    with spinner(f"Deleting enrollment token set {token_id}..."):
        client.request("DELETE", f"/api/v2/enrollment/tokenset/{token_id}")

    echo_success(f"Enrollment token set {token_id} deleted.")
