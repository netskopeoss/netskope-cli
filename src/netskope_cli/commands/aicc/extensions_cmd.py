"""AICC AI extension inventory commands (``ntsk aicc extensions``)."""

from __future__ import annotations

import urllib.parse
from enum import Enum
from typing import Optional

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_ALL,
    HELP_END,
    HELP_LIMIT,
    HELP_OFFSET,
    HELP_SEARCH,
    HELP_START,
    add_filters,
    aicc_get,
    resolve_time_range,
    run_list,
    show_payload,
    unwrap_data,
)

extensions_app = typer.Typer(
    name="extensions",
    help=(
        "AI extension inventory — browser, editor, and desktop AI extensions on devices.\n\n"
        "Extensions (e.g. the Claude browser extension, Copilot editor plugins) are "
        "discovered on managed endpoints. There is no list endpoint — extension names "
        "surface in agents/apps inventories and footprints; use 'get' with the exact "
        "name plus a --type."
    ),
    no_args_is_help=True,
)


class _ExtensionType(str, Enum):
    browser_extension = "browser_extension"
    editor_extension = "editor_extension"
    desktop_extension = "desktop_extension"


class _SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class _IdentitySort(str, Enum):
    name_ = "name"
    bytes_ = "bytes"


def _ext_path(extension_name: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/extensions/{urllib.parse.quote(extension_name, safe='')}{suffix}"


@extensions_app.command("get")
def get_extension(
    ctx: typer.Context,
    extension_name: str = typer.Argument(
        ..., help="Exact extension name, e.g. 'Claude'. Case-sensitive; quote names with spaces."
    ),
    extension_type: Optional[_ExtensionType] = typer.Option(
        None,
        "--type",
        "-t",
        help="Extension class: browser_extension, editor_extension, or desktop_extension.",
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show details for one AI extension.

    Queries GET /api/v2/aicc/inventory/extensions/{extension_name}. Returns
    metadata (extension_id, version, publisher, device_count,
    identity_count), the browser/editor distribution, and associated
    identities.

    Examples:
        ntsk aicc extensions get Claude --type browser_extension
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(params, type=extension_type.value if extension_type else None)
    response = aicc_get(ctx, _ext_path(extension_name), params, spinner_text=f"Fetching {extension_name}...")
    show_payload(ctx, unwrap_data(response), title=f"AICC Extension — {extension_name}")


@extensions_app.command("deployments")
def extension_deployments(
    ctx: typer.Context,
    extension_name: str = typer.Argument(..., help="Exact extension name, e.g. 'Claude'."),
    extension_type: _ExtensionType = typer.Option(
        ...,
        "--type",
        "-t",
        help="Extension class (required): browser_extension, editor_extension, or desktop_extension.",
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List devices where an extension is installed.

    Queries GET /api/v2/aicc/inventory/extensions/{extension_name}/deployments.

    Examples:
        ntsk aicc extensions deployments Claude --type browser_extension
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "type": extension_type.value}
    add_filters(params, search=search)
    run_list(
        ctx,
        _ext_path(extension_name, "/deployments"),
        params,
        title=f"AICC Extension Deployments — {extension_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
    )


@extensions_app.command("identities")
def extension_identities(
    ctx: typer.Context,
    extension_name: str = typer.Argument(..., help="Exact extension name, e.g. 'Claude'."),
    extension_type: Optional[_ExtensionType] = typer.Option(
        None,
        "--type",
        "-t",
        help="Extension class: browser_extension, editor_extension, or desktop_extension.",
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _IdentitySort = typer.Option(_IdentitySort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the identities that installed an extension.

    Queries GET /api/v2/aicc/inventory/extensions/{extension_name}/identities.

    Examples:
        ntsk aicc extensions identities Claude --type browser_extension
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {
        "start_time": start_iso,
        "end_time": end_iso,
        "sort_by": sort_by.value,
        "sort_dir": sort_dir.value,
    }
    add_filters(params, search=search, type=extension_type.value if extension_type else None)
    run_list(
        ctx,
        _ext_path(extension_name, "/identities"),
        params,
        title=f"AICC Extension Identities — {extension_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
    )
