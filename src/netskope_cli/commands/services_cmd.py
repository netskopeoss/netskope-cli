"""Services and CCI commands for the Netskope CLI.

Provides subcommands for Cloud Confidence Index (CCI) lookups, tag
management, publisher listing, and private-app management.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

services_app = typer.Typer(
    name="services",
    help=(
        "Cloud Confidence Index (CCI) lookups, service tags, publishers, and private apps.\n\n"
        "This command group lets you look up CCI risk scores for cloud applications, "
        "manage service tags for categorization, list publishers for private access, "
        "and create or list private applications. Use these commands to assess SaaS "
        "application risk and manage your Netskope service catalog."
    ),
    no_args_is_help=True,
)

tags_app = typer.Typer(
    name="tags",
    help=(
        "Create, list, update, and delete CCI service tags.\n\n"
        "Service tags are labels that can be applied to cloud applications for "
        "categorization and policy targeting. Tags help organize apps by business "
        "function, risk level, or compliance requirement."
    ),
    no_args_is_help=True,
)

publishers_app = typer.Typer(
    name="publishers",
    help=(
        "List and inspect Netskope publishers.\n\n"
        "Publishers are on-premises or cloud-hosted connectors that enable secure "
        "access to private applications. Use these commands to view publisher status "
        "and configuration."
    ),
    no_args_is_help=True,
)

private_apps_app = typer.Typer(
    name="private-apps",
    help=(
        "Create and list private applications.\n\n"
        "Private applications are internal services (e.g., intranet, internal APIs) "
        "that are accessed through Netskope publishers. Use these commands to "
        "register new private apps or view existing ones."
    ),
    no_args_is_help=True,
)

services_app.add_typer(tags_app, name="tags")
services_app.add_typer(publishers_app, name="publishers")
services_app.add_typer(private_apps_app, name="private-apps")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an :class:`OutputFormatter` respecting global flags."""
    state = ctx.obj
    no_color = state.no_color if state else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _output_format(ctx: typer.Context) -> str:
    """Return the user-requested output format string."""
    state = ctx.obj
    return state.output.value if state else "table"


# ---------------------------------------------------------------------------
# CCI command
# ---------------------------------------------------------------------------


@services_app.command("cci")
def cci(
    ctx: typer.Context,
    app_name: Optional[str] = typer.Argument(
        None,
        help=(
            "Name of the cloud application to look up. Must match the application name "
            "as indexed by Netskope CCI (e.g. 'Box', 'Dropbox', 'Slack'). The CCI API "
            "requires an exact app name — partial names and wildcards are not supported."
        ),
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help=(
            "Filter results by application category such as 'Cloud Storage', 'Collaboration', "
            "or 'Social Media'. Omit to include all categories. Categories are defined by "
            "the Netskope CCI database."
        ),
    ),
    ccl: Optional[str] = typer.Option(
        None,
        "--ccl",
        help=(
            "Filter by Cloud Confidence Level rating. Valid values: 'excellent', 'high', "
            "'medium', 'low', 'poor'. Use this to find apps that meet or fail your risk "
            "threshold. Omit to include all confidence levels."
        ),
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help=(
            "Filter results by a specific service tag name. Tags are custom labels applied "
            "to applications for categorization. Omit to include apps regardless of tags."
        ),
    ),
    connector: Optional[str] = typer.Option(
        None,
        "--connector",
        help=(
            "Filter results by connector type. Connectors enable API-based access to cloud "
            "apps for inline and out-of-band protection. Omit to include all connector types."
        ),
    ),
    discovered: Optional[bool] = typer.Option(
        None,
        "--discovered",
        help=(
            "Filter by discovery status. Set to True to show only discovered (shadow IT) "
            "apps, or False for sanctioned apps only. Omit to include both."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of CCI results to return. Use for pagination with large "
            "result sets. Omit to return all matching results."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of results to skip for pagination. Combine with --limit to page " "through results. Defaults to 0."
        ),
    ),
) -> None:
    """Look up Cloud Confidence Index (CCI) risk data for a cloud application.

    Queries GET /api/v2/services/cci/app for risk ratings, compliance posture,
    and security attributes of cloud applications. The CCI score helps security
    teams assess whether an app is safe to use and which policies to apply.

    The CCI API requires an exact application name — it does not support
    listing all apps or partial/wildcard searches. To browse apps, use the
    Netskope admin console or query application events with
    'ntsk events application'.

    Examples:
        netskope services cci Dropbox
        netskope -o json services cci Box --ccl excellent
        netskope services cci Slack --category Collaboration --limit 5
    """
    if app_name is None:
        from rich.console import Console

        state = ctx.obj
        no_color = state.no_color if state is not None else False
        console = Console(no_color=no_color, stderr=True)
        console.print(
            "[yellow]CCI lookup requires an application name.[/yellow]\n\n"
            "The CCI API does not support listing all apps. You must specify an\n"
            "exact application name (e.g. 'Dropbox', 'Box', 'Slack').\n\n"
            "Examples:\n"
            "  [bold]ntsk services cci Dropbox[/bold]\n"
            "  [bold]ntsk services cci Box --ccl excellent -o json[/bold]\n\n"
            "[dim]To browse discovered apps, use: ntsk events application --limit 50[/dim]"
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    params: dict[str, object] = {"apps": app_name}
    if category is not None:
        params["category"] = category
    if ccl is not None:
        params["ccl"] = ccl
    if tag is not None:
        params["tag"] = tag
    if connector is not None:
        params["connector"] = connector
    if discovered is not None:
        params["discovered"] = discovered
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    data = client.request("GET", "/api/v2/services/cci/app", params=params)
    fmt.format_output(
        data,
        fmt=_output_format(ctx),
        title=f"CCI — {app_name}",
        empty_hint="No CCI records found. This may require API Connector configuration.",
    )


# ---------------------------------------------------------------------------
# Tags commands
# ---------------------------------------------------------------------------


@tags_app.command("list")
def tags_list(
    ctx: typer.Context,
    apps: Optional[str] = typer.Option(
        None,
        "--apps",
        help=(
            "Semicolon-separated list of application names to filter tags by. "
            "For example: 'Box;Dropbox;Slack'. When provided, only tags associated "
            "with the specified apps are returned. Omit to list all tags."
        ),
    ),
) -> None:
    """List all CCI service tags, optionally filtered by application.

    Queries GET /api/v2/services/cci/tags (filtered) or /tags/all (unfiltered).
    Service tags categorize cloud applications for policy targeting. Use this to
    see which tags exist and which apps they are applied to.

    Examples:
        netskope services tags list
        netskope services tags list --apps "Box;Dropbox"
        netskope -o json services tags list
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    if apps:
        data = client.request("GET", "/api/v2/services/cci/tags", params={"apps": apps})
    else:
        data = client.request("GET", "/api/v2/services/cci/tags/all")
    fmt.format_output(data, fmt=_output_format(ctx), title="Service Tags")


@tags_app.command("get")
def tags_get(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the service tag to retrieve. Find tag IDs by running " "'netskope services tags list'."),
    ),
) -> None:
    """Retrieve details for a specific service tag by ID.

    Queries GET /api/v2/services/cci/tags/{id} for tag name, associated apps,
    and metadata. Use this to inspect a tag before updating or deleting it.

    Examples:
        netskope services tags get 5
        netskope -o json services tags get 5
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    data = client.request("GET", f"/api/v2/services/cci/tags/{tag_id}")
    fmt.format_output(data, fmt=_output_format(ctx), title=f"Tag {tag_id}")


@tags_app.command("create")
def tags_create(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "Display name for the new service tag. Should be descriptive and unique, "
            "such as 'Finance-Approved' or 'High-Risk-Apps'."
        ),
    ),
    apps: Optional[str] = typer.Option(
        None,
        "--apps",
        help=(
            "Comma-separated list of application names to associate with the tag. "
            "For example: 'Box,Dropbox,OneDrive'. Omit to create the tag without "
            "any app associations (apps can be added later via update)."
        ),
    ),
) -> None:
    """Create a new CCI service tag with optional app associations.

    Sends POST /api/v2/services/cci/tags to create a tag that can be used to
    categorize cloud applications. Tags enable policy targeting by business
    function, risk level, or compliance requirement.

    Examples:
        netskope services tags create "Finance-Approved"
        netskope services tags create "High-Risk" --apps "TikTok,Reddit,4chan"
        netskope -o json services tags create "HIPAA-Compliant" --apps "Box,Zoom"
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    body: dict[str, object] = {"tag_name": name}
    if apps is not None:
        body["apps"] = [a.strip() for a in apps.split(",") if a.strip()]

    data = client.request("POST", "/api/v2/services/cci/tags", json_data=body)

    state = ctx.obj
    no_color = state.no_color if state else False
    echo_success(f"Tag '{name}' created.", no_color=no_color)
    if data:
        fmt.format_output(data, fmt=_output_format(ctx), title="Created Tag")


@tags_app.command("update")
def tags_update(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help="Numeric ID of the tag to update. Find IDs via 'netskope services tags list'.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=("New display name for the tag. Omit to keep the current name. " "Must be unique within your tenant."),
    ),
    apps: Optional[str] = typer.Option(
        None,
        "--apps",
        help=(
            "Comma-separated list of app names to associate with the tag. This REPLACES "
            "the current app associations. Include all desired apps. "
            "For example: 'Box,Dropbox,OneDrive'."
        ),
    ),
) -> None:
    """Update an existing service tag's name or app associations.

    Sends PUT /api/v2/services/cci/tags/{id} with the provided changes. At least
    one of --name or --apps must be specified. App associations are fully replaced,
    not merged.

    Examples:
        netskope services tags update 5 --name "Updated Tag Name"
        netskope services tags update 5 --apps "Slack,Teams,Zoom"
        netskope services tags update 5 --name "Finance" --apps "QuickBooks,Xero"
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    body: dict[str, object] = {}
    if name is not None:
        body["tag_name"] = name
    if apps is not None:
        body["apps"] = [a.strip() for a in apps.split(",") if a.strip()]

    if not body:
        typer.echo("Nothing to update. Provide --name and/or --apps.", err=True)
        raise typer.Exit(code=1)

    data = client.request("PUT", f"/api/v2/services/cci/tags/{tag_id}", json_data=body)

    state = ctx.obj
    no_color = state.no_color if state else False
    echo_success(f"Tag {tag_id} updated.", no_color=no_color)
    if data:
        fmt.format_output(data, fmt=_output_format(ctx), title=f"Updated Tag {tag_id}")


@tags_app.command("delete")
def tags_delete(
    ctx: typer.Context,
    tag_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the tag to delete. Find IDs via 'netskope services tags list'. "
            "This action cannot be undone."
        ),
    ),
) -> None:
    """Delete a service tag by ID.

    Sends DELETE /api/v2/services/cci/tags/{id}. This permanently removes the
    tag and its app associations. Policies referencing this tag may need to be
    updated.

    Examples:
        netskope services tags delete 5
    """
    client = _build_client(ctx)

    client.request("DELETE", f"/api/v2/services/cci/tags/{tag_id}")

    state = ctx.obj
    no_color = state.no_color if state else False
    echo_success(f"Tag {tag_id} deleted.", no_color=no_color)


# ---------------------------------------------------------------------------
# Publishers commands
# ---------------------------------------------------------------------------


@publishers_app.command("list")
def publishers_list(
    ctx: typer.Context,
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help=(
            "Maximum number of publishers to return. Defaults to 25. "
            "Increase for larger exports or decrease for quick lookups."
        ),
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        help=(
            "Number of records to skip for pagination. Combine with --limit " "to page through results. Defaults to 0."
        ),
    ),
    fields: str | None = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated list of field names to include in the response.",
    ),
    count: bool = typer.Option(False, "--count", help="Print only the total count."),
) -> None:
    """List all publishers registered in the tenant.

    Queries GET /api/v2/services/publisher to retrieve all publishers. Publishers
    are connectors that enable secure access to private applications. Use this to
    find publisher IDs needed for private app creation.

    Examples:
        netskope services publishers list
        netskope -o json services publishers list
        netskope services publishers list --limit 50 --offset 0
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    params: dict[str, object] = {"limit": limit, "offset": offset}
    data = client.request("GET", "/api/v2/infrastructure/publishers", params=params)
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    state = ctx.obj
    fmt.format_output(
        data,
        fmt=_output_format(ctx),
        title="Publishers",
        fields=field_list,
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@publishers_app.command("get")
def publishers_get(
    ctx: typer.Context,
    publisher_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the publisher to retrieve. Find IDs via " "'netskope services publishers list'."),
    ),
) -> None:
    """Retrieve details for a specific publisher by ID.

    Queries GET /api/v2/services/publisher/{id} for publisher name, status,
    version, and configuration. Use this to verify publisher health or
    troubleshoot connectivity issues.

    Examples:
        netskope services publishers get 10
        netskope -o json services publishers get 10
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    data = client.request("GET", f"/api/v2/infrastructure/publishers/{publisher_id}")
    fmt.format_output(data, fmt=_output_format(ctx), title=f"Publisher {publisher_id}")


# ---------------------------------------------------------------------------
# Private Apps commands
# ---------------------------------------------------------------------------


@private_apps_app.command("list")
def private_apps_list(
    ctx: typer.Context,
    fields: str | None = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated list of field names to include in the response.",
    ),
    count: bool = typer.Option(False, "--count", help="Print only the total count."),
) -> None:
    """List all private applications configured in the tenant.

    Queries GET /api/v2/services/privateapps to retrieve all registered private
    applications. Private apps are internal services accessed through publishers.
    Use this to audit your private app inventory or find app details.

    Examples:
        netskope services private-apps list
        netskope -o json services private-apps list
        netskope services private-apps list --fields app_name,host,port
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    data = client.request("GET", "/api/v2/steering/apps/private")
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    state = ctx.obj
    fmt.format_output(
        data,
        fmt=_output_format(ctx),
        title="Private Apps",
        fields=field_list,
        default_fields=["app_name", "host", "port", "protocol", "publisher_name", "status"],
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@private_apps_app.command("get")
def private_apps_get(
    ctx: typer.Context,
    app_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the private application to retrieve. " "Find IDs via 'netskope services private-apps list'."
        ),
    ),
) -> None:
    """Retrieve details of a specific private application by ID.

    Queries GET /api/v2/steering/apps/private/{id} for the full app
    definition including host, port, protocol, and publisher assignment.

    Examples:
        netskope services private-apps get 10
        netskope -o json services private-apps get 10
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    data = client.request("GET", f"/api/v2/steering/apps/private/{app_id}")
    state = ctx.obj
    fmt.format_output(
        data,
        fmt=_output_format(ctx),
        title=f"Private App {app_id}",
        default_fields=[
            "app_name",
            "host",
            "protocols",
            "publisher_name",
            "status",
            "id",
            "reachability",
            "use_publisher_dns",
            "clientless_access",
        ],
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@private_apps_app.command("create")
def private_apps_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        help=(
            "Display name for the private application. Should be descriptive and "
            "identifiable, such as 'Internal Wiki' or 'Jenkins CI'. Must be unique."
        ),
    ),
    host: str = typer.Option(
        ...,
        "--host",
        help=(
            "Hostname, FQDN, or IP address of the private application. This is the "
            "address the publisher will use to reach the app. For example: "
            "'wiki.internal.corp' or '10.0.1.50'."
        ),
    ),
    port: int = typer.Option(
        ...,
        "--port",
        help=(
            "Port number the private application listens on. Common values: 443 (HTTPS), "
            "80 (HTTP), 22 (SSH), 3389 (RDP). Must be between 1 and 65535."
        ),
    ),
    protocol: str = typer.Option(
        "TCP",
        "--protocol",
        help=(
            "Network protocol for the application. Valid values: 'TCP' or 'UDP'. "
            "Most web applications use TCP. Defaults to 'TCP'."
        ),
    ),
    publisher_id: int = typer.Option(
        ...,
        "--publisher-id",
        help=(
            "ID of the publisher that provides connectivity to this private app. "
            "Find publisher IDs via 'netskope services publishers list'. The publisher "
            "must be deployed and reachable from the app's network."
        ),
    ),
) -> None:
    """Register a new private application with a publisher.

    Sends POST /api/v2/services/privateapps to create a private app definition.
    The app will be accessible through the specified publisher once steering
    rules are configured. Use this when onboarding new internal services.

    Examples:
        netskope services private-apps create --name "Internal Wiki" \\
            --host wiki.corp.local --port 443 --publisher-id 10
        netskope services private-apps create --name "Jenkins" \\
            --host 10.0.1.50 --port 8080 --protocol TCP --publisher-id 5
    """
    client = _build_client(ctx)
    fmt = _get_formatter(ctx)

    body: dict[str, object] = {
        "app_name": name,
        "host": host,
        "port": port,
        "protocol": protocol,
        "publisher_id": publisher_id,
    }

    data = client.request("POST", "/api/v2/steering/apps/private", json_data=body)

    state = ctx.obj
    no_color = state.no_color if state else False
    echo_success(f"Private app '{name}' created.", no_color=no_color)
    if data:
        fmt.format_output(data, fmt=_output_format(ctx), title="Created Private App")
