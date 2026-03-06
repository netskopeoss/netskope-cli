"""SCIM user and group management commands for the Netskope CLI.

Provides subcommands for managing users and groups via the Netskope SCIM v2
API endpoints (/api/v2/scim/Users and /api/v2/scim/Groups).
"""

from __future__ import annotations

from typing import Any, Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import ValidationError
from netskope_cli.core.output import OutputFormatter, echo_success

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

groups_app = typer.Typer(
    name="groups",
    help=(
        "Create, list, update, and delete SCIM v2 groups.\n\n"
        "Groups organize users for policy targeting. Manage group membership to "
        "control which security policies apply to which sets of users. Groups are "
        "provisioned via the SCIM /api/v2/scim/Groups endpoints."
    ),
    no_args_is_help=True,
)

users_app = typer.Typer(
    name="users",
    help=(
        "Provision and manage SCIM v2 users and groups.\n\n"
        "This command group provides full CRUD operations for user and group "
        "identities via the Netskope SCIM v2 API. Use these commands to provision "
        "users from your identity provider, manage group membership for policy "
        "targeting, and automate user lifecycle operations."
    ),
    no_args_is_help=True,
)

users_app.add_typer(groups_app, name="groups", help="Manage SCIM groups.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an OutputFormatter that respects the global --no-color flag."""
    state = ctx.obj
    no_color = state.no_color if state else False
    count_only = getattr(state, "count", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the user-selected output format string."""
    state = ctx.obj
    return state.output.value if state else "table"


def _is_raw(ctx: typer.Context) -> bool:
    """Return True if the user requested raw (unprocessed) output."""
    state = ctx.obj
    return state.raw if state else False


def _simplify_scim_user(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten a single SCIM user record for human-friendly output."""
    simplified: dict[str, Any] = {}

    # Preserve well-known top-level keys
    for key in ("id", "userName", "active", "displayName", "externalId", "groups"):
        if key in record:
            simplified[key] = record[key]

    # Flatten name dict
    name = record.get("name")
    if isinstance(name, dict):
        if "givenName" in name:
            simplified["givenName"] = name["givenName"]
        if "familyName" in name:
            simplified["familyName"] = name["familyName"]

    # Flatten emails list to primary email string
    emails = record.get("emails")
    if isinstance(emails, list):
        primary = next(
            (e.get("value") for e in emails if isinstance(e, dict) and e.get("primary")),
            None,
        )
        if primary is None and emails:
            first = emails[0]
            primary = first.get("value") if isinstance(first, dict) else None
        if primary:
            simplified["email"] = primary

    # Flatten SCIM extension keys (urn:ietf:params:scim:*) up one level
    for key, value in record.items():
        if key.startswith("urn:") and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                simplified[sub_key] = sub_value

    return simplified


def _simplify_scim_users(data: Any) -> Any:
    """Simplify SCIM user response data, handling both list and single record."""
    if isinstance(data, dict):
        # SCIM list response has a "Resources" key
        if "Resources" in data:
            data["Resources"] = [_simplify_scim_user(r) for r in data["Resources"] if isinstance(r, dict)]
            return data
        # Single user record (has "userName" or "schemas" hint)
        if "userName" in data or "schemas" in data:
            return _simplify_scim_user(data)
    if isinstance(data, list):
        return [_simplify_scim_user(r) for r in data if isinstance(r, dict)]
    return data


def _simplify_scim_group(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten a single SCIM group record for human-friendly output."""
    simplified: dict[str, Any] = {}

    for key in ("id", "displayName"):
        if key in record:
            simplified[key] = record[key]

    members = record.get("members")
    if isinstance(members, list):
        simplified["member_count"] = len(members)
    else:
        simplified["member_count"] = 0

    return simplified


def _simplify_scim_groups(data: Any) -> Any:
    """Simplify SCIM group response data, handling both list and single record."""
    if isinstance(data, dict):
        if "Resources" in data:
            data["Resources"] = [_simplify_scim_group(r) for r in data["Resources"] if isinstance(r, dict)]
            return data
        if "displayName" in data or "schemas" in data:
            return _simplify_scim_group(data)
    if isinstance(data, list):
        return [_simplify_scim_group(r) for r in data if isinstance(r, dict)]
    return data


def _parse_set_options(values: list[str]) -> dict[str, Any]:
    """Parse a list of ``key=value`` strings into a dict.

    Raises ValidationError if any entry is malformed.
    """
    result: dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise ValidationError(
                f"Invalid --set value '{item}'. Expected format: key=value",
            )
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        # Attempt basic type coercion
        if value.lower() == "true":
            result[key] = True
        elif value.lower() == "false":
            result[key] = False
        else:
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------


@users_app.command("list")
def user_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "SCIM filter expression to narrow results. Uses SCIM 2.0 filter syntax. "
            "For example: 'userName eq \"user@example.com\"' or 'active eq true'. "
            "Omit to return all users."
        ),
    ),
    count: int = typer.Option(
        100,
        "--limit",
        "--count",
        help=(
            "Number of user records to return per page. Use with --start-index for "
            "pagination through large user directories. Defaults to 100. "
            "The API may enforce an upper bound."
        ),
    ),
    start_index: int = typer.Option(
        1,
        "--start-index",
        "--offset",
        help=(
            "1-based index of the first result to return. Use with --count for "
            "pagination. For example, --start-index 101 --count 100 returns users "
            "101-200. Defaults to 1."
        ),
    ),
) -> None:
    """List SCIM users with optional filtering and pagination.

    Queries GET /api/v2/scim/Users to retrieve provisioned user identities.
    Use SCIM filter expressions to find specific users. This is useful for
    auditing user accounts, verifying provisioning, and automation workflows.

    Examples:
        netskope users list
        netskope users list --filter 'userName eq "alice@example.com"'
        netskope -o json users list --filter 'active eq true' --count 50
    """
    client = _build_client(ctx)
    params: dict[str, Any] = {
        "count": count,
        "startIndex": start_index,
    }
    if filter_:
        params["filter"] = filter_

    data = client.request("GET", "/api/v2/scim/Users", params=params)

    if not _is_raw(ctx):
        data = _simplify_scim_users(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="SCIM Users",
        default_fields=["id", "userName", "active", "displayName", "email"],
    )


@users_app.command("get")
def user_get(
    ctx: typer.Context,
    user_id: str = typer.Argument(
        ...,
        help=(
            "The SCIM user ID to retrieve. This is the unique identifier assigned by "
            "Netskope when the user was provisioned. Find IDs via 'netskope users list'."
        ),
    ),
) -> None:
    """Retrieve a single SCIM user by their unique ID.

    Queries GET /api/v2/scim/Users/{id} for the full user record including
    username, email, active status, and group memberships. Use this to verify
    a user's provisioning state or inspect their attributes.

    Examples:
        netskope users get abc123-def456
        netskope -o json users get abc123-def456
    """
    client = _build_client(ctx)
    data = client.request("GET", f"/api/v2/scim/Users/{user_id}")

    if not _is_raw(ctx):
        data = _simplify_scim_users(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"SCIM User {user_id}",
    )


@users_app.command("create")
def user_create(
    ctx: typer.Context,
    username: str = typer.Option(
        ...,
        "--username",
        help=(
            "The userName for the SCIM user, typically an email address. This is the "
            "primary login identifier and must be unique across all users in the tenant. "
            "For example: 'alice@example.com'."
        ),
    ),
    email: str = typer.Option(
        ...,
        "--email",
        help=(
            "Primary email address for the user. Used for notifications and as the "
            "contact email. Typically the same as --username but can differ. "
            "Must be a valid email format."
        ),
    ),
    active: bool = typer.Option(
        True,
        "--active/--inactive",
        help=(
            "Whether the user account should be active or inactive. Active users can "
            "authenticate and are subject to security policies. Use --inactive to create "
            "a disabled account. Defaults to active."
        ),
    ),
) -> None:
    """Create a new SCIM user in the Netskope tenant.

    Sends POST /api/v2/scim/Users with the SCIM 2.0 User schema. The user will
    be provisioned and can be added to groups for policy targeting. Use this for
    automated user onboarding from identity providers or HR systems.

    Examples:
        netskope users create --username alice@example.com --email alice@example.com
        netskope users create --username bob@example.com --email bob@example.com --inactive
        netskope -o json users create --username contractor@vendor.com --email contractor@vendor.com
    """
    body: dict[str, Any] = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": username,
        "active": active,
        "emails": [
            {
                "value": email,
                "primary": True,
            }
        ],
    }

    client = _build_client(ctx)
    data = client.request("POST", "/api/v2/scim/Users", json_data=body)

    echo_success(
        f"User '{username}' created.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="Created SCIM User",
    )


@users_app.command("update")
def user_update(
    ctx: typer.Context,
    user_id: str = typer.Argument(
        ...,
        help=("SCIM user ID to update. Find IDs via 'netskope users list' or " "'netskope users get'."),
    ),
    set_values: Optional[list[str]] = typer.Option(
        None,
        "--set",
        help=(
            "Field to update in key=value format. Can be repeated for multiple fields. "
            "Common fields: 'active=true|false', 'userName=email@example.com'. "
            "Values are auto-coerced: 'true'/'false' become booleans, integers are parsed."
        ),
    ),
) -> None:
    """Update one or more fields on an existing SCIM user via PATCH.

    Sends PATCH /api/v2/scim/Users/{id} with SCIM PatchOp replace operations.
    Pass one or more --set key=value flags to specify the fields to modify. Use
    this for user lifecycle management such as deactivating accounts or updating
    email addresses.

    Examples:
        netskope users update abc123 --set active=false
        netskope users update abc123 --set userName=new@example.com --set active=true
        netskope -o json users update abc123 --set active=false
    """
    if not set_values:
        raise ValidationError(
            "At least one --set key=value is required.",
            suggestion="Example: netskope users update <id> --set active=false",
        )

    fields = _parse_set_options(set_values)

    operations = [
        {
            "op": "replace",
            "path": key,
            "value": value,
        }
        for key, value in fields.items()
    ]

    body: dict[str, Any] = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": operations,
    }

    client = _build_client(ctx)
    data = client.request("PATCH", f"/api/v2/scim/Users/{user_id}", json_data=body)

    echo_success(
        f"User '{user_id}' updated.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"Updated SCIM User {user_id}",
    )


@users_app.command("delete")
def user_delete(
    ctx: typer.Context,
    user_id: str = typer.Argument(
        ...,
        help=(
            "SCIM user ID to delete. Find IDs via 'netskope users list'. "
            "This action permanently removes the user and cannot be undone."
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
    """Permanently delete a SCIM user from the tenant.

    Sends DELETE /api/v2/scim/Users/{id}. This is a destructive operation that
    removes the user identity. The user will lose access to all Netskope-protected
    resources. Use --yes to skip confirmation for automation.

    Examples:
        netskope users delete abc123
        netskope users delete abc123 --yes
    """
    if not yes:
        typer.confirm(
            f"Are you sure you want to delete user '{user_id}'?",
            abort=True,
        )

    client = _build_client(ctx)
    client.request("DELETE", f"/api/v2/scim/Users/{user_id}")

    echo_success(
        f"User '{user_id}' deleted.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )


# ---------------------------------------------------------------------------
# Group commands
# ---------------------------------------------------------------------------


@groups_app.command("list")
def group_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "SCIM filter expression to narrow results. Uses SCIM 2.0 filter syntax. "
            "For example: 'displayName eq \"Engineering\"' or 'displayName co \"Dev\"'. "
            "Omit to return all groups."
        ),
    ),
    count: int = typer.Option(
        100,
        "--limit",
        "--count",
        help=(
            "Number of group records per page. Use with --start-index for pagination. "
            "Defaults to 100. The API may enforce an upper limit."
        ),
    ),
    start_index: int = typer.Option(
        1,
        "--start-index",
        help=("1-based index of the first result to return. Use with --count for " "pagination. Defaults to 1."),
    ),
) -> None:
    """List SCIM groups with optional filtering and pagination.

    Queries GET /api/v2/scim/Groups to retrieve all provisioned groups. Groups
    are used to organize users for policy targeting and access control. Use SCIM
    filter expressions to find specific groups.

    Examples:
        netskope users groups list
        netskope users groups list --filter 'displayName eq "Engineering"'
        netskope -o json users groups list --count 50
    """
    client = _build_client(ctx)
    params: dict[str, Any] = {
        "count": count,
        "startIndex": start_index,
    }
    if filter_:
        params["filter"] = filter_

    data = client.request("GET", "/api/v2/scim/Groups", params=params)

    if not _is_raw(ctx):
        data = _simplify_scim_groups(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="SCIM Groups",
        default_fields=["id", "displayName", "member_count"],
    )


@groups_app.command("get")
def group_get(
    ctx: typer.Context,
    group_id: str = typer.Argument(
        ...,
        help="SCIM group ID to retrieve. Find IDs via 'netskope users groups list'.",
    ),
) -> None:
    """Retrieve a single SCIM group by its unique ID.

    Queries GET /api/v2/scim/Groups/{id} for the full group record including
    display name and member list. Use this to inspect group membership or
    verify provisioning state.

    Examples:
        netskope users groups get grp-abc123
        netskope -o json users groups get grp-abc123
    """
    client = _build_client(ctx)
    data = client.request("GET", f"/api/v2/scim/Groups/{group_id}")

    if not _is_raw(ctx):
        data = _simplify_scim_groups(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"SCIM Group {group_id}",
    )


@groups_app.command("create")
def group_create(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "Display name for the new group. Should be descriptive, such as "
            "'Engineering' or 'Sales-Team'. Must be unique within the tenant."
        ),
    ),
    members: Optional[str] = typer.Option(
        None,
        "--members",
        help=(
            "Comma-separated list of SCIM user IDs to add as initial members. "
            "For example: 'uid1,uid2,uid3'. Omit to create an empty group "
            "(members can be added later via update)."
        ),
    ),
) -> None:
    """Create a new SCIM group with optional initial members.

    Sends POST /api/v2/scim/Groups with the SCIM 2.0 Group schema. Groups
    organize users for security policy targeting. Use this for automated group
    provisioning from identity providers.

    Examples:
        netskope users groups create "Engineering"
        netskope users groups create "Finance" --members "uid1,uid2,uid3"
        netskope -o json users groups create "Contractors"
    """
    body: dict[str, Any] = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "displayName": name,
    }

    if members:
        member_ids = [m.strip() for m in members.split(",") if m.strip()]
        body["members"] = [{"value": mid} for mid in member_ids]

    client = _build_client(ctx)
    data = client.request("POST", "/api/v2/scim/Groups", json_data=body)

    echo_success(
        f"Group '{name}' created.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="Created SCIM Group",
    )


@groups_app.command("update")
def group_update(
    ctx: typer.Context,
    group_id: str = typer.Argument(
        ...,
        help="SCIM group ID to update. Find IDs via 'netskope users groups list'.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=("New display name for the group. Omit to keep the current name. " "Must be unique within the tenant."),
    ),
    members: Optional[str] = typer.Option(
        None,
        "--members",
        help=(
            "Comma-separated list of SCIM user IDs to set as group members. This "
            "REPLACES the entire member list. Include all desired members. "
            "For example: 'uid1,uid2,uid3'."
        ),
    ),
) -> None:
    """Update a SCIM group's name or member list via PATCH.

    Sends PATCH /api/v2/scim/Groups/{id} with SCIM PatchOp replace operations.
    At least one of --name or --members must be provided. Member updates fully
    replace the current member list.

    Examples:
        netskope users groups update grp-abc123 --name "New Team Name"
        netskope users groups update grp-abc123 --members "uid1,uid2,uid3"
        netskope users groups update grp-abc123 --name "DevOps" --members "uid4,uid5"
    """
    operations: list[dict[str, Any]] = []

    if name is not None:
        operations.append(
            {
                "op": "replace",
                "path": "displayName",
                "value": name,
            }
        )

    if members is not None:
        member_ids = [m.strip() for m in members.split(",") if m.strip()]
        operations.append(
            {
                "op": "replace",
                "path": "members",
                "value": [{"value": mid} for mid in member_ids],
            }
        )

    if not operations:
        raise ValidationError(
            "At least one of --name or --members is required.",
            suggestion="Example: netskope users groups update <id> --name 'New Name'",
        )

    body: dict[str, Any] = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": operations,
    }

    client = _build_client(ctx)
    data = client.request("PATCH", f"/api/v2/scim/Groups/{group_id}", json_data=body)

    echo_success(
        f"Group '{group_id}' updated.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"Updated SCIM Group {group_id}",
    )


@groups_app.command("delete")
def group_delete(
    ctx: typer.Context,
    group_id: str = typer.Argument(
        ...,
        help=(
            "SCIM group ID to delete. Find IDs via 'netskope users groups list'. " "This permanently removes the group."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and proceed with deletion. "
            "Required for non-interactive use (scripts, CI/CD, AI agents). "
            "Defaults to False."
        ),
    ),
) -> None:
    """Permanently delete a SCIM group from the tenant.

    Sends DELETE /api/v2/scim/Groups/{id}. This removes the group and all
    membership associations. Policies referencing this group may be affected.
    Use --yes to skip confirmation for automation.

    Examples:
        netskope users groups delete grp-abc123
        netskope users groups delete grp-abc123 --yes
    """
    if not yes:
        typer.confirm(
            f"Are you sure you want to delete group '{group_id}'?",
            abort=True,
        )

    client = _build_client(ctx)
    client.request("DELETE", f"/api/v2/scim/Groups/{group_id}")

    echo_success(
        f"Group '{group_id}' deleted.",
        no_color=ctx.obj.no_color if ctx.obj else False,
    )
