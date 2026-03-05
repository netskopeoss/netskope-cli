"""Command-tree discovery command for the Netskope CLI.

Prints the full command tree so users can explore available commands
and subcommands without guessing.
"""

from __future__ import annotations

import click
import typer
from rich.console import Console
from rich.tree import Tree


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
        label = f"[bold]{name}[/bold]"
        if first_line:
            label += f"  [dim]{first_line}[/dim]"
        if isinstance(cmd, click.Group):
            branch = tree.add(label)
            _walk(cmd, branch, click.Context(cmd, parent=ctx, info_name=name))
        else:
            tree.add(label)


def tree_command(ctx: typer.Context) -> None:
    """Print the full command tree for discoverability.

    Displays every command and subcommand registered in the CLI as an
    indented tree. Hidden aliases are omitted. Use this to discover
    available commands without reading docs.

    Examples:
        netskope commands
    """
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    console = Console(no_color=no_color, stderr=True)

    # Walk up to the root Click group
    root_ctx = ctx
    while root_ctx.parent is not None:
        root_ctx = root_ctx.parent
    root_group = root_ctx.command

    tree = Tree("[bold cyan]netskope[/bold cyan]")
    if isinstance(root_group, click.Group):
        _walk(root_group, tree, root_ctx)

    console.print(tree)
