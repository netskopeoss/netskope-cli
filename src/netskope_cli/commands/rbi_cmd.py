"""Remote Browser Isolation commands for the Netskope CLI.

Provides subcommands to list RBI applications, supported browsers, default
categories, and manage RBI templates via the Netskope RBI API.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
rbi_app = typer.Typer(
    name="rbi",
    help="Remote Browser Isolation management.",
    no_args_is_help=True,
)

_apps_app = typer.Typer(
    name="apps",
    help="Manage RBI applications.",
    no_args_is_help=True,
)
rbi_app.add_typer(_apps_app, name="apps")

_templates_app = typer.Typer(
    name="templates",
    help="Manage RBI templates.",
    no_args_is_help=True,
)
rbi_app.add_typer(_templates_app, name="templates")


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
# Commands — apps
# ---------------------------------------------------------------------------


@_apps_app.command("list")
def list_apps(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of RBI applications to return.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Offset for pagination (number of records to skip).",
    ),
) -> None:
    """List all Remote Browser Isolation applications.

    Retrieves the list of applications configured for Remote Browser
    Isolation via GET /api/v2/rbi/applications. RBI applications define
    which web applications are rendered through isolated browser sessions
    to protect users from web-based threats.

    Results can be paginated using --limit and --offset.

    Examples:

        # List all RBI applications
        netskope rbi apps list

        # List the first 10 RBI applications
        netskope rbi apps list --limit 10

        # Paginate through results
        netskope rbi apps list --limit 20 --offset 20

        # Output as JSON for scripting
        netskope -o json rbi apps list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching RBI applications..."):
        data = client.request("GET", "/api/v2/rbi/applications", params=params or None)

    formatter.format_output(data, fmt=fmt, title="RBI Applications")


# ---------------------------------------------------------------------------
# Commands — browsers
# ---------------------------------------------------------------------------


@rbi_app.command("browsers")
def list_browsers(
    ctx: typer.Context,
) -> None:
    """List supported browsers for Remote Browser Isolation.

    Retrieves the list of browser types that can be used with RBI via
    GET /api/v2/rbi/browsers/supported. This is a reference endpoint
    that returns the browser engines and versions supported for isolated
    rendering sessions.

    Examples:

        # List supported browsers
        netskope rbi browsers

        # Output as JSON
        netskope -o json rbi browsers

        # Output as YAML
        netskope -o yaml rbi browsers
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching supported browsers..."):
        data = client.request("GET", "/api/v2/rbi/browsers/supported")

    formatter.format_output(data, fmt=fmt, title="RBI Supported Browsers")


# ---------------------------------------------------------------------------
# Commands — categories
# ---------------------------------------------------------------------------


@rbi_app.command("categories")
def list_categories(
    ctx: typer.Context,
) -> None:
    """List default RBI URL categories.

    Retrieves the default URL categories for Remote Browser Isolation via
    GET /api/v2/rbi/categories/default. These categories define the types
    of web content that are routed through isolated browser sessions by
    default (e.g. uncategorized sites, newly registered domains).

    Examples:

        # List default RBI categories
        netskope rbi categories

        # Output as JSON
        netskope -o json rbi categories

        # Output as CSV for spreadsheet import
        netskope -o csv rbi categories
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching default RBI categories..."):
        data = client.request("GET", "/api/v2/rbi/categories/default")

    formatter.format_output(data, fmt=fmt, title="RBI Default Categories")


# ---------------------------------------------------------------------------
# Commands — templates list / get
# ---------------------------------------------------------------------------


@_templates_app.command("list")
def list_templates(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of RBI templates to return.",
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help="Offset for pagination (number of records to skip).",
    ),
) -> None:
    """List all RBI templates.

    Retrieves the list of Remote Browser Isolation templates via
    GET /api/v2/rbi/templates. Templates define the isolation profile
    settings including rendering mode, clipboard policies, file upload
    and download restrictions, and other security controls applied to
    isolated browser sessions.

    Results can be paginated using --limit and --offset.

    Examples:

        # List all RBI templates
        netskope rbi templates list

        # List the first 5 templates
        netskope rbi templates list --limit 5

        # Paginate through results
        netskope rbi templates list --limit 10 --offset 10

        # Output as JSON
        netskope -o json rbi templates list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    with spinner("Fetching RBI templates..."):
        data = client.request("GET", "/api/v2/rbi/templates", params=params or None)

    formatter.format_output(data, fmt=fmt, title="RBI Templates")


@_templates_app.command("get")
def get_template(
    ctx: typer.Context,
    template_id: int = typer.Argument(
        ...,
        help="The unique identifier of the RBI template to retrieve.",
    ),
) -> None:
    """Get details of a specific RBI template.

    Retrieves a single Remote Browser Isolation template by its ID via
    GET /api/v2/rbi/templates/{id}. Returns the full template definition
    including isolation mode, clipboard settings, file transfer policies,
    and other security controls.

    Examples:

        # Get RBI template with ID 1
        netskope rbi templates get 1

        # Output as YAML
        netskope -o yaml rbi templates get 1

        # Output as JSON for scripting
        netskope -o json rbi templates get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching RBI template {template_id}..."):
        data = client.request("GET", f"/api/v2/rbi/templates/{template_id}")

    formatter.format_output(data, fmt=fmt, title=f"RBI Template {template_id}")
