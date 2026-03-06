"""Notification management commands for the Netskope CLI.

Provides subcommands to list, create, and delete notification templates, as
well as retrieve delivery settings via the Netskope notifications API.
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
notifications_app = typer.Typer(
    name="notifications",
    help="Manage notification templates and delivery settings.",
    no_args_is_help=True,
)

_templates_app = typer.Typer(
    name="templates",
    help="Manage user notification templates.",
    no_args_is_help=True,
)
notifications_app.add_typer(_templates_app, name="templates")

_settings_app = typer.Typer(
    name="settings",
    help="View notification delivery settings.",
    no_args_is_help=True,
)
notifications_app.add_typer(_settings_app, name="settings")


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
# Commands — templates list / get / create / delete
# ---------------------------------------------------------------------------


@_templates_app.command("list")
def list_templates(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of templates to return.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Offset for pagination (number of records to skip).",
    ),
) -> None:
    """List all user notification templates.

    Retrieves notification templates configured in the tenant via
    GET /api/v2/notifications/user/templates. Templates define the
    content and format of notifications sent to end users when a policy
    action is triggered.

    Results can be paginated using --limit and --offset.

    Examples:

        # List all notification templates
        netskope notifications templates list

        # List the first 5 templates
        netskope notifications templates list --limit 5

        # Paginate through results
        netskope notifications templates list --limit 10 --offset 10

        # Output as JSON
        netskope -o json notifications templates list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching notification templates..."):
        data = client.request("GET", "/api/v2/notifications/user/templates", params=params or None)

    formatter.format_output(data, fmt=fmt, title="Notification Templates")


@_templates_app.command("get")
def get_template(
    ctx: typer.Context,
    template_id: int = typer.Argument(
        ...,
        help="The unique identifier of the notification template to retrieve.",
    ),
) -> None:
    """Get details of a specific notification template.

    Retrieves a single user notification template by its ID via
    GET /api/v2/notifications/user/templates/{id}. Returns the full
    template definition including name, type, and body content.

    Examples:

        # Get template with ID 42
        netskope notifications templates get 42

        # Output as YAML
        netskope -o yaml notifications templates get 42

        # Output as JSON for scripting
        netskope -o json notifications templates get 100
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching notification template {template_id}..."):
        data = client.request("GET", f"/api/v2/notifications/user/templates/{template_id}")

    formatter.format_output(data, fmt=fmt, title=f"Notification Template {template_id}")


@_templates_app.command("create")
def create_template(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Display name for the new notification template.",
    ),
    template_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Template type (e.g. 'block', 'warn', 'redirect', 'quarantine').",
    ),
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help="HTML or plain-text body content of the notification template.",
    ),
) -> None:
    """Create a new user notification template.

    Creates a notification template via POST /api/v2/notifications/user/templates.
    The template defines the content displayed to end users when a policy
    action such as block, warn, or redirect is triggered.

    The --name, --type, and --body options are all required.

    Examples:

        # Create a simple block notification template
        netskope notifications templates create \\
            --name "Custom Block Page" \\
            --type block \\
            --body "<h1>Access Denied</h1><p>This site is blocked.</p>"

        # Create a warning template
        netskope notifications templates create \\
            --name "DLP Warning" \\
            --type warn \\
            --body "You are about to share sensitive data."

        # Output the created template as JSON
        netskope -o json notifications templates create \\
            --name "Quarantine Notice" \\
            --type quarantine \\
            --body "This file has been quarantined."
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {
        "name": name,
        "type": template_type,
        "body": body,
    }

    with spinner("Creating notification template..."):
        data = client.request("POST", "/api/v2/notifications/user/templates", json_data=payload)

    echo_success(f"Notification template '{name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created Notification Template")


@_templates_app.command("update")
def update_template(
    ctx: typer.Context,
    template_id: int = typer.Argument(
        ...,
        help="The unique identifier of the notification template to update.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="New display name for the notification template.",
    ),
    template_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="New template type (e.g. 'block', 'warn', 'redirect', 'quarantine').",
    ),
    body: Optional[str] = typer.Option(
        None,
        "--body",
        "-b",
        help="New HTML or plain-text body content.",
    ),
) -> None:
    """Update an existing notification template.

    Sends PUT /api/v2/notifications/user/templates/{id} with the provided
    changes. At least one of --name, --type, or --body must be specified.

    Examples:

        # Update template name
        netskope notifications templates update 42 --name "Updated Block Page"

        # Update template body
        netskope notifications templates update 42 \\
            --body "<h1>New Content</h1>"

        # Update multiple fields
        netskope notifications templates update 42 \\
            --name "DLP Warning v2" --type warn --body "Updated warning text."
    """
    payload: dict[str, object] = {}
    if name is not None:
        payload["name"] = name
    if template_type is not None:
        payload["type"] = template_type
    if body is not None:
        payload["body"] = body

    if not payload:
        typer.echo("Nothing to update. Provide --name, --type, and/or --body.", err=True)
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Updating notification template {template_id}..."):
        data = client.request(
            "PUT",
            f"/api/v2/notifications/user/templates/{template_id}",
            json_data=payload,
        )

    echo_success(f"Notification template {template_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated Notification Template {template_id}")


@_templates_app.command("delete")
def delete_template(
    ctx: typer.Context,
    template_id: int = typer.Argument(
        ...,
        help="The unique identifier of the notification template to delete.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt and delete immediately.",
    ),
) -> None:
    """Delete a user notification template.

    Permanently removes a notification template by its ID via
    DELETE /api/v2/notifications/user/templates/{id}. This action
    cannot be undone. Templates that are currently in use by policies
    should be reassigned before deletion.

    A confirmation prompt is shown unless --yes is provided.

    Examples:

        # Delete template 42 (with confirmation prompt)
        netskope notifications templates delete 42

        # Delete template 42 without confirmation
        netskope notifications templates delete 42 --yes

        # Delete template using short flag
        netskope notifications templates delete 99 -y
    """
    console = _get_console(ctx)

    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete notification template {template_id}?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    client = _build_client(ctx)

    with spinner(f"Deleting notification template {template_id}..."):
        client.request("DELETE", f"/api/v2/notifications/user/templates/{template_id}")

    echo_success(f"Notification template {template_id} deleted.")


# ---------------------------------------------------------------------------
# Commands — settings
# ---------------------------------------------------------------------------


@_settings_app.command("get")
def get_delivery_settings(
    ctx: typer.Context,
) -> None:
    """Retrieve notification delivery settings.

    Fetches the current notification delivery settings for the tenant via
    GET /api/v2/notifications/deliverysettings. Delivery settings control
    how and when notifications are sent to users, including email relay
    configuration, sender addresses, and delivery frequency.

    Examples:

        # View delivery settings as a table
        netskope notifications settings get

        # View delivery settings as JSON
        netskope -o json notifications settings get

        # View delivery settings as YAML
        netskope -o yaml notifications settings get
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching notification delivery settings..."):
        data = client.request("GET", "/api/v2/notifications/user/deliverysettings")

    formatter.format_output(data, fmt=fmt, title="Notification Delivery Settings")


# Hidden alias so "notifications settings list" also works.
_settings_app.command("list", hidden=True)(get_delivery_settings)
