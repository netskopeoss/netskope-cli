"""NPA private app discovery settings management commands."""

from __future__ import annotations

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _get_formatter,
    _get_output_format,
    _load_json_file,
)
from netskope_cli.core.output import echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
discovery_app = typer.Typer(name="discovery", help="Manage private app discovery settings.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@discovery_app.command("get")
def get_discovery_settings(
    ctx: typer.Context,
) -> None:
    """Retrieve the current private app discovery settings.

    Queries GET /api/v2/steering/apps/private/discoverysettings.

    Examples:
        netskope npa discovery get
        netskope -o json npa discovery get
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching discovery settings..."):
        data = client.request("GET", "/api/v2/steering/apps/private/discoverysettings")

    formatter.format_output(data, fmt=fmt, title="Private App Discovery Settings")


@discovery_app.command("update")
def update_discovery_settings(
    ctx: typer.Context,
    json_file: str = typer.Option(
        ...,
        "--json-file",
        help="Path to a JSON file containing the discovery settings payload. Required because discovery settings "
        "are complex structured objects.",
    ),
) -> None:
    """Update the private app discovery settings.

    Sends POST /api/v2/steering/apps/private/discoverysettings with the contents
    of the provided JSON file.

    Examples:
        netskope npa discovery update --json-file discovery.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload = _load_json_file(json_file)

    with spinner("Updating discovery settings..."):
        data = client.request("POST", "/api/v2/steering/apps/private/discoverysettings", json_data=payload)

    echo_success("Private app discovery settings updated.")
    formatter.format_output(data, fmt=fmt, title="Updated Discovery Settings")
