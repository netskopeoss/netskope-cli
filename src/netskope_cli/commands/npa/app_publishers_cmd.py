"""NPA app-publisher association commands for the Netskope CLI.

Provides subcommands for managing associations between private applications
and publishers.
"""

from __future__ import annotations

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
    _parse_comma_sep_ints,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------

app_publishers_app = typer.Typer(name="app-publishers", help="Manage app-publisher associations.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app_publishers_app.command("add")
def publishers_add(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of private application IDs."),
    publisher_ids: str = typer.Option(..., "--publisher-ids", help="Comma-separated list of publisher IDs."),
) -> None:
    """Add publisher associations to private applications.

    Sends PATCH /api/v2/steering/apps/private/publishers.

    Examples:
        netskope npa app-publishers add --app-ids 123,456 --publisher-ids 10,20
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_id_list = _parse_comma_sep_ints(app_ids)
    pub_id_list = _parse_comma_sep_ints(publisher_ids)
    if not app_id_list or not pub_id_list:
        echo_error("Both --app-ids and --publisher-ids are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"private_app_ids": app_id_list, "publisher_ids": pub_id_list}

    with spinner("Adding publisher associations...", no_color=no_color):
        data = client.request("PATCH", "/api/v2/steering/apps/private/publishers", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA App-Publisher Associations — Added",
        )
    else:
        echo_success("Publisher associations added successfully.", no_color=no_color)


@app_publishers_app.command("replace")
def publishers_replace(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of private application IDs."),
    publisher_ids: str = typer.Option(..., "--publisher-ids", help="Comma-separated list of publisher IDs."),
) -> None:
    """Replace all publisher associations on private applications.

    Sends PUT /api/v2/steering/apps/private/publishers.

    Examples:
        netskope npa app-publishers replace --app-ids 123,456 --publisher-ids 30,40
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_id_list = _parse_comma_sep_ints(app_ids)
    pub_id_list = _parse_comma_sep_ints(publisher_ids)
    if not app_id_list or not pub_id_list:
        echo_error("Both --app-ids and --publisher-ids are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"private_app_ids": app_id_list, "publisher_ids": pub_id_list}

    with spinner("Replacing publisher associations...", no_color=no_color):
        data = client.request("PUT", "/api/v2/steering/apps/private/publishers", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA App-Publisher Associations — Replaced",
        )
    else:
        echo_success("Publisher associations replaced successfully.", no_color=no_color)


@app_publishers_app.command("remove")
def publishers_remove(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of private application IDs."),
    publisher_ids: str = typer.Option(..., "--publisher-ids", help="Comma-separated list of publisher IDs."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove publisher associations from private applications.

    Sends DELETE /api/v2/steering/apps/private/publishers with a JSON body.

    Examples:
        netskope npa app-publishers remove --app-ids 123 --publisher-ids 10 --yes
    """
    client = _build_client(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_id_list = _parse_comma_sep_ints(app_ids)
    pub_id_list = _parse_comma_sep_ints(publisher_ids)
    if not app_id_list or not pub_id_list:
        echo_error("Both --app-ids and --publisher-ids are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    _confirm_delete("publisher associations", f"apps={app_ids}, publishers={publisher_ids}", yes, ctx)

    payload = {"private_app_ids": app_id_list, "publisher_ids": pub_id_list}

    with spinner("Removing publisher associations...", no_color=no_color):
        client.request("DELETE", "/api/v2/steering/apps/private/publishers", json_data=payload)

    echo_success("Publisher associations removed successfully.", no_color=no_color)
