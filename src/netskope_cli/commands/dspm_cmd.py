"""DSPM (Data Security Posture Management) commands for the Netskope CLI.

Provides subcommands for querying DSPM resources, connecting datastores,
triggering scans, and retrieving analytics metrics.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import NotFoundError
from netskope_cli.core.output import OutputFormatter, echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------
dspm_app = typer.Typer(
    name="dspm",
    help=(
        "Data Security Posture Management (DSPM) operations.\n\n"
        "This command group provides access to Netskope DSPM capabilities including "
        "querying resources (datastores, databases, schemas, tables, columns), "
        "connecting discovered datastores, triggering classification scans, and "
        "retrieving analytics metrics. Use these commands to monitor sensitive data "
        "exposure and enforce data security policies across your cloud environment."
    ),
    no_args_is_help=True,
)

_datastores_app = typer.Typer(
    name="datastores",
    help=(
        "Connect discovered datastores and trigger classification scans.\n\n"
        "Use 'connect' to register discovered datastores for monitoring, and "
        "'scan' to trigger on-demand data classification scans. Scans identify "
        "sensitive data types such as PII, PCI, and PHI across your datastores."
    ),
    no_args_is_help=True,
)

dspm_app.add_typer(_datastores_app, name="datastores")


# ---------------------------------------------------------------------------
# Resource type enum
# ---------------------------------------------------------------------------
class ResourceType(str, Enum):
    connected_datastores = "connected_datastores"
    databases = "databases"
    schemas = "schemas"
    tables = "tables"
    columns = "columns"
    sensitive_data_types = "sensitive_data_types"
    data_tags = "data_tags"
    scans = "scans"
    policy_violations = "policy_violations"
    assessment_summary = "assessment_summary"
    classification_columns = "classification_columns"
    sidecar_pools = "sidecar_pools"
    infrastructure_connections = "infrastructure_connections"
    infrastructure_platforms = "infrastructure_platforms"
    archived_datastores = "archived_datastores"
    discovered_datastores = "discovered_datastores"
    data_tag_categories = "data_tag_categories"
    sensitive_data_type_categories = "sensitive_data_type_categories"
    supported_data_types = "supported_data_types"
    sensitivity_levels = "sensitivity_levels"
    classification_files = "classification_files"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dspm_app.command("resources")
def resources(
    ctx: typer.Context,
    resource_type: ResourceType = typer.Argument(
        ...,
        help=(
            "The DSPM resource type to query. Valid values include: connected_datastores, "
            "databases, schemas, tables, columns, sensitive_data_types, data_tags, scans, "
            "policy_violations, assessment_summary, classification_columns, sidecar_pools, "
            "infrastructure_connections, infrastructure_platforms, archived_datastores, "
            "discovered_datastores, data_tag_categories, sensitive_data_type_categories, "
            "supported_data_types, sensitivity_levels, classification_files."
        ),
    ),
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help=(
            "Filter expression to narrow results. The filter syntax is specific to the "
            "DSPM API and supports field comparisons. For example: 'name eq \"prod-db\"'. "
            "Omit to return all resources of the given type."
        ),
    ),
    sortby: Optional[str] = typer.Option(
        None,
        "--sortby",
        help=(
            "Field name to sort results by. Available fields depend on the resource type. "
            "Common fields include 'name', 'created_at', and 'updated_at'. "
            "Omit to use the API default sort order."
        ),
    ),
    sortorder: Optional[SortOrder] = typer.Option(
        None,
        "--sortorder",
        help=(
            "Sort direction for the results. Valid values: 'asc' (ascending) or "
            "'desc' (descending). Only applies when --sortby is also set. "
            "Defaults to ascending if omitted."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of records to skip before returning results. Use with --limit for "
            "pagination through large datasets. Defaults to 0."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of records to return. Use for pagination with large result "
            "sets. Omit to return all matching resources (subject to API limits)."
        ),
    ),
) -> None:
    """List DSPM resources of the specified type with optional filtering.

    Queries GET /api/v2/dspm/{resource_type} with optional filtering, sorting,
    and pagination. Use this to explore your data security posture, find sensitive
    data, review scan results, and audit policy violations.

    Examples:
        netskope dspm resources connected_datastores
        netskope dspm resources tables --filter 'name eq "users"' --limit 20
        netskope -o json dspm resources policy_violations --sortby created_at --sortorder desc
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    params: dict[str, str | int] = {}
    if filter is not None:
        params["filter"] = filter
    if sortby is not None:
        params["sortby"] = sortby
    if sortorder is not None:
        params["sortorder"] = sortorder.value
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    path = f"/api/v2/dspm/{resource_type.value}"

    try:
        with spinner(f"Fetching {resource_type.value}...", no_color=no_color):
            data = client.request("GET", path, params=params or None)
    except NotFoundError:
        echo_error(
            "This endpoint may not be available on your tenant (HTTP 404).",
            no_color=no_color,
        )
        raise typer.Exit(code=1)

    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"DSPM — {resource_type.value}",
    )


@dspm_app.command("analytics")
def analytics(
    ctx: typer.Context,
    metric_type: str = typer.Argument(
        ...,
        help=(
            "The analytics metric type to retrieve. Available metrics depend on your "
            "DSPM configuration and may include summary statistics, trend data, and "
            "risk scores across your datastores."
        ),
    ),
) -> None:
    """Retrieve DSPM analytics for a specific metric type.

    Queries GET /api/v2/dspm/analytics/{metric_type} for aggregated DSPM
    statistics and trend data. Use this to build dashboards, generate reports,
    and monitor your data security posture over time.

    Examples:
        netskope dspm analytics summary
        netskope -o json dspm analytics risk_score
        netskope -o json dspm analytics sensitivity_trends
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    path = f"/api/v2/dspm/analytics/{metric_type}"

    with spinner(f"Fetching analytics ({metric_type})...", no_color=no_color):
        data = client.request("GET", path)

    formatter.format_output(
        data,
        fmt=_get_output_format(ctx),
        title=f"DSPM Analytics — {metric_type}",
    )


# ---------------------------------------------------------------------------
# Datastores sub-commands
# ---------------------------------------------------------------------------


@_datastores_app.command("connect")
def datastores_connect(
    ctx: typer.Context,
    ids: str = typer.Option(
        ...,
        "--ids",
        help=(
            "Comma-separated list of discovered datastore IDs to connect. Find IDs by "
            "running 'netskope dspm resources discovered_datastores'. For example: "
            "'ds-001,ds-002,ds-003'. At least one ID is required."
        ),
    ),
) -> None:
    """Connect one or more discovered datastores for DSPM monitoring.

    Sends POST /api/v2/dspm/connected_datastores to register discovered
    datastores for ongoing monitoring and classification. Once connected,
    datastores can be scanned for sensitive data. Use 'dspm resources
    discovered_datastores' first to find available datastores.

    Examples:
        netskope dspm datastores connect --ids ds-001
        netskope dspm datastores connect --ids "ds-001,ds-002,ds-003"
        netskope -o json dspm datastores connect --ids ds-001
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    id_list = [item.strip() for item in ids.split(",") if item.strip()]
    if not id_list:
        echo_error("No datastore IDs provided.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": id_list}

    with spinner("Connecting datastores...", no_color=no_color):
        data = client.request(
            "POST",
            "/api/v2/dspm/connected_datastores",
            json_data=payload,
        )

    if data is not None:
        formatter.format_output(
            data,
            fmt=_get_output_format(ctx),
            title="DSPM — Connect Datastores",
        )
    else:
        echo_success(
            f"Datastores connected successfully: {', '.join(id_list)}",
            no_color=no_color,
        )


@_datastores_app.command("scan")
def datastores_scan(
    ctx: typer.Context,
    ids: str = typer.Option(
        ...,
        "--ids",
        help=(
            "Comma-separated list of connected datastore IDs to scan. The datastores "
            "must already be connected (use 'dspm datastores connect' first). "
            "For example: 'ds-001,ds-002'. At least one ID is required."
        ),
    ),
) -> None:
    """Trigger an on-demand classification scan on one or more datastores.

    Sends POST /api/v2/dspm/scans to initiate data classification. Scans
    identify sensitive data types (PII, PCI, PHI, etc.) across tables and
    columns. Scan results are available via 'dspm resources scans'. Scans
    may take several minutes to complete depending on datastore size.

    Examples:
        netskope dspm datastores scan --ids ds-001
        netskope dspm datastores scan --ids "ds-001,ds-002,ds-003"
        netskope -o json dspm datastores scan --ids ds-001
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    id_list = [item.strip() for item in ids.split(",") if item.strip()]
    if not id_list:
        echo_error("No datastore IDs provided.", no_color=no_color)
        raise typer.Exit(code=1)

    payload = {"ids": id_list}

    with spinner("Triggering scans...", no_color=no_color):
        data = client.request(
            "POST",
            "/api/v2/dspm/scans",
            json_data=payload,
        )

    if data is not None:
        formatter.format_output(
            data,
            fmt=_get_output_format(ctx),
            title="DSPM — Scan Datastores",
        )
    else:
        echo_success(
            f"Scans triggered successfully for: {', '.join(id_list)}",
            no_color=no_color,
        )
