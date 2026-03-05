"""NPA private application tag commands for the Netskope CLI.

Provides subcommands for managing tags on NPA private applications including
CRUD operations, bulk add/replace/remove, and policy-in-use checks.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
    _parse_comma_sep,
    _parse_comma_sep_ints,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------

tags_app = typer.Typer(name="tags", help="Manage private application tags.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@tags_app.command("list")
def tags_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(None, "--limit", help="Maximum number of tags to return."),
    offset: Optional[int] = typer.Option(None, "--offset", help="Number of records to skip for pagination."),
    query: Optional[str] = typer.Option(None, "--query", help="Search query string to filter tags."),
    count: bool = typer.Option(False, "--count", help="Print only the total count of matching tags."),
) -> None:
    """List private application tags.

    Queries GET /api/v2/steering/apps/private/tags.

    Examples:
        netskope npa tags list
        netskope npa tags list --limit 50 --query web
        netskope -o json npa tags list --count
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj
    no_color = state.no_color if state is not None else False

    params: dict[str, str | int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if query is not None:
        params["query"] = query

    with spinner("Fetching tags...", no_color=no_color):
        data = client.request("GET", "/api/v2/steering/apps/private/tags", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Private Application Tags",
        default_fields=["tag_id", "tag_name"],
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@tags_app.command("get")
def tags_get(
    ctx: typer.Context,
    tag_id: int = typer.Argument(..., help="The unique ID of the tag to retrieve."),
) -> None:
    """Retrieve details of a single tag by ID.

    Queries GET /api/v2/steering/apps/private/tags/{id}.

    Examples:
        netskope npa tags get 42
        netskope -o json npa tags get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching tag {tag_id}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/steering/apps/private/tags/{tag_id}")

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"NPA Tag {tag_id}",
    )


@tags_app.command("create")
def tags_create(
    ctx: typer.Context,
    app_id: str = typer.Option(..., "--app-id", help="The application ID to associate the tags with."),
    tags: str = typer.Option(..., "--tags", help="Comma-separated list of tag names to create."),
) -> None:
    """Create tags on a private application.

    Sends POST /api/v2/steering/apps/private/tags.

    Examples:
        netskope npa tags create --app-id 123 --tags web,production
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    tag_names = _parse_comma_sep(tags)
    if not tag_names:
        echo_error("No tag names provided.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"id": app_id, "tags": [{"tag_name": t} for t in tag_names]}

    with spinner("Creating tags...", no_color=no_color):
        data = client.request("POST", "/api/v2/steering/apps/private/tags", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA Tags — Created",
            default_fields=["tag_id", "tag_name"],
        )
    else:
        echo_success("Tags created successfully.", no_color=no_color)


@tags_app.command("update")
def tags_update(
    ctx: typer.Context,
    tag_id: int = typer.Argument(..., help="The unique ID of the tag to update."),
    tag_name: str = typer.Option(..., "--tag-name", help="The new name for the tag."),
) -> None:
    """Update an existing tag.

    Sends PUT /api/v2/steering/apps/private/tags/{id}.

    Examples:
        netskope npa tags update 42 --tag-name new-name
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    payload = {"tag_name": tag_name}

    with spinner(f"Updating tag {tag_id}...", no_color=no_color):
        data = client.request("PUT", f"/api/v2/steering/apps/private/tags/{tag_id}", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title=f"NPA Tag {tag_id} — Updated",
            default_fields=["tag_id", "tag_name"],
        )
    else:
        echo_success(f"Tag {tag_id} updated successfully.", no_color=no_color)


@tags_app.command("delete")
def tags_delete(
    ctx: typer.Context,
    tag_id: int = typer.Argument(..., help="The unique ID of the tag to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a tag.

    Sends DELETE /api/v2/steering/apps/private/tags/{id}.

    Examples:
        netskope npa tags delete 42
        netskope npa tags delete 42 --yes
    """
    client = _build_client(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    _confirm_delete("tag", tag_id, yes, ctx)

    with spinner(f"Deleting tag {tag_id}...", no_color=no_color):
        client.request("DELETE", f"/api/v2/steering/apps/private/tags/{tag_id}")

    echo_success(f"Tag {tag_id} deleted successfully.", no_color=no_color)


@tags_app.command("add")
def tags_add(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of application IDs."),
    tags: str = typer.Option(..., "--tags", help="Comma-separated list of tag names to add."),
) -> None:
    """Add tags to multiple private applications.

    Sends PATCH /api/v2/steering/apps/private/tags.

    Examples:
        netskope npa tags add --app-ids 123,456 --tags web,production
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_ids_list = _parse_comma_sep(app_ids)
    tag_names = _parse_comma_sep(tags)
    if not app_ids_list or not tag_names:
        echo_error("Both --app-ids and --tags are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": app_ids_list, "tags": [{"tag_name": t} for t in tag_names]}

    with spinner("Adding tags...", no_color=no_color):
        data = client.request("PATCH", "/api/v2/steering/apps/private/tags", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA Tags — Added",
        )
    else:
        echo_success("Tags added successfully.", no_color=no_color)


@tags_app.command("replace")
def tags_replace(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of application IDs."),
    tags: str = typer.Option(..., "--tags", help="Comma-separated list of tag names to set."),
) -> None:
    """Replace all tags on multiple private applications.

    Sends PUT /api/v2/steering/apps/private/tags.

    Examples:
        netskope npa tags replace --app-ids 123,456 --tags web,staging
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_ids_list = _parse_comma_sep(app_ids)
    tag_names = _parse_comma_sep(tags)
    if not app_ids_list or not tag_names:
        echo_error("Both --app-ids and --tags are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": app_ids_list, "tags": [{"tag_name": t} for t in tag_names]}

    with spinner("Replacing tags...", no_color=no_color):
        data = client.request("PUT", "/api/v2/steering/apps/private/tags", json_data=payload)

    if data is not None:
        formatter.format_output(
            data,
            fmt=fmt,
            title="NPA Tags — Replaced",
        )
    else:
        echo_success("Tags replaced successfully.", no_color=no_color)


@tags_app.command("remove")
def tags_remove(
    ctx: typer.Context,
    app_ids: str = typer.Option(..., "--app-ids", help="Comma-separated list of application IDs."),
    tags: str = typer.Option(..., "--tags", help="Comma-separated list of tag names to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove tags from multiple private applications.

    Sends DELETE /api/v2/steering/apps/private/tags with a JSON body.

    Examples:
        netskope npa tags remove --app-ids 123,456 --tags web,staging
        netskope npa tags remove --app-ids 123 --tags old-tag --yes
    """
    client = _build_client(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    app_ids_list = _parse_comma_sep(app_ids)
    tag_names = _parse_comma_sep(tags)
    if not app_ids_list or not tag_names:
        echo_error("Both --app-ids and --tags are required and must not be empty.", no_color=no_color)
        raise typer.Exit(code=1)

    _confirm_delete("tags", tags, yes, ctx)

    payload = {"ids": app_ids_list, "tags": [{"tag_name": t} for t in tag_names]}

    with spinner("Removing tags...", no_color=no_color):
        client.request("DELETE", "/api/v2/steering/apps/private/tags", json_data=payload)

    echo_success("Tags removed successfully.", no_color=no_color)


@tags_app.command("policy-check")
def tags_policy_check(
    ctx: typer.Context,
    ids: str = typer.Option(..., "--ids", help="Comma-separated list of tag IDs to check."),
) -> None:
    """Check which policies reference the specified tags.

    Sends POST /api/v2/steering/apps/private/tags/getpolicyinuse.

    Examples:
        netskope npa tags policy-check --ids 42,99
        netskope -o json npa tags policy-check --ids 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    tag_ids = _parse_comma_sep_ints(ids)
    if not tag_ids:
        echo_error("No valid IDs provided.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": tag_ids}
    with spinner("Checking policy usage...", no_color=no_color):
        data = client.request("POST", "/api/v2/steering/apps/private/tags/getpolicyinuse", json_data=payload)

    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Tags — Policy Check",
    )
