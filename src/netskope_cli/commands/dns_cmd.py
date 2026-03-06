"""DNS Security profile management commands for the Netskope CLI.

Provides DNS profile CRUD, deployment, inheritance group management,
and reference data lookups (tunnels, domain categories, record types).
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, echo_warning

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

dns_app = typer.Typer(
    name="dns",
    help=(
        "Manage DNS Security profiles on the Netskope platform.\n\n"
        "This command group provides DNS profile CRUD operations, deployment of "
        "pending changes, inheritance group management, and reference data lookups "
        "for tunnels, domain categories, and DNS record types."
    ),
    no_args_is_help=True,
)

profiles_app = typer.Typer(
    name="profiles",
    help=(
        "Create, list, update, delete, and deploy DNS Security profiles.\n\n"
        "DNS profiles define the security posture for DNS traffic inspection. "
        "Each profile contains rules for blocking, allowing, or alerting on "
        "DNS queries to specific domain categories or record types."
    ),
    no_args_is_help=True,
)

groups_app = typer.Typer(
    name="groups",
    help=(
        "Manage DNS Security inheritance groups.\n\n"
        "Inheritance groups let you organize DNS profiles into hierarchical "
        "structures so that child profiles can inherit settings from a parent "
        "group. Use groups to enforce consistent DNS security baselines."
    ),
    no_args_is_help=True,
)

dns_app.add_typer(profiles_app, name="profiles")
dns_app.add_typer(groups_app, name="groups")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an OutputFormatter respecting the current state."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from state."""
    state = ctx.obj
    return state.output.value if state is not None else "table"


# ---------------------------------------------------------------------------
# Profiles commands
# ---------------------------------------------------------------------------


@profiles_app.command("list")
def profiles_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Server-side filter expression to narrow the returned DNS profiles. "
            "Use this to search by name or other profile attributes. "
            "The exact syntax follows the Netskope REST API filter format."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of DNS profiles to return in a single response. "
            "Use this for pagination when you have many profiles. "
            "Combine with --offset for paginated retrieval."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of DNS profiles to skip before returning results. "
            "Use together with --limit for pagination. For example, "
            "--offset 20 --limit 10 returns items 21-30."
        ),
    ),
    sortby: Optional[str] = typer.Option(
        None,
        "--sortby",
        help=(
            "Field name to sort the results by, such as 'name' or 'id'. "
            "When omitted the API returns results in its default order. "
            "Combine with --sortorder to control ascending/descending."
        ),
    ),
    sortorder: Optional[str] = typer.Option(
        None,
        "--sortorder",
        help=(
            "Sort direction for the results. Valid values: 'asc' for ascending "
            "or 'desc' for descending. Requires --sortby to be set. "
            "Defaults to ascending when --sortby is provided without this flag."
        ),
    ),
) -> None:
    """List all DNS Security profiles configured in the tenant.

    Fetches DNS profiles from GET /api/v2/profiles/dns with optional
    filtering, pagination, and sorting. Use this to audit existing profiles,
    find profile IDs for updates, or verify newly created profiles.

    Examples:
        netskope dns profiles list
        netskope dns profiles list --limit 10 --offset 0
        netskope dns profiles list --sortby name --sortorder asc
        netskope -o json dns profiles list --filter "name eq 'Default'"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if filter_ is not None:
        params["filter"] = filter_
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if sortby is not None:
        params["sortby"] = sortby
    if sortorder is not None:
        params["sortorder"] = sortorder

    result = client.request("GET", "/api/v2/profiles/dns", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DNS Profiles")


@profiles_app.command("get")
def profiles_get(
    ctx: typer.Context,
    profile_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the DNS profile to retrieve. Find IDs by running "
            "'netskope dns profiles list'. The ID is a tenant-unique integer "
            "assigned when the profile was created."
        ),
    ),
) -> None:
    """Retrieve details of a specific DNS Security profile by its ID.

    Fetches a single DNS profile from GET /api/v2/profiles/dns/{id} including
    its name, rules, and configuration. Use this to inspect a profile before
    updating or to verify changes after an update.

    Examples:
        netskope dns profiles get 42
        netskope -o json dns profiles get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    result = client.request("GET", f"/api/v2/profiles/dns/{profile_id}")

    formatter.format_output(result, fmt=fmt, title=f"DNS Profile {profile_id}")


@profiles_app.command("create")
def profiles_create(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "A descriptive name for the new DNS Security profile. This name is "
            "displayed in the Netskope admin console and referenced by policies. "
            "Must be unique within your tenant."
        ),
    ),
) -> None:
    """Create a new DNS Security profile.

    Sends POST /api/v2/profiles/dns to create a named DNS profile. After
    creating the profile, configure its rules and run 'netskope dns profiles
    deploy' to push the changes live.

    Examples:
        netskope dns profiles create "Corporate DNS Policy"
        netskope -o json dns profiles create "Guest Network Profile"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = {"name": name}

    result = client.request("POST", "/api/v2/profiles/dns", json_data=body)

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"DNS profile '{name}' created.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title="Created DNS Profile")


@profiles_app.command("update")
def profiles_update(
    ctx: typer.Context,
    profile_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the DNS profile to update. Find IDs by running " "'netskope dns profiles list'."),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=(
            "New name for the DNS profile. Omit to keep the current name. "
            "Must be unique within your tenant. The name is displayed in "
            "the admin console and referenced by policies."
        ),
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        help=(
            "Updated description for the DNS profile. Omit to keep the current "
            "description. Use this to document the purpose or scope of the "
            "profile for other administrators."
        ),
    ),
    log_traffic: Optional[bool] = typer.Option(
        None,
        "--log-traffic/--no-log-traffic",
        help=(
            "Enable or disable traffic logging for this DNS profile. When enabled, "
            "DNS queries matching this profile are recorded in the event log. "
            "Useful for auditing and troubleshooting DNS security events."
        ),
    ),
) -> None:
    """Update an existing DNS Security profile by ID.

    Sends PATCH /api/v2/profiles/dns/{id} with the provided changes. Only the
    fields you specify are updated; all other fields remain unchanged. After
    updating, run 'netskope dns profiles deploy' to activate the changes.

    Examples:
        netskope dns profiles update 42 --name "Renamed Profile"
        netskope dns profiles update 42 --description "Updated security baseline"
        netskope dns profiles update 42 --log-traffic --name "Audited Profile"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    data: dict[str, object] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if log_traffic is not None:
        data["log_traffic"] = log_traffic

    if not data:
        echo_warning(
            "No update options provided. Use --name, --description, or --log-traffic.",
            no_color=ctx.obj.no_color if ctx.obj is not None else False,
        )
        raise typer.Exit(code=1)

    result = client.request(
        "PATCH",
        f"/api/v2/profiles/dns/{profile_id}",
        json_data=data,
    )

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"DNS profile {profile_id} updated.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title=f"Updated DNS Profile {profile_id}")


@profiles_app.command("delete")
def profiles_delete(
    ctx: typer.Context,
    profile_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the DNS profile to delete. Find IDs by running "
            "'netskope dns profiles list'. This action cannot be undone."
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
    """Delete a DNS Security profile by ID.

    Sends DELETE /api/v2/profiles/dns/{id}. This is a destructive operation
    that cannot be undone. Any policies referencing this profile may be
    affected. After deletion, run 'netskope dns profiles deploy' to activate
    the change.

    Examples:
        netskope dns profiles delete 42
        netskope dns profiles delete 42 --yes
    """
    if not yes:
        typer.confirm(
            f"Are you sure you want to delete DNS profile {profile_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    result = client.request("DELETE", f"/api/v2/profiles/dns/{profile_id}")

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"DNS profile {profile_id} deleted.", no_color=no_color)

    if result is not None:
        formatter = _get_formatter(ctx)
        fmt = _get_output_format(ctx)
        formatter.format_output(result, fmt=fmt, title="Delete Result")


@profiles_app.command("deploy")
def profiles_deploy(
    ctx: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help=(
            "Deploy all pending DNS profile changes at once. When set, the --ids "
            "option is ignored. Use this to push every staged modification to "
            "production in a single operation."
        ),
    ),
    ids: Optional[str] = typer.Option(
        None,
        "--ids",
        help=(
            "Comma-separated list of DNS profile IDs to deploy. Only changes for "
            "these specific profiles are pushed live. For example: '1,5,12'. "
            "Mutually exclusive with --all."
        ),
    ),
    change_note: Optional[str] = typer.Option(
        None,
        "--change-note",
        help=(
            "A short note describing the reason for this deployment. Recorded in "
            "the audit log for compliance and troubleshooting. Best practice is "
            "to include a ticket or change-request reference."
        ),
    ),
) -> None:
    """Deploy pending DNS Security profile changes to the live tenant.

    Sends POST /api/v2/profiles/dns/deploy to apply staged DNS profile
    modifications to the production configuration. You can deploy all pending
    changes with --all, or target specific profiles with --ids.

    Examples:
        netskope dns profiles deploy --all
        netskope dns profiles deploy --ids "1,5,12"
        netskope dns profiles deploy --all --change-note "JIRA-1234: enable logging"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body: dict[str, object] = {}
    if all_profiles:
        body["all"] = True
    elif ids is not None:
        body["ids"] = [int(i.strip()) for i in ids.split(",") if i.strip()]
    if change_note is not None:
        body["change_note"] = change_note

    result = client.request("POST", "/api/v2/profiles/dns/deploy", json_data=body)

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success("DNS profile changes deployed successfully.", no_color=no_color)

    if result is not None:
        formatter.format_output(result, fmt=fmt, title="Deploy Result")


# ---------------------------------------------------------------------------
# Reference data commands (top-level under dns)
# ---------------------------------------------------------------------------


@dns_app.command("tunnels")
def dns_tunnels(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Server-side filter expression to narrow the returned tunnels. "
            "Use this to search by tunnel name or status. "
            "The exact syntax follows the Netskope REST API filter format."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of DNS tunnels to return in a single response. "
            "Use this for pagination when you have many tunnels. "
            "Combine with --offset for paginated retrieval."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of DNS tunnels to skip before returning results. "
            "Use together with --limit for pagination. For example, "
            "--offset 10 --limit 5 returns items 11-15."
        ),
    ),
) -> None:
    """List DNS tunnels available for DNS Security profiles.

    Fetches DNS tunnels from GET /api/v2/profiles/dns/tunnels with optional
    filtering and pagination. Tunnels represent the network paths used to
    route DNS traffic through the Netskope infrastructure.

    Examples:
        netskope dns tunnels
        netskope dns tunnels --limit 10 --offset 0
        netskope -o json dns tunnels --filter "name eq 'us-west'"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if filter_ is not None:
        params["filter"] = filter_
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    result = client.request("GET", "/api/v2/profiles/dns/tunnels", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DNS Tunnels")


@dns_app.command("categories")
def dns_categories(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Server-side filter expression to narrow the returned domain categories. "
            "Use this to search by category name or identifier. "
            "The exact syntax follows the Netskope REST API filter format."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of domain categories to return in a single response. "
            "Use this for pagination when there are many categories. "
            "Omit to return all categories."
        ),
    ),
) -> None:
    """List domain categories available for DNS Security rules.

    Fetches domain categories from GET /api/v2/profiles/dns/domaincategories.
    Domain categories classify websites and domains (e.g. 'Malware', 'Social
    Media') and are used in DNS profile rules to allow, block, or alert.

    Examples:
        netskope dns categories
        netskope dns categories --limit 20
        netskope -o json dns categories --filter "name eq 'Malware'"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if filter_ is not None:
        params["filter"] = filter_
    if limit is not None:
        params["limit"] = limit

    result = client.request("GET", "/api/v2/profiles/dns/domaincategories", params=params or None)

    formatter.format_output(result, fmt=fmt, title="Domain Categories")


@dns_app.command("record-types")
def dns_record_types(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Server-side filter expression to narrow the returned DNS record types. "
            "Use this to search by record type name (e.g. 'A', 'AAAA', 'MX'). "
            "The exact syntax follows the Netskope REST API filter format."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of DNS record types to return in a single response. "
            "Use this for pagination when there are many record types. "
            "Omit to return all record types."
        ),
    ),
) -> None:
    """List DNS record types available for DNS Security rules.

    Fetches record types from GET /api/v2/profiles/dns/recordtypes. Record
    types (A, AAAA, MX, CNAME, etc.) can be referenced in DNS profile rules
    to control which query types are allowed, blocked, or logged.

    Examples:
        netskope dns record-types
        netskope dns record-types --limit 10
        netskope -o json dns record-types --filter "name eq 'MX'"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if filter_ is not None:
        params["filter"] = filter_
    if limit is not None:
        params["limit"] = limit

    result = client.request("GET", "/api/v2/profiles/dns/recordtypes", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DNS Record Types")


# ---------------------------------------------------------------------------
# Inheritance groups commands
# ---------------------------------------------------------------------------


@groups_app.command("list")
def groups_list(
    ctx: typer.Context,
    filter_: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Server-side filter expression to narrow the returned inheritance groups. "
            "Use this to search by group name or other attributes. "
            "The exact syntax follows the Netskope REST API filter format."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of inheritance groups to return in a single response. "
            "Use this for pagination when you have many groups. "
            "Combine with --offset for paginated retrieval."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of inheritance groups to skip before returning results. "
            "Use together with --limit for pagination. For example, "
            "--offset 10 --limit 5 returns items 11-15."
        ),
    ),
) -> None:
    """List all DNS Security inheritance groups.

    Fetches inheritance groups from GET /api/v2/profiles/dns/inheritancegroups
    with optional filtering and pagination. Inheritance groups organize DNS
    profiles into hierarchical structures for centralized policy management.

    Examples:
        netskope dns groups list
        netskope dns groups list --limit 10 --offset 0
        netskope -o json dns groups list --filter "name eq 'Default'"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if filter_ is not None:
        params["filter"] = filter_
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    result = client.request("GET", "/api/v2/profiles/dns/inheritancegroups", params=params or None)

    formatter.format_output(result, fmt=fmt, title="DNS Inheritance Groups")


@groups_app.command("get")
def groups_get(
    ctx: typer.Context,
    group_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the inheritance group to retrieve. Find IDs by running "
            "'netskope dns groups list'. The ID is a tenant-unique integer "
            "assigned when the group was created."
        ),
    ),
) -> None:
    """Retrieve details of a specific DNS inheritance group by its ID.

    Fetches a single inheritance group from
    GET /api/v2/profiles/dns/inheritancegroups/{id} including its name,
    description, and member profiles. Use this to inspect a group before
    updating or to verify changes after an update.

    Examples:
        netskope dns groups get 7
        netskope -o json dns groups get 7
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    result = client.request("GET", f"/api/v2/profiles/dns/inheritancegroups/{group_id}")

    formatter.format_output(result, fmt=fmt, title=f"DNS Inheritance Group {group_id}")


@groups_app.command("create")
def groups_create(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "A descriptive name for the new inheritance group. This name is "
            "displayed in the Netskope admin console and used to organize DNS "
            "profiles. Must be unique within your tenant."
        ),
    ),
) -> None:
    """Create a new DNS Security inheritance group.

    Sends POST /api/v2/profiles/dns/inheritancegroups to create a named
    group. After creating the group, add profiles to it and run
    'netskope dns groups deploy' to push the changes live.

    Examples:
        netskope dns groups create "Regional Office Group"
        netskope -o json dns groups create "Dev Team DNS"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = {"name": name}

    result = client.request("POST", "/api/v2/profiles/dns/inheritancegroups", json_data=body)

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"Inheritance group '{name}' created.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title="Created Inheritance Group")


@groups_app.command("update")
def groups_update(
    ctx: typer.Context,
    group_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the inheritance group to update. Find IDs by running " "'netskope dns groups list'."),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=(
            "New name for the inheritance group. Omit to keep the current name. "
            "Must be unique within your tenant. The name is displayed in "
            "the admin console for group identification."
        ),
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        help=(
            "Updated description for the inheritance group. Omit to keep the "
            "current description. Use this to document the purpose or scope "
            "of the group for other administrators."
        ),
    ),
) -> None:
    """Update an existing DNS inheritance group by ID.

    Sends PATCH /api/v2/profiles/dns/inheritancegroups/{id} with the provided
    changes. Only the fields you specify are updated; all other fields remain
    unchanged. After updating, run 'netskope dns groups deploy' to activate.

    Examples:
        netskope dns groups update 7 --name "Renamed Group"
        netskope dns groups update 7 --description "EMEA office DNS group"
        netskope dns groups update 7 --name "HQ Group" --description "Headquarters DNS"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    data: dict[str, object] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description

    if not data:
        echo_warning(
            "No update options provided. Use --name or --description.",
            no_color=ctx.obj.no_color if ctx.obj is not None else False,
        )
        raise typer.Exit(code=1)

    result = client.request(
        "PATCH",
        f"/api/v2/profiles/dns/inheritancegroups/{group_id}",
        json_data=data,
    )

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"Inheritance group {group_id} updated.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title=f"Updated Inheritance Group {group_id}")


@groups_app.command("delete")
def groups_delete(
    ctx: typer.Context,
    group_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the inheritance group to delete. Find IDs by running "
            "'netskope dns groups list'. This action cannot be undone."
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
    """Delete a DNS inheritance group by ID.

    Sends DELETE /api/v2/profiles/dns/inheritancegroups/{id}. This is a
    destructive operation that cannot be undone. Profiles that belonged to
    this group will no longer inherit its settings. After deletion, run
    'netskope dns groups deploy' to activate the change.

    Examples:
        netskope dns groups delete 7
        netskope dns groups delete 7 --yes
    """
    if not yes:
        typer.confirm(
            f"Are you sure you want to delete inheritance group {group_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    result = client.request("DELETE", f"/api/v2/profiles/dns/inheritancegroups/{group_id}")

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"Inheritance group {group_id} deleted.", no_color=no_color)

    if result is not None:
        formatter = _get_formatter(ctx)
        fmt = _get_output_format(ctx)
        formatter.format_output(result, fmt=fmt, title="Delete Result")


@groups_app.command("deploy")
def groups_deploy(
    ctx: typer.Context,
    all_groups: bool = typer.Option(
        False,
        "--all",
        help=(
            "Deploy all pending inheritance group changes at once. When set, the "
            "--ids option is ignored. Use this to push every staged modification "
            "to production in a single operation."
        ),
    ),
    ids: Optional[str] = typer.Option(
        None,
        "--ids",
        help=(
            "Comma-separated list of inheritance group IDs to deploy. Only changes "
            "for these specific groups are pushed live. For example: '2,7,14'. "
            "Mutually exclusive with --all."
        ),
    ),
    change_note: Optional[str] = typer.Option(
        None,
        "--change-note",
        help=(
            "A short note describing the reason for this deployment. Recorded in "
            "the audit log for compliance and troubleshooting. Best practice is "
            "to include a ticket or change-request reference."
        ),
    ),
) -> None:
    """Deploy pending DNS inheritance group changes to the live tenant.

    Sends POST /api/v2/profiles/dns/inheritancegroups/deploy to apply staged
    inheritance group modifications to the production configuration. You can
    deploy all pending changes with --all, or target specific groups with --ids.

    Examples:
        netskope dns groups deploy --all
        netskope dns groups deploy --ids "2,7,14"
        netskope dns groups deploy --all --change-note "JIRA-5678: new office group"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body: dict[str, object] = {}
    if all_groups:
        body["all"] = True
    elif ids is not None:
        body["ids"] = [int(i.strip()) for i in ids.split(",") if i.strip()]
    if change_note is not None:
        body["change_note"] = change_note

    result = client.request(
        "POST",
        "/api/v2/profiles/dns/inheritancegroups/deploy",
        json_data=body,
    )

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success("Inheritance group changes deployed successfully.", no_color=no_color)

    if result is not None:
        formatter.format_output(result, fmt=fmt, title="Deploy Result")
