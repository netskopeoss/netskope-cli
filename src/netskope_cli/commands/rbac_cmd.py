"""Role-Based Access Control (RBAC) commands for the Netskope CLI.

Provides subcommands for managing RBAC roles and listing admin users in
your Netskope tenant.  Use these commands to audit who has access to what,
create custom roles with fine-grained permissions, and clean up stale roles.
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

rbac_app = typer.Typer(
    name="rbac",
    help="Role-Based Access Control — manage roles and admin users.",
    no_args_is_help=True,
)

_roles_app = typer.Typer(
    name="roles",
    help="Create, inspect, and delete RBAC roles.",
    no_args_is_help=True,
)

_admins_app = typer.Typer(
    name="admins",
    help="List and inspect admin users.",
    no_args_is_help=True,
)

rbac_app.add_typer(_roles_app, name="roles")
rbac_app.add_typer(_admins_app, name="admins")


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
# Roles commands
# ---------------------------------------------------------------------------


@_roles_app.command("list")
def roles_list(ctx: typer.Context) -> None:
    """List all RBAC roles defined in your Netskope tenant.

    Queries GET /api/v2/rbac/roles and returns every role, including
    built-in system roles and custom roles created by administrators.
    Use this command to audit which roles exist before assigning them
    to admin users or to verify that a newly created role appears.

    Examples:
        # List all roles as a table (default output)
        netskope rbac roles list

        # Output roles as JSON for scripting
        netskope -o json rbac roles list

        # List roles for a non-default profile
        netskope --profile staging rbac roles list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching RBAC roles...", no_color=no_color):
        data = client.request("GET", "/api/v2/rbac/roles")

    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="RBAC Roles",
        default_fields=["name", "type", "description", "scope"],
    )


@_roles_app.command("get")
def roles_get(
    ctx: typer.Context,
    role_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the role to retrieve. "
            "You can find role IDs by running 'netskope rbac roles list'."
        ),
    ),
) -> None:
    """Get detailed information about a specific RBAC role.

    Queries GET /api/v2/rbac/roles/{id} and returns the full role
    definition including its name, description, and the complete list
    of permissions assigned to it.  Use this to inspect a role before
    modifying or deleting it, or to compare permissions across roles.

    Examples:
        # Get details for role ID 42
        netskope rbac roles get 42

        # Output as YAML for readability
        netskope -o yaml rbac roles get 42
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching role {role_id}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/rbac/roles/{role_id}")

    formatter.format_output(data, fmt=_get_output_format(ctx), title=f"RBAC Role {role_id}")


@_roles_app.command("create")
def roles_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        help=(
            "Human-readable name for the new role.  Must be unique within the "
            "tenant.  Choose a descriptive name like 'SOC-Analyst-ReadOnly' so "
            "that its purpose is immediately clear."
        ),
    ),
    permissions: str = typer.Option(
        ...,
        "--permissions",
        help=(
            "Comma-separated list of permission strings to grant to this role. "
            "Each permission maps to a specific API scope or UI capability in "
            "the Netskope console.  Example: 'alerts:read,policy:read,events:read'."
        ),
    ),
) -> None:
    """Create a new custom RBAC role with the specified permissions.

    Sends POST /api/v2/rbac/roles to create a new role.  Custom roles
    let you implement least-privilege access for administrators by
    granting only the permissions they need.  Once created, the role
    can be assigned to admin users via the Netskope console or API.

    Examples:
        # Create a read-only analyst role
        netskope rbac roles create --name "SOC-Analyst" --permissions "alerts:read,events:read"

        # Create a policy-admin role
        netskope rbac roles create --name "Policy-Admin" --permissions "policy:read,policy:write"

        # Create a role and output the result as JSON
        netskope -o json rbac roles create --name "Auditor" --permissions "reports:read"
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]

    body: dict[str, object] = {
        "name": name,
        "permissions": perm_list,
    }

    with spinner("Creating role...", no_color=no_color):
        data = client.request("POST", "/api/v2/rbac/roles", json_data=body)

    echo_success(f"Role '{name}' created.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title="Created Role")


@_roles_app.command("update")
def roles_update(
    ctx: typer.Context,
    role_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the role to update. "
            "You can find role IDs by running 'netskope rbac roles list'."
        ),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="New display name for the role.",
    ),
    permissions: Optional[str] = typer.Option(
        None,
        "--permissions",
        help=(
            "Comma-separated list of permission strings. This REPLACES the "
            "current permissions. Example: 'alerts:read,policy:read,events:read'."
        ),
    ),
) -> None:
    """Update an RBAC role's name or permissions.

    Sends PUT /api/v2/rbac/roles/{id} with the provided changes. At least
    one of --name or --permissions must be specified. Permission lists are
    fully replaced, not merged.

    Examples:
        netskope rbac roles update 42 --name "Updated Role Name"
        netskope rbac roles update 42 --permissions "alerts:read,events:read"
        netskope -o json rbac roles update 42 --name "SOC-Analyst-v2"
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    body: dict[str, object] = {}
    if name is not None:
        body["name"] = name
    if permissions is not None:
        body["permissions"] = [p.strip() for p in permissions.split(",") if p.strip()]

    if not body:
        typer.echo("Nothing to update. Provide --name and/or --permissions.", err=True)
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _build_formatter(ctx)

    with spinner(f"Updating role {role_id}...", no_color=no_color):
        data = client.request("PUT", f"/api/v2/rbac/roles/{role_id}", json_data=body)

    echo_success(f"Role {role_id} updated.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title=f"Updated Role {role_id}")


@_roles_app.command("delete")
def roles_delete(
    ctx: typer.Context,
    role_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the role to delete. "
            "You can find role IDs by running 'netskope rbac roles list'."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and immediately delete "
            "the role.  Useful for scripted or CI/CD workflows where no "
            "terminal is available for user input."
        ),
    ),
) -> None:
    """Delete an RBAC role by its ID.

    Sends DELETE /api/v2/rbac/roles/{id} to permanently remove a custom
    role.  Built-in system roles cannot be deleted.  Any admin users
    currently assigned to the deleted role will lose those permissions,
    so verify role assignments before proceeding.

    Examples:
        # Delete role 42 (will prompt for confirmation)
        netskope rbac roles delete 42

        # Delete role 42 without confirmation
        netskope rbac roles delete 42 --yes

        # Delete from a specific profile
        netskope --profile staging rbac roles delete 99 -y
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if not yes:
        typer.confirm(
            f"Are you sure you want to delete role {role_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    with spinner(f"Deleting role {role_id}...", no_color=no_color):
        client.request("DELETE", f"/api/v2/rbac/roles/{role_id}")

    echo_success(f"Role {role_id} deleted.", no_color=no_color)


# ---------------------------------------------------------------------------
# Admins commands
# ---------------------------------------------------------------------------


@_admins_app.command("list")
def admins_list(ctx: typer.Context) -> None:
    """List all admin users in your Netskope tenant.

    Queries GET /api/v2/rbac/admins to retrieve every administrator
    account along with their assigned roles and current status.  This
    is useful for security audits, onboarding reviews, and verifying
    that the right people have administrative access to the tenant.

    Examples:
        # List all admin users
        netskope rbac admins list

        # Output as CSV for a spreadsheet audit
        netskope -o csv rbac admins list

        # Pipe JSON output to jq for filtering
        netskope -o json rbac admins list | jq '.[] | select(.role=="Admin")'
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching admin users...", no_color=no_color):
        data = client.request("GET", "/api/v2/rbac/admins")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="RBAC Admin Users")
