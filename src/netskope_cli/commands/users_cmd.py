"""User and group management commands for the Netskope CLI.

Provides query commands via the User Management API (/api/v2/users/) for
richer data including group membership, and SCIM v2 CRUD commands for
provisioning (/api/v2/scim/).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import NotFoundError, ValidationError
from netskope_cli.core.output import OutputFormatter, echo_success

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

groups_app = typer.Typer(
    name="groups",
    help=(
        "Query and manage groups.\n\n"
        "Query commands use the User Management API (/api/v2/users/) which returns "
        "rich metadata including user counts and provisioner info. CRUD commands use "
        "SCIM v2 (/api/v2/scim/Groups) for provisioning."
    ),
    no_args_is_help=True,
)

users_app = typer.Typer(
    name="users",
    help=(
        "Query and manage users and groups.\n\n"
        "Query commands (list, get) use the User Management API which returns rich "
        "data including group membership. CRUD commands (create, update, delete) use "
        "SCIM v2 for provisioning. Use 'users groups members' to find all users in "
        "a specific group."
    ),
    no_args_is_help=True,
)

users_app.add_typer(groups_app, name="groups", help="Query and manage groups.")


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
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the user-selected output format string."""
    state = ctx.obj
    return state.output.value if state else "table"


def _is_raw(ctx: typer.Context) -> bool:
    """Return True if the user requested raw (unprocessed) output."""
    state = ctx.obj
    return state.raw if state else False


def _build_query_body(filter_json: str | None, limit: int, offset: int) -> dict[str, Any]:
    """Construct the POST body for User Management API query endpoints.

    Returns ``{"query": {"filter": ..., "paging": {"offset": n, "limit": n}}}``.
    """
    body: dict[str, Any] = {
        "query": {"paging": {"offset": offset, "limit": limit}},
    }
    if filter_json:
        try:
            filter_dict = json.loads(filter_json)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"Invalid --filter JSON: {exc}",
                suggestion=(
                    "Filter must be a valid JSON object. Examples:\n"
                    """  --filter '{"and": [{"emails": {"eq": "user@example.com"}}]}'\n"""
                    """  --filter '{"deleted": {"eq": false}}'"""
                ),
            ) from exc
        body["query"]["filter"] = filter_dict
    return body


# ---------------------------------------------------------------------------
# User Management API simplifiers
# ---------------------------------------------------------------------------


def _simplify_um_user(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten a User Management API user record for human-friendly output."""
    simplified: dict[str, Any] = {}

    for key in ("id", "givenName", "familyName"):
        if key in record:
            simplified[key] = record[key]

    # Flatten emails list to primary email string
    emails = record.get("emails")
    if isinstance(emails, list) and emails:
        if isinstance(emails[0], dict):
            primary = next(
                (e.get("value") for e in emails if isinstance(e, dict) and e.get("primary")),
                None,
            )
            if primary is None:
                primary = emails[0].get("value")
            simplified["email"] = primary
        elif isinstance(emails[0], str):
            simplified["email"] = emails[0]

    # Extract fields from the first account entry
    accounts = record.get("accounts")
    if isinstance(accounts, list) and accounts:
        acct = accounts[0]
        if isinstance(acct, dict):
            for key in ("scimId", "userName", "active", "deleted", "parentGroups", "ou", "provisioner"):
                if key in acct:
                    simplified[key] = acct[key]

    return simplified


def _simplify_um_users(data: Any) -> Any:
    """Simplify User Management API user response data.

    Handles the real envelope ``{"counts": ..., "data": [...]}``, a bare list
    (after output-formatter unwrapping), or the ``{"users": [...]}`` shape
    used in unit-test mocks.
    """
    if isinstance(data, dict):
        for key in ("data", "users"):
            if key in data and isinstance(data[key], list):
                data[key] = [_simplify_um_user(r) for r in data[key] if isinstance(r, dict)]
                return data
    if isinstance(data, list):
        return [_simplify_um_user(r) for r in data if isinstance(r, dict)]
    return data


def _simplify_um_group(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten a User Management API group record for human-friendly output."""
    simplified: dict[str, Any] = {}
    for key in ("id", "scimId", "displayName", "userCount", "provisioner", "deleted"):
        if key in record:
            simplified[key] = record[key]
    return simplified


def _simplify_um_groups(data: Any) -> Any:
    """Simplify User Management API group response data.

    Handles the real envelope ``{"counts": ..., "data": [...]}``, a bare list,
    or the ``{"groups": [...]}`` shape used in unit-test mocks.
    """
    if isinstance(data, dict):
        for key in ("data", "groups"):
            if key in data and isinstance(data[key], list):
                data[key] = [_simplify_um_group(r) for r in data[key] if isinstance(r, dict)]
                return data
    if isinstance(data, list):
        return [_simplify_um_group(r) for r in data if isinstance(r, dict)]
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
# User query commands (User Management API)
# ---------------------------------------------------------------------------


@users_app.command("list")
def user_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "JSON filter dict for the User Management API. Uses structured operators "
            "(eq, in, sw, co). Filterable fields: userName, emails, accounts.deleted, "
            "accounts.active, accounts.parentGroups, accounts.ou.\n\n"
            "Examples:\n"
            """  '{"and": [{"emails": {"eq": "user@example.com"}}]}'\n"""
            """  '{"accounts.active": {"eq": true}}'"""
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        help="Maximum number of records to return (max 1000). Defaults to 100.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="0-based pagination offset. Defaults to 0.",
    ),
) -> None:
    """List users with group membership data.

    Queries POST /api/v2/users/getusers via the User Management API, which
    returns richer data than SCIM including parentGroups for each user account.

    Examples:
        netskope users list
        netskope users list --filter '{"and": [{"emails": {"eq": "alice@example.com"}}]}'
        netskope -o json users list --limit 50 --offset 100
        netskope users list --filter '{"accounts.parentGroups": {"in": ["Engineering"]}}'
    """
    client = _build_client(ctx)
    body = _build_query_body(filter_, limit, offset)
    data = client.request("POST", "/api/v2/users/getusers", json_data=body)

    if not _is_raw(ctx):
        data = _simplify_um_users(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="Users",
        default_fields=["id", "userName", "email", "active", "parentGroups"],
    )


@users_app.command("get")
def user_get(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        ...,
        help=(
            "Email address or username to look up. If the value contains '@', it is "
            "treated as an email; otherwise as a username. Use --by to override."
        ),
    ),
    by: Optional[str] = typer.Option(
        None,
        "--by",
        help="Force lookup field: 'email' or 'username'. Auto-detected by default.",
    ),
) -> None:
    """Look up a single user by email or username.

    Uses POST /api/v2/users/getusers with a filter to find the user. Returns
    rich data including group membership (parentGroups).

    Examples:
        netskope users get alice@example.com
        netskope users get alice --by username
        netskope -o json users get alice@example.com
    """
    if by == "email" or (by is None and "@" in identifier):
        filter_dict: dict[str, Any] = {"and": [{"emails": {"eq": identifier}}]}
    elif by == "username":
        filter_dict = {"and": [{"userName": {"eq": identifier}}]}
    else:
        # No @ and no --by flag: default to userName
        filter_dict = {"and": [{"userName": {"eq": identifier}}]}

    body: dict[str, Any] = {
        "query": {"filter": filter_dict, "paging": {"offset": 0, "limit": 1}},
    }

    client = _build_client(ctx)
    data = client.request("POST", "/api/v2/users/getusers", json_data=body)

    # Extract the single user from the response
    users = data if isinstance(data, list) else None
    if users is None and isinstance(data, dict):
        users = data.get("users", data.get("data", data.get("result")))
    if isinstance(users, list) and len(users) == 0:
        raise NotFoundError(
            f"No user found matching '{identifier}'.",
            suggestion="Check the email/username and try again. Use 'netskope users list' to browse.",
        )

    if not _is_raw(ctx):
        data = _simplify_um_users(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"User '{identifier}'",
    )


# ---------------------------------------------------------------------------
# User CRUD commands (SCIM v2)
# ---------------------------------------------------------------------------


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
    be provisioned and can be added to groups for policy targeting. Use
    'netskope users list' or 'netskope users get' to look up users afterward.

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
        help=(
            "SCIM user ID (scimId) to update. Find scimId values via " "'netskope users list' or 'netskope users get'."
        ),
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
    The user_id is the scimId from the User Management API response. Pass one
    or more --set key=value flags to specify the fields to modify.

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
            "SCIM user ID (scimId) to delete. Find scimId values via "
            "'netskope users list'. This permanently removes the user."
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
# Group query commands (User Management API)
# ---------------------------------------------------------------------------


@groups_app.command("list")
def group_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "JSON filter dict for the User Management API. Uses structured operators "
            "(eq, in, sw, co). Filterable fields: id, scimId, deleted, collectionId, "
            "parentGroups, idps.\n\n"
            "Examples:\n"
            """  '{"deleted": {"eq": false}}'\n"""
            """  '{"id": {"eq": "Engineering"}}'"""
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        help="Maximum number of records to return (max 1000). Defaults to 100.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="0-based pagination offset. Defaults to 0.",
    ),
) -> None:
    """List groups with rich metadata.

    Queries POST /api/v2/users/getgroups via the User Management API, which
    returns richer data than SCIM including userCount and provisioner info.

    Examples:
        netskope users groups list
        netskope users groups list --filter '{"deleted": {"eq": false}}'
        netskope -o json users groups list --limit 50
    """
    client = _build_client(ctx)
    body = _build_query_body(filter_, limit, offset)
    data = client.request("POST", "/api/v2/users/getgroups", json_data=body)

    if not _is_raw(ctx):
        data = _simplify_um_groups(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="Groups",
        default_fields=["id", "displayName", "userCount", "provisioner", "deleted"],
    )


@groups_app.command("get")
def group_get(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Group display name to look up. For example: 'Engineering'.",
    ),
) -> None:
    """Look up a single group by display name.

    Uses POST /api/v2/users/getgroups with a filter to find the group. Returns
    rich data including userCount, provisioner, and modification timestamps.

    Examples:
        netskope users groups get "Engineering"
        netskope -o json users groups get "Sales Team"
    """
    filter_dict: dict[str, Any] = {"displayName": {"eq": name}}
    body: dict[str, Any] = {
        "query": {"filter": filter_dict, "paging": {"offset": 0, "limit": 1}},
    }

    client = _build_client(ctx)
    data = client.request("POST", "/api/v2/users/getgroups", json_data=body)

    # Check if any group was found
    groups = data if isinstance(data, list) else None
    if groups is None and isinstance(data, dict):
        groups = data.get("groups", data.get("data", data.get("result")))
    if isinstance(groups, list) and len(groups) == 0:
        raise NotFoundError(
            f"No group found matching '{name}'.",
            suggestion="Check the group name and try again. Use 'netskope users groups list' to browse.",
        )

    if not _is_raw(ctx):
        data = _simplify_um_groups(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"Group '{name}'",
    )


@groups_app.command("members")
def group_members(
    ctx: typer.Context,
    group_name: str = typer.Argument(
        ...,
        help=("Display name of the group to list members for. " "For example: 'Engineering' or 'Sales Team'."),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        help="Maximum number of members to return (max 1000). Defaults to 100.",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help="0-based pagination offset. Defaults to 0.",
    ),
) -> None:
    """List all users in a specific group.

    Uses POST /api/v2/users/getusers with a pre-built filter to find users
    whose accounts.parentGroups includes the given group name.

    Examples:
        netskope users groups members "Engineering"
        netskope users groups members "Sales Team" --limit 50
        netskope -o json users groups members "Engineering"
    """
    filter_dict: dict[str, Any] = {"accounts.parentGroups": {"in": [group_name]}}
    body: dict[str, Any] = {
        "query": {
            "filter": filter_dict,
            "paging": {"offset": offset, "limit": limit},
        },
    }

    client = _build_client(ctx)
    data = client.request("POST", "/api/v2/users/getusers", json_data=body)

    if not _is_raw(ctx):
        data = _simplify_um_users(data)

    formatter = _get_formatter(ctx)
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"Members of '{group_name}'",
        default_fields=["id", "userName", "email", "active"],
    )


# ---------------------------------------------------------------------------
# Group CRUD commands (SCIM v2)
# ---------------------------------------------------------------------------


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
            "Comma-separated list of SCIM user IDs (scimId) to add as initial members. "
            "For example: 'uid1,uid2,uid3'. Find scimId values via 'netskope users list'. "
            "Omit to create an empty group (members can be added later via update)."
        ),
    ),
) -> None:
    """Create a new SCIM group with optional initial members.

    Sends POST /api/v2/scim/Groups with the SCIM 2.0 Group schema. Groups
    organize users for security policy targeting. Use 'netskope users groups list'
    to look up groups afterward.

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
        help=(
            "SCIM group ID (scimId) to update. Find scimId values via "
            "'netskope users groups list' or 'netskope users groups get'."
        ),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="New display name for the group. Omit to keep the current name. Must be unique within the tenant.",
    ),
    members: Optional[str] = typer.Option(
        None,
        "--members",
        help=(
            "Comma-separated list of SCIM user IDs (scimId) to set as group members. "
            "This REPLACES the entire member list. Include all desired members. "
            "For example: 'uid1,uid2,uid3'."
        ),
    ),
) -> None:
    """Update a SCIM group's name or member list via PATCH.

    Sends PATCH /api/v2/scim/Groups/{id} with SCIM PatchOp replace operations.
    The group_id is the scimId from the User Management API response. At least
    one of --name or --members must be provided.

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
            "SCIM group ID (scimId) to delete. Find scimId values via "
            "'netskope users groups list'. This permanently removes the group."
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
    Use 'netskope users groups members' to review membership before deletion.
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
