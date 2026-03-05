"""Shared helpers for NPA command modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only)


def _get_output_format(ctx: typer.Context) -> str:
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


def _get_console(ctx: typer.Context) -> Console:
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def _load_json_file(path: str) -> dict[str, Any]:
    """Load and parse a JSON file, raising typer.BadParameter on failure."""
    p = Path(path)
    if not p.exists():
        raise typer.BadParameter(f"File not found: {path}")
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {path}: {exc}")


def _parse_comma_sep(value: str | None) -> list[str]:
    """Split a comma-separated string into a list, stripping whitespace."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_comma_sep_ints(value: str | None) -> list[int]:
    """Split a comma-separated string into a list of integers."""
    if not value:
        return []
    parts = _parse_comma_sep(value)
    try:
        return [int(v) for v in parts]
    except ValueError:
        raise typer.BadParameter(f"Expected comma-separated integers, got: {value}")


def _confirm_delete(resource: str, resource_id: object, yes: bool, ctx: typer.Context) -> None:
    """Prompt for confirmation on destructive operations unless --yes is set."""
    if not yes:
        confirm = typer.confirm(f"Are you sure you want to delete {resource} {resource_id}?")
        if not confirm:
            console = _get_console(ctx)
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()
