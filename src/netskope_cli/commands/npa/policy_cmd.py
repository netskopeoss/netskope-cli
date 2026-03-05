"""NPA policy rules and groups management commands."""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
    _load_json_file,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
policy_app = typer.Typer(name="policy", help="Manage NPA policy rules and groups.", no_args_is_help=True)
rules_app = typer.Typer(name="rules", help="Manage NPA policy rules.", no_args_is_help=True)
groups_app = typer.Typer(name="groups", help="Manage NPA policy groups.", no_args_is_help=True)
policy_app.add_typer(rules_app, name="rules")
policy_app.add_typer(groups_app, name="groups")


# ---------------------------------------------------------------------------
# Rules commands
# ---------------------------------------------------------------------------


@rules_app.command("list")
def list_rules(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of rules to return. Use with --offset for pagination.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Number of records to skip before returning results. Use with --limit for pagination.",
    ),
    filter_query: Optional[str] = typer.Option(
        None,
        "--filter",
        "-F",
        help="Filter expression to narrow results.",
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        help="Comma-separated list of fields to include in the output.",
    ),
    sort_by: Optional[str] = typer.Option(
        None,
        "--sort-by",
        help="Field name to sort results by.",
    ),
    sort_order: Optional[str] = typer.Option(
        None,
        "--sort-order",
        help="Sort direction: 'asc' or 'desc'.",
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help="Return only the total count of matching rules.",
    ),
) -> None:
    """List all NPA policy rules with optional filtering and pagination.

    Queries GET /api/v2/policy/npa/rules to retrieve policy rule records.

    Examples:
        netskope npa policy rules list
        netskope npa policy rules list --limit 10 --sort-by rule_name
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter_query is not None:
        params["filter"] = filter_query
    if fields is not None:
        params["fields"] = fields
    if sort_by is not None:
        params["sortby"] = sort_by
    if sort_order is not None:
        params["sortorder"] = sort_order

    with spinner("Fetching NPA policy rules..."):
        data = client.request("GET", "/api/v2/policy/npa/rules", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Policy Rules",
        default_fields=["rule_id", "rule_name", "enabled", "group_name", "action"],
        count_only=count,
    )


@rules_app.command("get")
def get_rule(
    ctx: typer.Context,
    rule_id: int = typer.Argument(..., help="Numeric rule ID to retrieve."),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        help="Comma-separated list of fields to include in the output.",
    ),
) -> None:
    """Retrieve a specific NPA policy rule by ID.

    Queries GET /api/v2/policy/npa/rules/{id}.

    Examples:
        netskope npa policy rules get 42
        netskope -o json npa policy rules get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if fields is not None:
        params["fields"] = fields

    with spinner(f"Fetching NPA policy rule {rule_id}..."):
        data = client.request("GET", f"/api/v2/policy/npa/rules/{rule_id}", params=params or None)

    formatter.format_output(data, fmt=fmt, title=f"NPA Policy Rule {rule_id}")


@rules_app.command("create")
def create_rule(
    ctx: typer.Context,
    rule_name: Optional[str] = typer.Option(
        None,
        "--rule-name",
        help="Display name for the new rule.",
    ),
    group_id: Optional[str] = typer.Option(
        None,
        "--group-id",
        help="Policy group ID to assign this rule to.",
    ),
    enabled: bool = typer.Option(
        True,
        "--enabled/--disabled",
        help="Whether the rule is enabled. Defaults to enabled.",
    ),
    json_file: Optional[str] = typer.Option(
        None,
        "--json-file",
        help="Path to a JSON file containing the full rule body including rule_data.",
    ),
) -> None:
    """Create a new NPA policy rule.

    Sends POST /api/v2/policy/npa/rules. Provide either --json-file for a full
    rule body or use --rule-name and --group-id for a minimal payload.

    Examples:
        netskope npa policy rules create --rule-name "Allow SSH" --group-id "1"
        netskope npa policy rules create --json-file rule.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if json_file:
        payload = _load_json_file(json_file)
    else:
        if not rule_name:
            echo_error("Either --rule-name or --json-file is required.")
            raise typer.Exit(code=1)
        payload: dict[str, object] = {
            "rule_name": rule_name,
            "group_id": group_id,
            "enabled": "1" if enabled else "0",
        }

    with spinner("Creating NPA policy rule..."):
        data = client.request("POST", "/api/v2/policy/npa/rules", json_data=payload)

    echo_success("NPA policy rule created.")
    formatter.format_output(data, fmt=fmt, title="Created NPA Policy Rule")


@rules_app.command("update")
def update_rule(
    ctx: typer.Context,
    rule_id: int = typer.Argument(..., help="Numeric ID of the rule to update."),
    rule_name: Optional[str] = typer.Option(
        None,
        "--rule-name",
        help="New display name for the rule.",
    ),
    enabled: Optional[bool] = typer.Option(
        None,
        "--enabled/--disabled",
        help="Enable or disable the rule.",
    ),
    json_file: Optional[str] = typer.Option(
        None,
        "--json-file",
        help="Path to a JSON file containing the update payload. Overrides other options.",
    ),
) -> None:
    """Update an existing NPA policy rule.

    Sends PATCH /api/v2/policy/npa/rules/{id} with the provided changes.

    Examples:
        netskope npa policy rules update 42 --rule-name "Updated Rule"
        netskope npa policy rules update 42 --disabled
        netskope npa policy rules update 42 --json-file update.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if json_file:
        payload = _load_json_file(json_file)
    else:
        payload: dict[str, object] = {}
        if rule_name is not None:
            payload["rule_name"] = rule_name
        if enabled is not None:
            payload["enabled"] = "1" if enabled else "0"

        if not payload:
            echo_error("No update fields provided. Use --rule-name, --enabled/--disabled, or --json-file.")
            raise typer.Exit(code=1)

    with spinner(f"Updating NPA policy rule {rule_id}..."):
        data = client.request("PATCH", f"/api/v2/policy/npa/rules/{rule_id}", json_data=payload)

    echo_success(f"NPA policy rule {rule_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated NPA Policy Rule {rule_id}")


@rules_app.command("delete")
def delete_rule(
    ctx: typer.Context,
    rule_id: int = typer.Argument(..., help="Numeric ID of the rule to delete. This action cannot be undone."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and proceed with deletion.",
    ),
) -> None:
    """Delete an NPA policy rule.

    Sends DELETE /api/v2/policy/npa/rules/{id}. This is a destructive operation.
    Use --yes to skip confirmation.

    Examples:
        netskope npa policy rules delete 42
        netskope npa policy rules delete 42 --yes
    """
    _confirm_delete("NPA policy rule", rule_id, yes, ctx)

    client = _build_client(ctx)

    with spinner(f"Deleting NPA policy rule {rule_id}..."):
        client.request("DELETE", f"/api/v2/policy/npa/rules/{rule_id}")

    echo_success(f"NPA policy rule {rule_id} deleted.")


# ---------------------------------------------------------------------------
# Groups commands
# ---------------------------------------------------------------------------


@groups_app.command("list")
def list_groups(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of groups to return. Use with --offset for pagination.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Number of records to skip before returning results.",
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        help="Comma-separated list of fields to include in the output.",
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help="Return only the total count of matching groups.",
    ),
) -> None:
    """List all NPA policy groups.

    Queries GET /api/v2/policy/npa/policygroups to retrieve policy group records.

    Examples:
        netskope npa policy groups list
        netskope -o json npa policy groups list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if fields is not None:
        params["fields"] = fields

    with spinner("Fetching NPA policy groups..."):
        data = client.request("GET", "/api/v2/policy/npa/policygroups", params=params or None)

    formatter.format_output(
        data,
        fmt=fmt,
        title="NPA Policy Groups",
        default_fields=["group_id", "group_name"],
        count_only=count,
    )


@groups_app.command("get")
def get_group(
    ctx: typer.Context,
    group_id: int = typer.Argument(..., help="Numeric group ID to retrieve."),
) -> None:
    """Retrieve a specific NPA policy group by ID.

    Queries GET /api/v2/policy/npa/policygroups/{id}.

    Examples:
        netskope npa policy groups get 5
        netskope -o json npa policy groups get 5
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching NPA policy group {group_id}..."):
        data = client.request("GET", f"/api/v2/policy/npa/policygroups/{group_id}")

    formatter.format_output(data, fmt=fmt, title=f"NPA Policy Group {group_id}")


@groups_app.command("create")
def create_group(
    ctx: typer.Context,
    group_name: str = typer.Option(
        ...,
        "--group-name",
        help="Display name for the new policy group. Must be unique.",
    ),
) -> None:
    """Create a new NPA policy group.

    Sends POST /api/v2/policy/npa/policygroups.

    Examples:
        netskope npa policy groups create --group-name "Engineering Rules"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {"group_name": group_name}

    with spinner("Creating NPA policy group..."):
        data = client.request("POST", "/api/v2/policy/npa/policygroups", json_data=payload)

    echo_success(f"NPA policy group '{group_name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created NPA Policy Group")


@groups_app.command("update")
def update_group(
    ctx: typer.Context,
    group_id: int = typer.Argument(..., help="Numeric ID of the policy group to update."),
    group_name: Optional[str] = typer.Option(
        None,
        "--group-name",
        help="New display name for the policy group.",
    ),
) -> None:
    """Update an existing NPA policy group.

    Sends PATCH /api/v2/policy/npa/policygroups/{id}.

    Examples:
        netskope npa policy groups update 5 --group-name "Renamed Group"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {}
    if group_name is not None:
        payload["group_name"] = group_name

    if not payload:
        echo_error("No update fields provided. Use --group-name to specify a new value.")
        raise typer.Exit(code=1)

    with spinner(f"Updating NPA policy group {group_id}..."):
        data = client.request("PATCH", f"/api/v2/policy/npa/policygroups/{group_id}", json_data=payload)

    echo_success(f"NPA policy group {group_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated NPA Policy Group {group_id}")


@groups_app.command("delete")
def delete_group(
    ctx: typer.Context,
    group_id: int = typer.Argument(..., help="Numeric ID of the policy group to delete. This action cannot be undone."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and proceed with deletion.",
    ),
) -> None:
    """Delete an NPA policy group.

    Sends DELETE /api/v2/policy/npa/policygroups/{id}. This is a destructive
    operation. Use --yes to skip confirmation.

    Examples:
        netskope npa policy groups delete 5
        netskope npa policy groups delete 5 --yes
    """
    _confirm_delete("NPA policy group", group_id, yes, ctx)

    client = _build_client(ctx)

    with spinner(f"Deleting NPA policy group {group_id}..."):
        client.request("DELETE", f"/api/v2/policy/npa/policygroups/{group_id}")

    echo_success(f"NPA policy group {group_id} deleted.")
