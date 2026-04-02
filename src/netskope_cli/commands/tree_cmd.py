"""Command-tree discovery command for the Netskope CLI.

Prints the full command tree so users can explore available commands
and subcommands without guessing.
"""

from __future__ import annotations

import json as json_mod

import click
import typer
from rich.console import Console
from rich.tree import Tree


def _arg_signature(cmd: click.Command) -> str:
    """Build a string like '<RESOURCE_TYPE>' from a command's positional args."""
    args = [p for p in cmd.params if isinstance(p, click.Argument)]
    if not args:
        return ""
    return " ".join(f"<{a.human_readable_name.upper()}>" for a in args)


def _walk(group: click.Group, tree: Tree, ctx: click.Context) -> None:
    """Recursively add Click group children to a Rich tree."""
    for name in sorted(group.list_commands(ctx)):
        cmd = group.get_command(ctx, name)
        if cmd is None:
            continue
        # Skip hidden commands (aliases)
        if cmd.hidden:
            continue
        first_line = (cmd.help or "").strip().split("\n")[0]
        arg_sig = _arg_signature(cmd) if not isinstance(cmd, click.Group) else ""
        label = f"[bold]{name}[/bold]"
        if arg_sig:
            label += f" [cyan]{arg_sig}[/cyan]"
        if first_line:
            label += f"  [dim]{first_line}[/dim]"
        if isinstance(cmd, click.Group):
            branch = tree.add(label)
            _walk(cmd, branch, click.Context(cmd, parent=ctx, info_name=name))
        else:
            tree.add(label)


def _walk_json(group: click.Group, ctx: click.Context) -> list[dict]:
    """Recursively build a JSON-serialisable command tree."""
    result: list[dict] = []
    for name in sorted(group.list_commands(ctx)):
        cmd = group.get_command(ctx, name)
        if cmd is None or cmd.hidden:
            continue
        first_line = (cmd.help or "").strip().split("\n")[0]
        entry: dict = {"name": name, "help": first_line}

        # Positional arguments
        args = [p for p in cmd.params if isinstance(p, click.Argument)]
        if args:
            entry["args"] = [{"name": a.human_readable_name, "required": a.required, "type": a.type.name} for a in args]

        # Options (excluding --help)
        opts = [p for p in cmd.params if isinstance(p, click.Option) and p.name != "help"]
        if opts:
            entry["options"] = [
                {
                    "name": o.opts[0] if o.opts else o.name,
                    "required": o.required,
                    "help": (o.help or "").split("\n")[0][:120],
                }
                for o in opts
            ]

        if isinstance(cmd, click.Group):
            child_ctx = click.Context(cmd, parent=ctx, info_name=name)
            children = _walk_json(cmd, child_ctx)
            if children:
                entry["subcommands"] = children

        result.append(entry)
    return result


def tree_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output the command tree as machine-readable JSON for agent consumption.",
    ),
) -> None:
    """Print the full command tree for discoverability.

    Displays every command and subcommand registered in the CLI as an
    indented tree. Hidden aliases are omitted. Use this to discover
    available commands without reading docs.

    Use --json to output a machine-readable JSON tree with command names,
    arguments, options, and descriptions — ideal for AI agents that need
    to enumerate the full CLI surface in one call.

    Examples:
        netskope commands
        netskope commands --json
    """
    state = ctx.obj
    no_color = state.no_color if state is not None else False

    # Walk up to the root Click group
    root_ctx = ctx
    while root_ctx.parent is not None:
        root_ctx = root_ctx.parent
    root_group = root_ctx.command

    if json_output:
        if isinstance(root_group, click.Group):
            data = _walk_json(root_group, root_ctx)
        else:
            data = []
        print(json_mod.dumps(data, indent=2))
        return

    console = Console(no_color=no_color, stderr=True)
    tree = Tree("[bold cyan]netskope[/bold cyan]")
    if isinstance(root_group, click.Group):
        _walk(root_group, tree, root_ctx)

    console.print(tree)
