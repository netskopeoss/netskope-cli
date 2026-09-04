"""AICC AI model inventory commands (``ntsk aicc models``)."""

from __future__ import annotations

import urllib.parse
from enum import Enum
from typing import Optional

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_ACTIVE_ONLY,
    HELP_ALL,
    HELP_END,
    HELP_FIRST_SEEN_AFTER,
    HELP_LIMIT,
    HELP_OFFSET,
    HELP_SEARCH,
    HELP_START,
    HELP_TIMEZONE,
    add_filters,
    aicc_get,
    build_sort,
    resolve_single_time,
    resolve_time_range,
    run_list,
    show_payload,
    unwrap_data,
)

models_app = typer.Typer(
    name="models",
    help=(
        "AI model inventory — foundation and local models observed in your traffic.\n\n"
        "Covers both hosted models (API calls to providers) and locally-run models "
        "(e.g. Ollama, LM Studio on endpoints — names like 'qwen3:1.7b'). Each row "
        "includes provider, footprint (where the model runs), traffic bytes, and the "
        "number of identities using it. Local models on endpoints are a shadow-AI "
        "signal worth reviewing."
    ),
    no_args_is_help=True,
)


class _SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class _IdentitySort(str, Enum):
    name_ = "name"
    bytes_ = "bytes"


def _model_path(model_name: str, suffix: str = "") -> str:
    return f"{AICC_BASE}/inventory/models/{urllib.parse.quote(model_name, safe='')}{suffix}"


@models_app.command("list")
def list_models(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    provider: Optional[list[str]] = typer.Option(
        None,
        "--provider",
        help=(
            "Filter by model provider (repeatable), e.g. OpenAI, Anthropic. Discover values "
            "with 'ntsk aicc analytics breakdown models --dimension provider'."
        ),
    ),
    deployment: Optional[list[str]] = typer.Option(
        None, "--deployment", help="Filter by deployment/footprint type (repeatable), e.g. endpoint, cloud_web."
    ),
    first_seen_after: Optional[str] = typer.Option(None, "--first-seen-after", help=HELP_FIRST_SEEN_AFTER),
    active_only: bool = typer.Option(False, "--active-only", help=HELP_ACTIVE_ONLY),
    sort_by: Optional[str] = typer.Option(None, "--sort-by", help="Server-side sort field. Valid: bytes, identities."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List AI models observed in your environment.

    Queries GET /api/v2/aicc/inventory/models. Each row includes name,
    provider, footprint (endpoint = locally-run), bytes, identities,
    first_seen, and last_seen.

    Examples:
        ntsk aicc models list
        ntsk aicc models list --deployment endpoint             # locally-run models
        ntsk aicc models list --provider OpenAI --start 30d --all -o json
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso}
    add_filters(
        params,
        search=search,
        provider=provider,
        deployment=deployment,
        active_only=active_only,
        sort=build_sort(sort_by, sort_dir.value),
    )
    if first_seen_after:
        params["first_seen_after"] = resolve_single_time(ctx, first_seen_after)

    run_list(
        ctx,
        f"{AICC_BASE}/inventory/models",
        params,
        title="AICC — Models",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        default_fields=["name", "provider", "bytes", "identities", "first_seen", "last_seen"],
        empty_hint="No models found in this window. Try a longer --start (e.g. 30d, 90d).",
    )


@models_app.command("get")
def get_model(
    ctx: typer.Context,
    model_name: str = typer.Argument(
        ...,
        help=(
            "Exact model name as returned by 'aicc models list' (the 'name' field), "
            "e.g. 'gpt-oss:latest' or 'qwen3:1.7b'."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
) -> None:
    """Show full details for one model.

    Queries GET /api/v2/aicc/inventory/models/{model_name}.

    Examples:
        ntsk aicc models get "qwen3:1.7b"
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _model_path(model_name),
        {"start_time": start_iso, "end_time": end_iso},
        spinner_text=f"Fetching {model_name}...",
    )
    show_payload(ctx, unwrap_data(response), title=f"AICC Model — {model_name}")


@models_app.command("identities")
def model_identities(
    ctx: typer.Context,
    model_name: str = typer.Argument(..., help="Exact model name, e.g. 'qwen3:1.7b'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    sort_by: _IdentitySort = typer.Option(_IdentitySort.bytes_, "--sort-by", help="Sort field: name or bytes."),
    sort_dir: _SortDir = typer.Option(_SortDir.desc, "--sort-dir", help="Sort direction: asc or desc."),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List the identities that accessed a model.

    Queries GET /api/v2/aicc/inventory/models/{model_name}/identities.

    Examples:
        ntsk aicc models identities "qwen3:1.7b"
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {
        "start_time": start_iso,
        "end_time": end_iso,
        "sort_by": sort_by.value,
        "sort_dir": sort_dir.value,
    }
    add_filters(params, search=search)
    run_list(
        ctx,
        _model_path(model_name, "/identities"),
        params,
        title=f"AICC Model Identities — {model_name}",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
    )


@models_app.command("deployments")
def model_deployments(
    ctx: typer.Context,
    model_name: str = typer.Argument(..., help="Exact model name, e.g. 'qwen3:1.7b'."),
    deployment_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=(
            "Deployment class to list — a footprint key from 'aicc models get' "
            "(footprint.types), e.g. endpoint. An unknown type returns an empty list."
        ),
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    search: Optional[str] = typer.Option(None, "--search", help=HELP_SEARCH),
    limit: int = typer.Option(50, "--limit", "-l", help=HELP_LIMIT),
    offset: int = typer.Option(0, "--offset", help=HELP_OFFSET),
    fetch_all: bool = typer.Option(False, "--all", help=HELP_ALL),
) -> None:
    """List deployment instances of a model (per footprint type).

    Queries GET /api/v2/aicc/inventory/models/{model_name}/deployments.
    First run 'aicc models get NAME' and check footprint.types for valid --type values.

    Examples:
        ntsk aicc models deployments "qwen3:1.7b" --type endpoint
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    params: dict = {"start_time": start_iso, "end_time": end_iso, "type": deployment_type}
    add_filters(params, search=search)
    run_list(
        ctx,
        _model_path(model_name, "/deployments"),
        params,
        title=f"AICC Model Deployments — {model_name} ({deployment_type})",
        limit=limit,
        offset=offset,
        fetch_all=fetch_all,
        empty_hint=(
            "No deployments of this type. Run 'ntsk aicc models get' and use one of the "
            "footprint.types values as --type."
        ),
    )


@models_app.command("trend")
def model_trend(
    ctx: typer.Context,
    model_name: str = typer.Argument(..., help="Exact model name, e.g. 'qwen3:1.7b'."),
    start: Optional[str] = typer.Option(None, "--start", "-s", "--since", help=HELP_START),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    tz: str = typer.Option("UTC", "--timezone", "-z", help=HELP_TIMEZONE),
) -> None:
    """Show the traffic trend for one model (bytes/sessions per bucket).

    Queries GET /api/v2/aicc/inventory/models/{model_name}/traffic-trend.

    Examples:
        ntsk aicc models trend "qwen3:1.7b" --start 30d
    """
    start_iso, end_iso = resolve_time_range(ctx, start, end)
    response = aicc_get(
        ctx,
        _model_path(model_name, "/traffic-trend"),
        {"start_time": start_iso, "end_time": end_iso, "timezone": tz},
        spinner_text=f"Fetching traffic trend for {model_name}...",
    )
    payload = unwrap_data(response)
    rows = payload.get("data") if isinstance(payload, dict) else None
    show_payload(
        ctx,
        rows if isinstance(rows, list) else payload,
        title=f"AICC Model Traffic Trend — {model_name}",
        empty_hint="No trend data in this window.",
    )
