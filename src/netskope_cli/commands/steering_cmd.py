"""Steering configuration commands for the Netskope CLI.

Provides subcommands for managing private applications and the global
steering configuration.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_error, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
steering_app = typer.Typer(
    name="steering",
    help=(
        "Manage traffic steering configuration for private applications.\n\n"
        "This command group controls how traffic is steered to private applications "
        "and manages the global steering configuration. Use these commands to list "
        "and inspect private app steering rules, and to view or update the global "
        "steering settings that control Netskope Client behaviour."
    ),
    no_args_is_help=True,
)

_private_apps_app = typer.Typer(
    name="private-apps",
    help=(
        "List and inspect private applications in the steering configuration.\n\n"
        "Private applications are internal services that traffic is steered to through "
        "Netskope publishers. Use these commands to view which private apps are "
        "configured and inspect their steering rules."
    ),
    no_args_is_help=True,
)

_config_app = typer.Typer(
    name="config",
    help=(
        "View and update the global steering configuration.\n\n"
        "The global steering configuration controls how the Netskope Client steers "
        "traffic. Use 'get' to view the current configuration and 'update' to modify "
        "settings using key=value pairs.\n\n"
        "Running 'steering config' with no subcommand defaults to 'get'."
    ),
    invoke_without_command=True,
)

steering_app.add_typer(_private_apps_app, name="private-apps")
steering_app.add_typer(_config_app, name="config")


@_config_app.callback(invoke_without_command=True)
def _config_default(ctx: typer.Context) -> None:
    """When no subcommand is given, default to 'get'."""
    if ctx.invoked_subcommand is None:
        config_get(ctx, scope=None)


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
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


def _parse_key_value_pairs(values: list[str]) -> dict[str, str]:
    """Parse a list of ``key=value`` strings into a dictionary.

    Raises
    ------
    typer.BadParameter
        If any element does not contain an ``=`` sign.
    """
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise typer.BadParameter(f"Invalid key=value pair: {item!r}. Expected format: key=value")
        key, _, value = item.partition("=")
        result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Private-apps commands
# ---------------------------------------------------------------------------


@_private_apps_app.command("list")
def private_apps_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of private apps to return. Use with --offset for pagination "
            "through large lists. Omit to return all apps."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=("Number of records to skip before returning results. Use with --limit for " "pagination. Defaults to 0."),
    ),
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Filter expression to narrow results. Filter syntax is API-specific and "
            "supports field comparisons. Omit to return all private applications."
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated list of field names to include in the response.",
    ),
    count: bool = typer.Option(False, "--count", help="Print only the total count."),
) -> None:
    """List private applications in the steering configuration.

    Queries GET /api/v2/steering/apps/private to retrieve all private
    applications with their steering rules. Use this to audit which internal
    services are accessible through Netskope and verify their configuration.

    Examples:
        netskope steering private-apps list
        netskope steering private-apps list --limit 20 --offset 0
        netskope -o json steering private-apps list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    state = ctx.obj
    no_color = state.no_color if state is not None else False

    params: dict[str, str | int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter is not None:
        params["filter"] = filter

    with spinner("Fetching private applications...", no_color=no_color):
        data = client.request(
            "GET",
            "/api/v2/steering/apps/private",
            params=params or None,
        )

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title="Steering — Private Applications",
        default_fields=["app_name", "host", "port", "protocol", "publisher_name", "status"],
        fields=field_list,
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@_private_apps_app.command("get")
def private_apps_get(
    ctx: typer.Context,
    id: str = typer.Argument(
        ...,
        help=(
            "The unique ID of the private application to retrieve. Find IDs by running "
            "'netskope steering private-apps list'."
        ),
    ),
) -> None:
    """Retrieve details of a single private application by ID.

    Queries GET /api/v2/steering/apps/private/{id} for the full application
    configuration including host, port, protocol, publisher association, and
    steering rules. Use this to troubleshoot connectivity or verify configuration.

    Examples:
        netskope steering private-apps get app-123
        netskope -o json steering private-apps get app-123
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    path = f"/api/v2/steering/apps/private/{id}"

    with spinner(f"Fetching private application {id}...", no_color=no_color):
        data = client.request("GET", path)

    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"Steering — Private Application {id}",
    )


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------


_SCOPE_ENDPOINTS: dict[str, str] = {
    "npa": "/api/v2/steering/globalconfig/clientconfiguration/npa",
    "publishers": "/api/v2/steering/globalconfig/publishers",
}

_VALID_SCOPES = list(_SCOPE_ENDPOINTS.keys())


@_config_app.command("get")
def config_get(
    ctx: typer.Context,
    scope: Optional[str] = typer.Option(
        None,
        "--scope",
        help=(
            "Limit to a specific configuration scope: 'npa' (client configuration) "
            "or 'publishers'. Omit to retrieve both."
        ),
    ),
) -> None:
    """Retrieve the current global steering configuration.

    Queries the production-enabled globalconfig endpoints for NPA client
    configuration and publisher feature flags. Use --scope to limit to one.

    Examples:
        netskope steering config get
        netskope steering config get --scope npa
        netskope steering config get --scope publishers
        netskope -o json steering config get
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if scope and scope not in _VALID_SCOPES:
        echo_error(
            f"Invalid scope {scope!r}. Choose from: {', '.join(_VALID_SCOPES)}",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    scopes = [scope] if scope else _VALID_SCOPES

    merged: dict[str, object] = {}
    for s in scopes:
        endpoint = _SCOPE_ENDPOINTS[s]
        with spinner(f"Fetching {s} config...", no_color=no_color):
            data = client.request("GET", endpoint)
        if isinstance(data, dict):
            # Nest under the scope name so it's clear which flags belong where.
            inner = data.get("data", data)
            merged[s] = inner
        elif data is not None:
            merged[s] = data

    formatter.format_output(
        merged,
        fmt=_get_output_format(ctx),
        title="Steering — Global Configuration",
    )


# Hidden alias so "steering config list" also works.
_config_app.command("list", hidden=True)(config_get)


@_config_app.command("update")
def config_update(
    ctx: typer.Context,
    scope: str = typer.Option(
        ...,
        "--scope",
        help=("Configuration scope to update: 'npa' (client configuration) " "or 'publishers'."),
    ),
    set_values: Optional[list[str]] = typer.Option(
        None,
        "--set",
        help=(
            "Configuration key=value pair to update. Can be repeated for multiple "
            "settings. For example: --set 'flag_name=1' --set 'other_flag=0'. "
            "At least one --set flag is required."
        ),
    ),
) -> None:
    """Update the global steering configuration with key=value pairs.

    Sends PATCH to the scoped globalconfig endpoint with the provided settings.
    This modifies the live steering configuration and affects how the Netskope
    Client steers traffic. Review the current config with 'steering config get'
    before making changes.

    Examples:
        netskope steering config update --scope npa --set flag_name=1
        netskope steering config update --scope publishers --set flag_a=1 --set flag_b=0
        netskope -o json steering config update --scope npa --set flag_name=1
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if scope not in _VALID_SCOPES:
        echo_error(
            f"Invalid scope {scope!r}. Choose from: {', '.join(_VALID_SCOPES)}",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    if not set_values:
        echo_error(
            "No configuration values provided. Use --set key=value to specify updates.",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    payload = _parse_key_value_pairs(set_values)
    endpoint = _SCOPE_ENDPOINTS[scope]

    with spinner(f"Updating {scope} steering config...", no_color=no_color):
        data = client.request(
            "PATCH",
            endpoint,
            json_data=payload,
        )

    if data is not None:
        formatter.format_output(
            data,
            fmt=_get_output_format(ctx),
            title=f"Steering — Updated {scope.upper()} Configuration",
        )
    else:
        from netskope_cli.core.output import echo_success

        echo_success(
            f"Steering {scope} configuration updated successfully.",
            no_color=no_color,
        )
