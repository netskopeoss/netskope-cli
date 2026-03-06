"""Shell completion — install or show completion scripts for bash, zsh, fish, and PowerShell."""

from __future__ import annotations

import os
import sys
from enum import Enum
from typing import Optional

import typer

completion_app = typer.Typer(
    name="completion",
    help="Install or display shell completion scripts.",
    no_args_is_help=True,
    add_completion=False,
)


class Shell(str, Enum):
    bash = "bash"
    zsh = "zsh"
    fish = "fish"
    powershell = "powershell"
    pwsh = "pwsh"


def _detect_shell() -> str | None:
    """Auto-detect the current shell from the SHELL environment variable."""
    shell_env = os.environ.get("SHELL", "")
    if not shell_env:
        return None
    name = os.path.basename(shell_env)
    valid = {s.value for s in Shell}
    return name if name in valid else None


def _resolve_shell(shell: Shell | None) -> str:
    """Resolve shell from explicit argument or auto-detection."""
    if shell is not None:
        return shell.value
    detected = _detect_shell()
    if detected is None:
        typer.echo(
            "Could not detect your shell. Please specify one explicitly:\n"
            "  netskope completion install bash\n"
            "  netskope completion show zsh\n\n"
            f"Supported shells: {', '.join(s.value for s in Shell)}",
            err=True,
        )
        raise typer.Exit(1)
    return detected


@completion_app.command()
def show(
    shell: Optional[Shell] = typer.Argument(
        None,
        help="Shell to generate completion for. Auto-detected from $SHELL if omitted.",
    ),
) -> None:
    """Print the completion script to stdout.

    Copy the output to the appropriate file, or pipe it:

        netskope completion show zsh > ~/.zfunc/_netskope
        netskope completion show bash >> ~/.bashrc
    """
    from typer._completion_shared import get_completion_script

    resolved = _resolve_shell(shell)
    prog_name = _get_prog_name()
    complete_var = "_{}_COMPLETE".format(prog_name.replace("-", "_").upper())
    script = get_completion_script(prog_name=prog_name, complete_var=complete_var, shell=resolved)
    typer.echo(script)


@completion_app.command()
def install(
    shell: Optional[Shell] = typer.Argument(
        None,
        help="Shell to install completion for. Auto-detected from $SHELL if omitted.",
    ),
) -> None:
    """Install completion for the specified shell.

    Writes the completion script to the standard location for your shell
    and (for bash) sources it from your shell RC file.

        netskope completion install zsh
        netskope completion install bash
    """
    from typer._completion_shared import install as typer_install

    resolved = _resolve_shell(shell)
    prog_name = _get_prog_name()
    complete_var = "_{}_COMPLETE".format(prog_name.replace("-", "_").upper())
    installed_shell, path = typer_install(shell=resolved, prog_name=prog_name, complete_var=complete_var)
    typer.echo(f"{installed_shell} completion installed in {path}")
    typer.echo("Completion will take effect once you restart the terminal.")


def _get_prog_name() -> str:
    """Return the CLI program name (netskope or ntsk)."""
    prog = os.path.basename(sys.argv[0]) if sys.argv else "netskope"
    # Strip common wrappers
    if prog in ("python", "python3", "__main__.py"):
        return "netskope"
    return prog
