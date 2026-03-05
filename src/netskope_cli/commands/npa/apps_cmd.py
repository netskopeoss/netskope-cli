"""NPA private application commands for the Netskope CLI.

Provides subcommands for managing NPA private applications including CRUD
operations, bulk delete, and policy-in-use checks.
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
    _load_json_file,
    _parse_comma_sep_ints,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------

apps_app = typer.Typer(name="apps", help="Manage NPA private applications.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@apps_app.command("list")
def apps_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(None, "--limit", help="Maximum number of applications to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of records to skip for pagination."),
    query: Optional[str] = typer.Option(None, "--query", help="Search query string to filter applications."),
    app_name: Optional[str] = typer.Option(None, "--app-name", help="Filter by application name."),
    publisher_name: Optional[str] = typer.Option(None, "--publisher-name", help="Filter by publisher name."),
    reachable: Optional[bool] = typer.Option(None, "--reachable", help="Filter by reachability status."),
    clientless_access: Optional[bool] = typer.Option(
        None, "--clientless-access", help="Filter by clientless access enabled/disabled."
    ),
    host: Optional[str] = typer.Option(None, "--host", help="Filter by host name."),
    in_policy: Optional[bool] = typer.Option(None, "--in-policy", help="Filter by whether the app is in a policy."),
    protocol: Optional[str] = typer.Option(None, "--protocol", help="Filter by protocol (e.g. tcp, udp)."),
    fields: Optional[str] = typer.Option(
        None, "--fields", "-f", help="Comma-separated list of field names to include."
    ),
    count: bool = typer.Option(False, "--count", help="Print only the total count of matching applications."),
) -> None:
    """List NPA private applications.

    Queries GET /api/v2/steering/apps/private to retrieve private applications
    with optional filtering.

    Examples:
        netskope npa apps list
        netskope npa apps list --limit 20 --app-name myapp
        netskope -o json npa apps list --count
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj
    no_color = state.no_color if state is not None else False

    params: dict[str, str | int | bool] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if query is not None:
        params["query"] = query
    if app_name is not None:
        params["app_name"] = app_name
    if publisher_name is not None:
        params["publisher_name"] = publisher_name
    if reachable is not None:
        params["reachable"] = reachable
    if clientless_access is not None:
        params["clientless_access"] = clientless_access
    if host is not None:
        params["host"] = host
    if in_policy is not None:
        params["in_policy"] = in_policy
    if protocol is not None:
        params["protocol"] = protocol

    with spinner("Fetching private applications...", no_color=no_color):
        data = client.request("GET", "/api/v2/steering/apps/private", params=params or None)

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Private Applications",
        default_fields=["app_name", "app_id", "host", "clientless_access", "use_publisher_dns"],
        fields=field_list,
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@apps_app.command("get")
def apps_get(
    ctx: typer.Context,
    app_id: int = typer.Argument(..., help="The unique ID of the private application to retrieve."),
) -> None:
    """Retrieve details of a single private application by ID.

    Queries GET /api/v2/steering/apps/private/{id}.

    Examples:
        netskope npa apps get 12345
        netskope -o json npa apps get 12345
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching private application {app_id}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/steering/apps/private/{app_id}")

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"NPA Private Application {app_id}",
    )


@apps_app.command("create")
def apps_create(
    ctx: typer.Context,
    app_name: Optional[str] = typer.Option(
        None, "--app-name", help="Name of the private application (required unless --json-file)."
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Hostname for the application (required unless --json-file)."
    ),
    protocols: Optional[str] = typer.Option(
        None, "--protocols", help='JSON array of protocol objects, e.g. \'[{"type":"tcp","port":"443"}]\'.'
    ),
    clientless_access: Optional[bool] = typer.Option(
        None, "--clientless-access", help="Enable or disable clientless access."
    ),
    use_publisher_dns: Optional[bool] = typer.Option(None, "--use-publisher-dns", help="Use publisher DNS resolution."),
    trust_self_signed_certs: Optional[bool] = typer.Option(
        None, "--trust-self-signed-certs", help="Trust self-signed certificates."
    ),
    publishers: Optional[str] = typer.Option(
        None, "--publishers", help='JSON array of publisher objects, e.g. \'[{"publisher_id":"123"}]\'.'
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", help='JSON array of tag objects, e.g. \'[{"tag_name":"web"}]\'.'
    ),
    json_file: Optional[str] = typer.Option(
        None, "--json-file", help="Path to a JSON file containing the full application payload."
    ),
) -> None:
    """Create a new NPA private application.

    Sends POST /api/v2/steering/apps/private. Provide options individually or
    supply a complete payload via --json-file.

    Examples:
        netskope npa apps create --app-name myapp --host internal.example.com
        netskope npa apps create --json-file app.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if json_file:
        payload = _load_json_file(json_file)
    else:
        if not app_name:
            echo_error("--app-name is required when not using --json-file.", no_color=no_color)
            raise typer.Exit(code=1)
        if not host:
            echo_error("--host is required when not using --json-file.", no_color=no_color)
            raise typer.Exit(code=1)

        payload: dict = {"app_name": app_name, "host": host}
        if protocols is not None:
            try:
                payload["protocols"] = json.loads(protocols)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --protocols: {exc}")
        if clientless_access is not None:
            payload["clientless_access"] = clientless_access
        if use_publisher_dns is not None:
            payload["use_publisher_dns"] = use_publisher_dns
        if trust_self_signed_certs is not None:
            payload["trust_self_signed_certs"] = trust_self_signed_certs
        if publishers is not None:
            try:
                payload["publishers"] = json.loads(publishers)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --publishers: {exc}")
        if tags is not None:
            try:
                payload["tags"] = json.loads(tags)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --tags: {exc}")

    with spinner("Creating private application...", no_color=no_color):
        data = client.request("POST", "/api/v2/steering/apps/private", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA Private Application — Created",
            default_fields=["app_name", "app_id", "host"],
        )
    else:
        echo_success("Private application created successfully.", no_color=no_color)


@apps_app.command("update")
def apps_update(
    ctx: typer.Context,
    app_id: int = typer.Argument(..., help="The unique ID of the private application to update."),
    app_name: Optional[str] = typer.Option(None, "--app-name", help="Updated application name."),
    host: Optional[str] = typer.Option(None, "--host", help="Updated hostname."),
    protocols: Optional[str] = typer.Option(
        None, "--protocols", help='JSON array of protocol objects, e.g. \'[{"type":"tcp","port":"443"}]\'.'
    ),
    clientless_access: Optional[bool] = typer.Option(
        None, "--clientless-access", help="Enable or disable clientless access."
    ),
    use_publisher_dns: Optional[bool] = typer.Option(None, "--use-publisher-dns", help="Use publisher DNS resolution."),
    trust_self_signed_certs: Optional[bool] = typer.Option(
        None, "--trust-self-signed-certs", help="Trust self-signed certificates."
    ),
    publishers: Optional[str] = typer.Option(
        None, "--publishers", help='JSON array of publisher objects, e.g. \'[{"publisher_id":"123"}]\'.'
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", help='JSON array of tag objects, e.g. \'[{"tag_name":"web"}]\'.'
    ),
    json_file: Optional[str] = typer.Option(
        None, "--json-file", help="Path to a JSON file containing the update payload."
    ),
) -> None:
    """Update an existing NPA private application.

    Sends PATCH /api/v2/steering/apps/private/{id}. Only provided fields are
    updated.

    Examples:
        netskope npa apps update 12345 --app-name new-name
        netskope npa apps update 12345 --json-file update.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if json_file:
        payload = _load_json_file(json_file)
    else:
        payload: dict = {}
        if app_name is not None:
            payload["app_name"] = app_name
        if host is not None:
            payload["host"] = host
        if protocols is not None:
            try:
                payload["protocols"] = json.loads(protocols)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --protocols: {exc}")
        if clientless_access is not None:
            payload["clientless_access"] = clientless_access
        if use_publisher_dns is not None:
            payload["use_publisher_dns"] = use_publisher_dns
        if trust_self_signed_certs is not None:
            payload["trust_self_signed_certs"] = trust_self_signed_certs
        if publishers is not None:
            try:
                payload["publishers"] = json.loads(publishers)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --publishers: {exc}")
        if tags is not None:
            try:
                payload["tags"] = json.loads(tags)
            except json.JSONDecodeError as exc:
                raise typer.BadParameter(f"Invalid JSON for --tags: {exc}")

        if not payload:
            echo_error("No update fields provided. Use options or --json-file.", no_color=no_color)
            raise typer.Exit(code=1)

    with spinner(f"Updating private application {app_id}...", no_color=no_color):
        data = client.request("PATCH", f"/api/v2/steering/apps/private/{app_id}", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title=f"NPA Private Application {app_id} — Updated",
            default_fields=["app_name", "app_id", "host"],
        )
    else:
        echo_success(f"Private application {app_id} updated successfully.", no_color=no_color)


@apps_app.command("delete")
def apps_delete(
    ctx: typer.Context,
    app_id: int = typer.Argument(..., help="The unique ID of the private application to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete an NPA private application.

    Sends DELETE /api/v2/steering/apps/private/{id}.

    Examples:
        netskope npa apps delete 12345
        netskope npa apps delete 12345 --yes
    """
    client = _build_client(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    _confirm_delete("private application", app_id, yes, ctx)

    with spinner(f"Deleting private application {app_id}...", no_color=no_color):
        client.request("DELETE", f"/api/v2/steering/apps/private/{app_id}")

    echo_success(f"Private application {app_id} deleted successfully.", no_color=no_color)


@apps_app.command("bulk-delete")
def apps_bulk_delete(
    ctx: typer.Context,
    ids: str = typer.Option(..., "--ids", help="Comma-separated list of private application IDs to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Bulk delete NPA private applications.

    Sends DELETE /api/v2/steering/apps/private with a list of application IDs.

    Examples:
        netskope npa apps bulk-delete --ids 123,456,789
        netskope npa apps bulk-delete --ids 123,456 --yes
    """
    client = _build_client(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_ids = _parse_comma_sep_ints(ids)
    if not app_ids:
        echo_error("No valid IDs provided.", no_color=no_color)
        raise typer.Exit(code=1)

    _confirm_delete("private applications", ids, yes, ctx)

    payload = {"private_app_ids": app_ids}
    with spinner("Deleting private applications...", no_color=no_color):
        client.request("DELETE", "/api/v2/steering/apps/private", json_data=payload)

    echo_success(f"Deleted private applications: {ids}", no_color=no_color)


@apps_app.command("policy-check")
def apps_policy_check(
    ctx: typer.Context,
    ids: str = typer.Option(..., "--ids", help="Comma-separated list of private application IDs to check."),
) -> None:
    """Check which policies reference the specified private applications.

    Sends POST /api/v2/steering/apps/private/getpolicyinuse.

    Examples:
        netskope npa apps policy-check --ids 123,456
        netskope -o json npa apps policy-check --ids 123
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_ids = _parse_comma_sep_ints(ids)
    if not app_ids:
        echo_error("No valid IDs provided.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": app_ids}
    with spinner("Checking policy usage...", no_color=no_color):
        data = client.request("POST", "/api/v2/steering/apps/private/getpolicyinuse", json_data=payload)

    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Private Applications — Policy Check",
    )
