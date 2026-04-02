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

# Command leaf names that indicate a mutating (write) operation.
# Used to tag commands in --flat output so AI agents can distinguish
# safe read-only commands from state-changing ones.
_WRITE_COMMAND_NAMES: frozenset[str] = frozenset(
    {
        "create",
        "update",
        "delete",
        "deploy",
        "revoke",
        "bulk-delete",
        "add",
        "replace",
        "remove",
        "assign",
        "upgrade",
        "connect",
        "scan",
        "scan-file",
        "scan-url",
        "url-recategorize",
        "false-positive",
        "config-update",
        "registration-token",
    }
)


def _has_yes_flag(cmd: click.Command) -> bool:
    """Return True if the command has a --yes / -y option."""
    return any(isinstance(p, click.Option) and "--yes" in (p.opts or []) for p in cmd.params)


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


def _walk_flat(group: click.Group, ctx: click.Context, prefix: str = "") -> list[tuple[str, str, str, str, bool]]:
    """Recursively collect leaf (executable) commands with their full path.

    Returns a list of (full_command, arg_signature, help_line, mode, has_yes) tuples.
    Only non-Group commands are included — groups are traversed but not emitted.
    ``mode`` is ``"write"`` for commands whose leaf name is in
    :data:`_WRITE_COMMAND_NAMES`, otherwise ``"read"``.
    """
    result: list[tuple[str, str, str, str, bool]] = []
    for name in sorted(group.list_commands(ctx)):
        cmd = group.get_command(ctx, name)
        if cmd is None or cmd.hidden:
            continue
        full_name = f"{prefix}{name}"
        if isinstance(cmd, click.Group):
            child_ctx = click.Context(cmd, parent=ctx, info_name=name)
            result.extend(_walk_flat(cmd, child_ctx, prefix=f"{full_name} "))
        else:
            arg_sig = _arg_signature(cmd)
            first_line = (cmd.help or "").strip().split("\n")[0]
            mode = "write" if name in _WRITE_COMMAND_NAMES else "read"
            has_yes = _has_yes_flag(cmd)
            result.append((full_name, arg_sig, first_line, mode, has_yes))
    return result


def tree_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output the command tree as machine-readable JSON for agent consumption.",
    ),
    flat: bool = typer.Option(
        False,
        "--flat",
        help="Print only leaf (executable) commands, one per line — ideal for scripting and AI agents.",
    ),
) -> None:
    """Print the full command tree for discoverability.

    Displays every command and subcommand registered in the CLI as an
    indented tree. Hidden aliases are omitted. Use this to discover
    available commands without reading docs.

    Use --json to output a machine-readable JSON tree with command names,
    arguments, options, and descriptions — ideal for AI agents that need
    to enumerate the full CLI surface in one call.

    Use --flat to print only leaf (executable) commands, one per line,
    with a short description. Combine with --json for a flat JSON array.

    Examples:
        netskope commands
        netskope commands --json
        netskope commands --flat
        netskope commands --flat --json
    """
    state = ctx.obj
    no_color = state.no_color if state is not None else False

    # Walk up to the root Click group
    root_ctx = ctx
    while root_ctx.parent is not None:
        root_ctx = root_ctx.parent
    root_group = root_ctx.command

    if flat:
        leaves = _walk_flat(root_group, root_ctx, prefix="ntsk ") if isinstance(root_group, click.Group) else []
        if json_output:
            data = []
            for cmd_path, arg_sig, help_line, mode, has_yes in leaves:
                entry: dict = {
                    "command": f"{cmd_path} {arg_sig}".strip() if arg_sig else cmd_path,
                    "help": help_line,
                    "mode": mode,
                }
                if has_yes:
                    entry["supports_yes_flag"] = True
                data.append(entry)
            print(json_mod.dumps(data, indent=2))
        else:
            # Calculate column widths for alignment
            lines = []
            for cmd_path, arg_sig, help_line, mode, _has_yes in leaves:
                display = f"{cmd_path} {arg_sig}".strip() if arg_sig else cmd_path
                tag = f"[{mode}]"
                lines.append((display, help_line, tag))
            if lines:
                max_cmd_len = max(len(cmd) for cmd, _, _ in lines)
                max_help_len = max(len(h) for _, h, _ in lines)
                cmd_pad = max_cmd_len + 4
                help_pad = max_help_len + 2
                for cmd, desc, tag in lines:
                    print(f"{cmd:<{cmd_pad}}{desc:<{help_pad}}{tag}")
        return

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
