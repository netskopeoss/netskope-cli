"""Netskope CLI — manage your Netskope tenant from the command line.

This is the main entry point. It creates the top-level Typer application,
registers all command-group sub-apps, and wires up global options and error
handling.
"""

from __future__ import annotations

import difflib
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from typer._completion_classes import completion_init
from typer.core import TyperCommand, TyperGroup, TyperOption

from netskope_cli.core.exceptions import NetskopeError
from netskope_cli.core.filtering import parse_filter, parse_sort_spec

# ---------------------------------------------------------------------------
# Version — single source of truth
# ---------------------------------------------------------------------------
__version__ = "1.4.8"

# ---------------------------------------------------------------------------
# Global state object threaded through the context
# ---------------------------------------------------------------------------


class OutputFormat(str, Enum):
    json = "json"
    table = "table"
    csv = "csv"
    yaml = "yaml"
    jsonl = "jsonl"


@dataclass
class State:
    """Mutable bag of global options accessible in every subcommand."""

    profile: str | None = None
    output: OutputFormat = OutputFormat.table
    verbose: int = 0
    quiet: bool = False
    # ``--quiet`` exactly as typed.  ``quiet`` above is also switched on when
    # stdout is not a TTY; a stderr notice that must reach a pipeline (the
    # --fields transition note) checks this one instead.
    quiet_explicit: bool = False
    no_color: bool = False
    raw: bool = False
    epoch: bool = False
    count: bool = False
    # ``--exact``: with ``--count`` on datasearch commands, page for the true total.
    exact: bool = False
    wide: bool = False
    # Global query options (see ``ntsk docs fields``).  ``where_expr`` and
    # ``sort_spec`` are the parsed forms of ``where`` / ``sort``.
    fields: list[str] | None = None
    list_fields: bool = False
    where: str | None = None
    where_expr: Any = None
    sort: str | None = None
    sort_spec: list[tuple[str, bool]] | None = None

    # Lazily initialised console respects --no-color
    _console: Console | None = field(default=None, repr=False)

    @property
    def console(self) -> Console:
        if self._console is None:
            self._console = Console(
                no_color=self.no_color,
                stderr=True,
            )
        return self._console


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="netskope",
    add_completion=False,
    help=(
        "Netskope CLI — manage your Netskope tenant from the command line.\n\n"
        "Tip: 'ntsk' is a shorthand alias for 'netskope'.\n\n"
        "A unified command-line interface for the Netskope Security Cloud platform. "
        "Use this tool to query security events, manage alerts and incidents, "
        "configure policies, provision users and groups via SCIM, inspect DSPM "
        "posture, manage publishers and steering, and administer CCI services -- "
        "all from your terminal or CI/CD pipeline.\n\n"
        "[bold]Command groups:[/bold]\n\n"
        "  [cyan]config[/cyan]       Manage CLI configuration profiles, tenants, and API tokens.\n"
        "  [cyan]auth[/cyan]         Authenticate via browser login, check status, or manage tokens.\n"
        "  [cyan]events[/cyan]       Query security events (alerts, application, network, page, audit, etc.).\n"
        "  [cyan]alerts[/cyan]       List and filter security alerts from the events datasearch API.\n"
        "  [cyan]incidents[/cyan]    View incidents, update status, retrieve DLP forensics.\n"
        "  [cyan]policy[/cyan]       Manage URL lists and deploy policy changes.\n"
        "  [cyan]services[/cyan]     Look up CCI scores, manage tags, publishers, and private apps.\n"
        "  [cyan]users[/cyan]        Provision and manage SCIM users and groups.\n"
        "  [cyan]dspm[/cyan]         Query DSPM resources, connect datastores, trigger scans.\n"
        "  [cyan]steering[/cyan]     Manage private-app steering and global steering configuration.\n"
        "  [cyan]publishers[/cyan]   Manage private-access publishers, upgrade profiles, and local brokers.\n\n"
        "[bold]Getting started:[/bold]\n\n"
        "  netskope config setup                          # one-step wizard\n"
        "  netskope alerts list --limit 10\n\n"
        "[bold]Quick start for scripting / AI agents:[/bold]\n\n"
        "  ntsk commands --flat --json                    # all commands with read/write tags (start here)\n"
        "  ntsk commands --flat                           # human-readable command list with \\[read]/\\[write] tags\n"
        "  ntsk status --extended -o json                 # full tenant health overview\n"
        "  ntsk alerts list --limit 100 -o json           # recent alerts\n"
        "  ntsk events application --limit 50 -o json     # app events\n"
        "  ntsk publishers list -o json                   # all publishers\n"
        "  ntsk services private-apps list -o json        # all private apps\n"
        "  ntsk users list --limit 50 -o json             # SCIM users\n\n"
        "[bold]Query any command (client-side, works everywhere):[/bold]\n\n"
        "  ntsk devices list --list-fields                # discover every field, nested paths included\n"
        "  ntsk devices list --fields hostname,host_info.os,epdlp.*   # pick columns, in this order\n"
        "  ntsk devices list --where 'host_info.os like \"win*\" and epdlp.criticalErrorsCount gt 0'\n"
        "  ntsk devices list --sort last_event_timestamp:desc --count\n"
        "  ntsk docs fields                               # full reference for --fields/--where/--sort\n\n"
        "[bold]Output formats:[/bold]  --output json | table | csv | yaml | jsonl\n\n"
        "[bold]Write command safety:[/bold]\n\n"
        "  Commands tagged \\[write] in 'ntsk commands --flat' modify tenant state.\n"
        "  All write commands prompt for confirmation before executing.\n"
        "  Pass --yes / -y to skip the prompt (required for scripts / CI / agents).\n"
        "  Omit --yes to see what will happen without committing the change.\n\n"
        "[bold]Environment variables:[/bold]\n\n"
        "  NETSKOPE_TENANT     Tenant hostname (overrides profile config).\n"
        "  NETSKOPE_API_TOKEN  API token (overrides keyring and profile config).\n"
        "  NETSKOPE_PROFILE    Active configuration profile name.\n"
        "  NO_COLOR            Disable coloured output when set to any value.\n"
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,  # We handle our own errors
)

# Register Typer's custom shell completion classes so that zsh/bash/fish
# completion works even though add_completion=False disables the built-in
# --install-completion flag (which would normally trigger this registration).
completion_init()


def _stdout_is_tty() -> bool:
    """Whether stdout is interactive (separate function so tests can override it)."""
    return sys.stdout.isatty()


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------
def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"netskope-cli {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Main callback — processes global flags and stores them in ctx.obj
# ---------------------------------------------------------------------------
@app.callback()
def main(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help=(
            "Configuration profile to use. Profiles allow you to maintain separate "
            "credentials and tenant settings for different environments (e.g. production, "
            "staging). Defaults to 'default'. Can also be set via NETSKOPE_PROFILE env var."
        ),
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table,
        "--output",
        "-o",
        help=(
            "Output format for command results. Valid values: json, table, csv, yaml, jsonl. "
            "Use 'json' for programmatic consumption and AI agent pipelines. Use 'table' "
            "(the default) for human-readable terminal output. Use 'jsonl' for streaming "
            "large result sets one record per line."
        ),
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help=(
            "Increase verbosity of output. Repeat for more detail: -v for info-level "
            "messages, -vv for debug-level messages including API request details. "
            "Defaults to 0 (warnings and errors only)."
        ),
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help=(
            "Suppress non-essential output such as spinners, progress indicators, and "
            "informational messages. Only data and errors are printed. Useful for scripting "
            "and CI/CD pipelines. Automatically enabled when stdout is not a TTY (piped output)."
        ),
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help=(
            "Disable coloured and styled terminal output. Automatically enabled when the "
            "NO_COLOR environment variable is set to any value. Use this in CI/CD "
            "environments or when piping output to files. Defaults to False."
        ),
        envvar="NO_COLOR",
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help=(
            "Include internal platform fields (prefixed with '_') in output. "
            "By default these are stripped for cleaner output. Use --raw when "
            "you need the full unfiltered API response."
        ),
    ),
    epoch: bool = typer.Option(
        False,
        "--epoch",
        help=(
            "Keep timestamps as raw Unix epoch integers. By default, machine-readable "
            "formats (JSON, JSONL, CSV, YAML) add ISO 8601 companion fields. "
            "Use --epoch to suppress this and output only raw epoch values."
        ),
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help=(
            "Print only the record count instead of full results. Endpoints that return a total "
            "report that total. Events, alerts and incidents commands fetch up to 10,000 rows (the API "
            "page cap) and print N+ when that cap is hit (json/jsonl/csv/yaml and piped output print the bare "
            "integer, a lower bound); add --exact to page for the true total. Elsewhere the count is of the rows "
            "--limit fetched."
        ),
    ),
    exact: bool = typer.Option(
        False,
        "--exact",
        help=(
            "With --count on events, alerts and incidents commands: page through the API in 10,000-row "
            "steps until the result set ends instead of stopping at the first page (requires --start so every "
            "page is counted against one fixed window). Prints N+ if the "
            "NETSKOPE_COUNT_CEILING (default 200,000 rows) is reached first. Can issue many requests. "
            "Datasearch endpoints only (events audit, infrastructure and transaction count one page); no effect "
            "on other commands."
        ),
    ),
    wide: bool = typer.Option(
        False,
        "--wide",
        "-W",
        help=(
            "Show all table columns without truncation. By default, table output "
            "auto-selects the most informative columns and truncates long values. "
            "Use --wide to see every column at full width. Also settable via "
            "NETSKOPE_WIDE=1 environment variable."
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=(
            "Comma-separated fields to output, in the order given. Works on every command and never changes "
            "the API request. Dotted paths reach nested values (host_info.os), a[].b maps over lists, and * "
            "globs expand (epdlp.*). Example: --fields hostname,host_info.os,last_event_timestamp. Discover "
            "names with --list-fields; a name no record has warns and renders blank/null. "
            "Events, alerts, incidents and npa publishers/policy commands also take --api-fields for a "
            "server-side projection; see 'ntsk docs fields'."
        ),
        rich_help_panel="Query options (client-side, any command)",
    ),
    list_fields: bool = typer.Option(
        False,
        "--list-fields",
        help=(
            "Run the command, then list every field in the response (nested paths included) with its type, "
            "how many records carry it, and a sample value, instead of printing the records. "
            "Example: ntsk devices list --list-fields. Add -o json for a machine-readable schema."
        ),
        rich_help_panel="Query options (client-side, any command)",
    ),
    where: Optional[str] = typer.Option(
        None,
        "--where",
        help=(
            "Client-side row filter in JQL syntax, applied after the API returns (so it works on every "
            "command, but only sees the rows --limit fetched). Operators: eq ne gt ge lt le in like between, "
            "and / or / not, parentheses, dotted paths, case-insensitive strings. "
            "Example: --where 'status eq connected and host_info.os like \"win*\"'. "
            "Syntax errors are reported before any API call. See 'ntsk docs fields'."
        ),
        rich_help_panel="Query options (client-side, any command)",
    ),
    sort: Optional[str] = typer.Option(
        None,
        "--sort",
        help=(
            "Client-side sort: FIELD or FIELD:desc, comma-separated for several keys. Dotted paths allowed. "
            "Example: --sort host_info.os,last_event_timestamp:desc. Missing values sort last."
        ),
        rich_help_panel="Query options (client-side, any command)",
    ),
    _version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the CLI version number and exit.",
    ),
) -> None:
    """Global options applied to every subcommand."""
    # Auto-enable quiet mode when stdout is not a TTY (piped output), but
    # keep the flag as typed: some stderr notices honour only an explicit -q.
    quiet_explicit = quiet
    if not quiet and not _stdout_is_tty():
        quiet = True

    # Parse the query options up front so a typo fails fast (exit 2) before
    # any API call is made.
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    where_expr = parse_filter(where) if where else None
    sort_spec = parse_sort_spec(sort) if sort else None

    state = State(
        profile=profile,
        output=output,
        verbose=verbose,
        quiet=quiet,
        quiet_explicit=quiet_explicit,
        no_color=no_color,
        raw=raw,
        epoch=epoch,
        count=count,
        exact=exact,
        wide=wide,
        fields=field_list,
        list_fields=list_fields,
        where=where,
        where_expr=where_expr,
        sort=sort,
        sort_spec=sort_spec,
    )
    ctx.obj = state

    # --where is client-side; on commands with a server-side --query, say so once.
    if where and not quiet:
        leaf = _resolve_leaf_command(sys.argv)
        if leaf is not None and "--query" in _local_option_names(leaf):
            state.console.print(
                "[dim]--where filters client-side after the API returned the rows --limit fetched; "
                "use --query for server-side JQL on this command.[/dim]"
            )

    # --- Configure logging based on verbosity ---
    if verbose >= 2:
        log_level = logging.DEBUG
    elif verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # Suppress noisy third-party loggers unless at max verbosity
    if verbose < 2:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    # --- First-run welcome banner ---
    # Show a helpful getting-started message when the user has no config and
    # is trying to run a data command (not config/auth/help/doctor).
    if not quiet:
        _maybe_show_setup_hint(ctx, profile)
        _maybe_show_update_notice(ctx)


# ---------------------------------------------------------------------------
# Update notice
# ---------------------------------------------------------------------------


def _maybe_show_update_notice(ctx: typer.Context) -> None:
    """Show a one-liner upgrade notice when a newer CLI version exists."""
    subcommand = ctx.invoked_subcommand
    if subcommand is None:
        for arg in sys.argv[1:]:
            if not arg.startswith("-"):
                subcommand = arg
                break
    if subcommand in _SETUP_COMMANDS:
        return
    try:
        from netskope_cli.core.version_check import maybe_show_update_notice

        state: State = ctx.obj
        maybe_show_update_notice(state.console, __version__, quiet=state.quiet)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# First-run setup hint
# ---------------------------------------------------------------------------

# Commands that do NOT require auth — suppress the setup banner for these.
_SETUP_COMMANDS = {
    "config",
    "auth",
    "completion",
    "doctor",
    "tenant",
    "docs",
    "commands",
    "help",
    "--help",
    "--version",
}


def _maybe_show_setup_hint(ctx: typer.Context, cli_profile: str | None) -> None:
    """Show a getting-started banner when credentials are missing.

    Only triggers when the invoked subcommand actually needs auth (i.e. not
    config, auth, doctor, or docs).
    """
    # Determine the subcommand being invoked.
    # Prefer Click's context (works correctly under CliRunner in tests);
    # fall back to sys.argv for edge cases where the context hasn't resolved yet.
    subcommand = ctx.invoked_subcommand
    if subcommand is None:
        args = ctx.args or sys.argv[1:]
        for arg in args:
            if isinstance(arg, str) and not arg.startswith("-"):
                subcommand = arg
                break

    if subcommand is None or subcommand in _SETUP_COMMANDS:
        return

    # Check whether credentials are available.
    from netskope_cli.core.config import get_active_profile, get_api_token, get_session_cookie, load_config

    try:
        cfg = load_config()
    except Exception:
        cfg = None

    from netskope_cli.core.exceptions import ConfigError

    if cfg is None:
        # No config at all — definitely first run.
        _print_welcome_banner()
        raise ConfigError(
            "No configuration found.",
            suggestion="Run `netskope config set-tenant HOSTNAME` then `netskope config set-token` to get started.",
        )

    active = get_active_profile(cfg, cli_profile=cli_profile)
    token = get_api_token(profile=active, cfg=cfg)
    session = get_session_cookie(profile=active, cfg=cfg)

    if not token and not session:
        # Config exists but no credentials.
        console = Console(stderr=True)
        from netskope_cli.core.config import get_tenant_url

        has_tenant = True
        try:
            get_tenant_url(profile=active, cfg=cfg)
        except (ValueError, Exception):
            has_tenant = False

        if not has_tenant:
            _print_welcome_banner()
            raise ConfigError(
                "No tenant or credentials configured.",
                suggestion="Run `netskope config set-tenant HOSTNAME` then `netskope config set-token` to get started.",
            )
        else:
            console.print()
            console.print(
                "[bold yellow]No credentials configured[/bold yellow] " f"for profile [bold]'{active}'[/bold]."
            )
            console.print()
            console.print("  Set up authentication (choose one):")
            console.print("    [cyan]netskope config set-token[/cyan]          # interactive prompt")
            console.print("    [cyan]netskope config set-token TOKEN[/cyan]    # pass directly")
            console.print("    [cyan]netskope auth login[/cyan]                # browser-based SSO")
            console.print('    [cyan]export NETSKOPE_API_TOKEN="..."[/cyan]    # env variable')
            console.print()
            console.print(
                "  [dim]Get a token from: Settings > Tools > REST API v2 in your" " Netskope admin console.[/dim]"
            )
            console.print()
            raise ConfigError(
                f"No credentials configured for profile '{active}'.",
                suggestion="Run `netskope config set-token` to configure authentication.",
            )


def _print_welcome_banner() -> None:
    """Print the first-run welcome message with full setup instructions."""
    console = Console(stderr=True)
    console.print()
    console.print("[bold]Welcome to the Netskope CLI![/bold] Let's get you set up.")
    console.print()
    console.print("  [bold]Step 1:[/bold] Set your tenant")
    console.print("    [cyan]netskope config set-tenant mytenant.goskope.com[/cyan]")
    console.print()
    console.print("  [bold]Step 2:[/bold] Set your API token (choose one)")
    console.print("    [cyan]netskope config set-token[/cyan]          # interactive prompt")
    console.print("    [cyan]netskope config set-token TOKEN[/cyan]    # pass directly")
    console.print("    [cyan]netskope auth login[/cyan]                # browser-based SSO")
    console.print('    [cyan]export NETSKOPE_API_TOKEN="..."[/cyan]    # env variable')
    console.print()
    console.print("  [bold]Then try:[/bold]")
    console.print("    [cyan]netskope alerts list --limit 5[/cyan]")
    console.print()
    console.print("  [dim]Get a token from: Settings > Tools > REST API v2 in your" " Netskope admin console.[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# Doctor command — comprehensive setup diagnostic
# ---------------------------------------------------------------------------


def _doctor_cmd(ctx: typer.Context) -> None:
    """Run a comprehensive check of your Netskope CLI setup.

    Verifies configuration, credentials, and API connectivity in one shot.
    Shows a checklist with pass/fail status for each item.

    Examples:
        netskope doctor
        netskope doctor --profile production
    """
    import time

    from netskope_cli.core.client import NetskopeClient
    from netskope_cli.core.config import (
        config_file_path,
        get_active_profile,
        get_api_token,
        get_session_cookie,
        get_tenant_url,
        load_config,
    )

    state = ctx.obj or State()
    console = Console(stderr=True, no_color=state.no_color)
    profile_name = state.profile

    console.print()
    console.print("[bold]Netskope CLI Doctor[/bold]")
    console.print()

    all_ok = True

    # 1. Config file
    cfg_path = config_file_path()
    if cfg_path.exists():
        console.print(f"  [green]\u2713[/green] Config file exists: {cfg_path}")
    else:
        console.print(f"  [red]\u2717[/red] Config file not found: {cfg_path}")
        console.print("    [dim]Run: netskope config set-tenant HOSTNAME[/dim]")
        all_ok = False

    # 2. Load config
    try:
        cfg = load_config()
    except Exception as exc:
        console.print(f"  [red]\u2717[/red] Config file parse error: {exc}")
        all_ok = False
        console.print()
        return

    # 3. Profile
    active = get_active_profile(cfg, cli_profile=profile_name)
    console.print(f"  [green]\u2713[/green] Active profile: [bold]{active}[/bold]")

    # 4. Tenant
    has_tenant = False
    try:
        base_url = get_tenant_url(profile=active, cfg=cfg)
        console.print(f"  [green]\u2713[/green] Tenant configured: [bold]{base_url}[/bold]")
        has_tenant = True
    except (ValueError, Exception):
        console.print("  [red]\u2717[/red] Tenant: [red]not configured[/red]")
        console.print("    [dim]Run: netskope config set-tenant HOSTNAME[/dim]")
        all_ok = False

    # 5. Token
    import os

    env_token = os.environ.get("NETSKOPE_API_TOKEN")
    token = get_api_token(profile=active, cfg=cfg)
    session = get_session_cookie(profile=active, cfg=cfg)

    if token:
        source = "NETSKOPE_API_TOKEN env var" if (env_token and token == env_token) else "keyring/config"
        console.print(f"  [green]\u2713[/green] API token: [green]set[/green] (source: {source})")
    else:
        console.print("  [red]\u2717[/red] API token: [red]not set[/red]")
        console.print("    [dim]Run: netskope config set-token[/dim]")
        all_ok = False

    # 6. Session cookie
    if session:
        console.print("  [green]\u2713[/green] Session cookie: [green]set[/green]")
    else:
        console.print("  [dim]\u2022[/dim] Session cookie: [dim]not set[/dim] (optional)")

    # 7. CA bundle / SSL
    from netskope_cli.core.config import find_netskope_ca_cert, get_ca_bundle

    ca_bundle = get_ca_bundle(profile=active, cfg=cfg)
    ns_cert = find_netskope_ca_cert()
    if ca_bundle:
        console.print(f"  [green]\u2713[/green] CA bundle: {ca_bundle}")
    elif ns_cert:
        console.print(f"  [yellow]\u2022[/yellow] Netskope CA cert detected: {ns_cert}")
        console.print(f'    [dim]Tip: export NETSKOPE_CA_BUNDLE="{ns_cert}" to use it[/dim]')
    else:
        console.print("  [dim]\u2022[/dim] CA bundle: [dim]default (certifi)[/dim]")

    # 8. API connectivity test
    verify: bool | str = ca_bundle if ca_bundle else True
    if has_tenant and (token or session):
        client = NetskopeClient(base_url=base_url, api_token=token, ci_session=session, verify=verify)
        now = int(time.time())
        try:
            client.request(
                "GET",
                "/api/v2/events/data/audit",
                params={"starttime": now - 3600, "endtime": now, "limit": 1},
            )
            console.print("  [green]\u2713[/green] API connectivity: [green]OK[/green]")
        except Exception as exc:
            from netskope_cli.core.exceptions import SSLError as NetskopeSSLError

            msg = str(exc).split("\n")[0]
            console.print(f"  [red]\u2717[/red] API connectivity: [red]FAILED[/red] — {msg}")
            if isinstance(exc, NetskopeSSLError):
                console.print("    [yellow]This looks like an SSL inspection issue.[/yellow]")
                if ns_cert:
                    console.print(f'    [dim]Try: export NETSKOPE_CA_BUNDLE="{ns_cert}"[/dim]')
                else:
                    console.print("    [dim]Run with -vv for details, or see: netskope docs ssl[/dim]")
            all_ok = False
    elif has_tenant:
        console.print("  [yellow]\u2022[/yellow] API connectivity: [yellow]skipped[/yellow] (no credentials)")
    else:
        console.print("  [yellow]\u2022[/yellow] API connectivity: [yellow]skipped[/yellow] (no tenant)")

    console.print()
    if all_ok:
        console.print("  [bold green]All checks passed![/bold green] You're good to go.")
    else:
        console.print("  [bold yellow]Some checks failed.[/bold yellow] Fix the issues above and re-run.")
    console.print()


# ---------------------------------------------------------------------------
# Tenant info command — lightweight tenant metadata
# ---------------------------------------------------------------------------


def _tenant_cmd(ctx: typer.Context) -> None:
    """Show tenant configuration and basic metadata.

    Displays the configured tenant URL, active profile, authentication
    method, and verifies API connectivity. Useful as a quick check
    before running other commands or for including in reports.

    Examples:
        netskope tenant
        netskope tenant -o json
    """
    import os
    import time

    from netskope_cli.core.client import NetskopeClient
    from netskope_cli.core.config import (
        get_active_profile,
        get_api_token,
        get_session_cookie,
        get_tenant_url,
        load_config,
    )
    from netskope_cli.core.output import build_formatter

    state: State = ctx.obj or State()
    console = Console(stderr=True, no_color=state.no_color)

    # Load configuration
    try:
        cfg = load_config()
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] Cannot load config: {exc}")
        raise typer.Exit(code=1)

    profile_name = get_active_profile(cfg, cli_profile=state.profile)

    # Tenant URL
    tenant_url = None
    try:
        tenant_url = get_tenant_url(profile=profile_name, cfg=cfg)
    except (ValueError, Exception):
        pass

    # Auth method
    env_token = os.environ.get("NETSKOPE_API_TOKEN")
    token = get_api_token(profile=profile_name, cfg=cfg)
    session = get_session_cookie(profile=profile_name, cfg=cfg)

    if token:
        auth_method = "token (env)" if (env_token and token == env_token) else "token (keyring/config)"
    elif session:
        auth_method = "session (browser)"
    else:
        auth_method = "none"

    # API connectivity check
    api_status = "unknown"
    if tenant_url and (token or session):
        client = NetskopeClient(base_url=tenant_url, api_token=token, ci_session=session)
        now = int(time.time())
        try:
            client.request(
                "GET",
                "/api/v2/events/data/audit",
                params={"starttime": now - 3600, "endtime": now, "limit": 1},
            )
            api_status = "connected"
        except Exception:
            api_status = "error"
    elif not tenant_url:
        api_status = "no tenant configured"
    else:
        api_status = "no credentials"

    info = {
        "tenant": tenant_url or "not configured",
        "profile": profile_name,
        "auth_method": auth_method,
        "api_status": api_status,
    }

    formatter = build_formatter(ctx)
    formatter.format_output(
        info,
        fmt=state.output.value,
        title="Tenant Info",
        unwrap=False,
        strip_internal=False,
        add_iso_timestamps=False,
    )


# ---------------------------------------------------------------------------
# Register subcommand groups
# ---------------------------------------------------------------------------

# Config, Auth & Completion — always available
from netskope_cli.commands.auth_cmd import auth_app  # noqa: E402
from netskope_cli.commands.completion_cmd import completion_app  # noqa: E402
from netskope_cli.commands.config_cmd import config_app  # noqa: E402

app.add_typer(
    config_app,
    name="config",
    help="Manage CLI configuration profiles, tenant hostnames, and API token storage.",
    rich_help_panel="Configuration",
)
app.add_typer(
    auth_app,
    name="auth",
    help="Authenticate with Netskope via browser login, check auth status, and manage tokens.",
    rich_help_panel="Configuration",
)
app.add_typer(
    completion_app,
    name="completion",
    help="Install or display shell completion scripts (bash, zsh, fish, PowerShell).",
    rich_help_panel="Configuration",
)

# Doctor — top-level diagnostic command
app.command("doctor", help="Check your CLI setup: config, credentials, and API connectivity.")(_doctor_cmd)

# Tenant — lightweight tenant metadata
app.command("tenant", help="Show tenant configuration, auth method, and API connectivity status.")(_tenant_cmd)

# Commands — full command tree for discoverability
from netskope_cli.commands.tree_cmd import tree_command  # noqa: E402

app.command("commands", help="Print the full command tree for discoverability.")(tree_command)

# Remaining command groups — imported with guards so the CLI stays usable
# even when individual modules are not yet implemented.

_optional_groups: list[tuple[str, str, str, str]] = [
    (
        "netskope_cli.commands.aicc",
        "aicc_app",
        "AI Command Center — inventory AI apps, MCP servers, agents, models, and identities"
        " with risk scoring, analytics, and AI Risk Report data.",
        "Cloud Security",
    ),
    (
        "netskope_cli.commands.events_cmd",
        "events_app",
        "Query security events by type (alerts, application, network, page, incident, audit,"
        " infrastructure, client-status, epdlp, transaction).",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.alerts_cmd",
        "alerts_app",
        "List and filter security alerts from the Netskope events datasearch API, and view known alert types.",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.incidents_cmd",
        "incidents_app",
        "View user confidence index, update incident fields, retrieve DLP forensics, and search incident events.",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.policy_cmd",
        "policy_app",
        "Manage URL lists (create, list, get, update, delete) and deploy pending policy changes to your tenant.",
        "Policy & Access",
    ),
    (
        "netskope_cli.commands.services_cmd",
        "services_app",
        "Look up Cloud Confidence Index (CCI) scores, manage service tags, list publishers, and manage private apps.",
        "Cloud Security",
    ),
    (
        "netskope_cli.commands.users_cmd",
        "users_app",
        "Provision and manage SCIM v2 users and groups for identity-based security policies.",
        "Policy & Access",
    ),
    (
        "netskope_cli.commands.dspm_cmd",
        "dspm_app",
        "Query Data Security Posture Management resources, connect datastores, trigger scans, and retrieve analytics.",
        "Cloud Security",
    ),
    (
        "netskope_cli.commands.steering_cmd",
        "steering_app",
        "Manage private-app steering rules and view or update the global steering configuration.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.publishers_cmd",
        "publishers_app",
        "Manage private-access publishers, view upgrade profiles, and list local brokers.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.rbac_cmd",
        "rbac_app",
        "Role-Based Access Control — manage roles, permissions, and admin users.",
        "Policy & Access",
    ),
    (
        "netskope_cli.commands.tokens_cmd",
        "tokens_app",
        "API Token Management — create, inspect, update, and revoke API tokens.",
        "Policy & Access",
    ),
    (
        "netskope_cli.commands.devices_cmd",
        "devices_app",
        "Device Management — list managed devices, manage tags, and check supported OS versions.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.spm_cmd",
        "spm_app",
        "SaaS Security Posture Management — posture scores, inventory, rules, and recent changes.",
        "Cloud Security",
    ),
    (
        "netskope_cli.commands.notifications_cmd",
        "notifications_app",
        "Manage notification templates and delivery settings.",
        "Monitoring",
    ),
    (
        "netskope_cli.commands.rbi_cmd",
        "rbi_app",
        "Remote Browser Isolation — manage applications, browsers, categories, and templates.",
        "Cloud Security",
    ),
    (
        "netskope_cli.commands.enrollment_cmd",
        "enrollment_app",
        "Device enrollment — create, list, and delete enrollment token sets.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.docs_cmd",
        "docs_app",
        "Documentation and help — open docs, search, view API reference, and JQL syntax.",
        "Configuration",
    ),
    (
        "netskope_cli.commands.atp_cmd",
        "atp_app",
        "Advanced Threat Protection — submit files and URLs for malware scanning and retrieve reports.",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.ips_cmd",
        "ips_app",
        "Intrusion Prevention System — view IPS status, manage IP allowlists, and browse signatures.",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.nsiq_cmd",
        "nsiq_app",
        "Netskope Threat Intelligence — URL lookups, recategorization requests, and false positive reports.",
        "Security & Events",
    ),
    (
        "netskope_cli.commands.dem_cmd",
        "dem_app",
        "Digital Experience Management — metrics, entities, alerts, traceroutes, probes, and apps.",
        "Monitoring",
    ),
    # Status / Dashboard
    (
        "netskope_cli.commands.status_cmd",
        "status_app",
        "Quick tenant health overview: alerts, publishers, private apps, and recent events.",
        "Monitoring",
    ),
    # DNS & VPN
    (
        "netskope_cli.commands.dns_cmd",
        "dns_app",
        "DNS Security — profiles, domain categories, tunneling detection, and inheritance groups.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.ipsec_cmd",
        "ipsec_app",
        "IPsec VPN — manage tunnels, POPs, and site-to-cloud connectivity.",
        "Infrastructure",
    ),
    (
        "netskope_cli.commands.npa",
        "npa_app",
        "Netskope Private Access — private apps, publishers, NPA policy, tags, local brokers, and discovery.",
        "Infrastructure",
    ),
]

_NAME_OVERRIDES: dict[str, str] = {
    "nsiq_app": "intel",
}

for _module, _attr, _help, _panel in _optional_groups:
    try:
        import importlib

        _mod = importlib.import_module(_module)
        _sub_app = getattr(_mod, _attr)
        _name = _NAME_OVERRIDES.get(_attr, _attr.removesuffix("_app"))
        app.add_typer(_sub_app, name=_name, help=_help, rich_help_panel=_panel)
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass  # Module not yet implemented — skip silently


# ---------------------------------------------------------------------------
# Error handling wrapper
# ---------------------------------------------------------------------------
# typer exports Exit, Abort and BadParameter but not the UsageError their
# bad-usage errors derive from, and cli() needs it to add hints ("did you
# mean", ntsk docs fields). This is the one import from typer's private
# vendored click; tests/integration/test_cli_commands.py pins it.
from typer._click.exceptions import UsageError  # noqa: E402

_error_displayed = False

# Every command typer builds is one of these two classes.
_AnyCommand = TyperGroup | TyperCommand


# Global flags that take a value / are boolean, hoisted to the global position.
_GLOBAL_VALUE_FLAGS = frozenset({"--output", "-o", "--profile", "--fields", "-f", "--where", "--sort"})
_GLOBAL_BOOL_FLAGS = frozenset(
    {
        "--quiet",
        "-q",
        "--no-color",
        "--verbose",
        "-v",
        "--raw",
        "--epoch",
        "--count",
        "--exact",
        "--wide",
        "-W",
        "--list-fields",
    }
)


def _option_takes_value(cmd: _AnyCommand, flag: str) -> bool:
    for param in cmd.params:
        if isinstance(param, TyperOption) and flag in (*param.opts, *param.secondary_opts):
            return not (param.is_flag or param.count)
    return False


def _local_option_names(cmd: _AnyCommand | None) -> set[str]:
    """Every option spelling (``--fields``, ``-f`` ...) the command declares itself."""
    names: set[str] = set()
    if cmd is None:
        return names
    for param in cmd.params:
        if isinstance(param, TyperOption):
            names.update(param.opts)
            names.update(param.secondary_opts)
    return names


def _resolve_leaf_command(argv: list[str]) -> TyperCommand | None:
    """Walk the command tree to the leaf subcommand named in *argv*.

    Returns ``None`` when the leaf cannot be determined (unknown command,
    ``help``, a bare group, or any unexpected error), in which case callers
    fall back to the historical behaviour.
    """
    try:
        root = typer.main.get_command(app)
        if not isinstance(root, TyperGroup):
            return None
        current: _AnyCommand = root
        ctx = typer.Context(root, info_name=argv[0] if argv else "netskope")
        i = 1
        while i < len(argv):
            tok = argv[i]
            if tok == "--":
                break
            if tok.startswith("-"):
                if "=" in tok:
                    i += 1
                    continue
                takes_value = tok in _GLOBAL_VALUE_FLAGS or _option_takes_value(current, tok)
                i += 2 if takes_value else 1
                continue
            if not isinstance(current, TyperGroup):
                return current
            nxt = current.get_command(ctx, tok)
            if not isinstance(nxt, (TyperGroup, TyperCommand)):
                return None
            ctx = typer.Context(nxt, parent=ctx, info_name=tok)
            current = nxt
            if isinstance(nxt, TyperCommand):
                return nxt
            i += 1
        return None if isinstance(current, TyperGroup) else current
    except Exception:  # pragma: no cover - defensive: argv rewriting must never crash
        return None


def _hoist_global_options(argv: list[str]) -> list[str]:
    """Move global flags (``-o``, ``--fields`` ...) to before the subcommand.

    Users naturally write ``netskope alerts list -o json`` but Typer/Click
    requires global options before the subcommand name.  This function
    rewrites *argv* so the option appears in the global position, making
    both orderings work transparently.

    A flag is only hoisted when the leaf subcommand does **not** declare it
    itself, so ``dem ... --where`` keeps its JSON where-clause, ``atp
    scan-file -f`` keeps meaning ``--file`` and ``policy url-list list
    --count`` stays local.  Server-side projections use the distinct
    ``--api-fields`` name, so ``--fields``/``-f`` is always the global
    client-side option.  Combined short flags (``-Wq``) are not recognised.
    """
    if len(argv) < 2:
        return argv

    local = _local_option_names(_resolve_leaf_command(argv))
    value_flags = {f for f in _GLOBAL_VALUE_FLAGS if f not in local}
    bool_flags = {f for f in _GLOBAL_BOOL_FLAGS if f not in local}

    result = [argv[0]]
    hoisted: list[str] = []
    rest: list[str] = []

    i = 1
    while i < len(argv):
        arg = argv[i]

        # Handle --output=json style
        if any(arg.startswith(f"{f}=") for f in value_flags):
            hoisted.append(arg)
            i += 1
            continue

        if arg in value_flags:
            hoisted.append(arg)
            if i + 1 < len(argv):
                hoisted.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue

        if arg in bool_flags:
            hoisted.append(arg)
            i += 1
            continue

        rest.append(arg)
        i += 1

    return result + hoisted + rest


def _show_group_hint(group: TyperGroup, cmd_path: str) -> None:
    """Print available subcommands when a group is invoked without a subcommand."""
    ctx = typer.Context(group, info_name=cmd_path.rsplit(" ", 1)[-1])
    console = Console(stderr=True)
    console.print(f"\n[yellow]'{cmd_path}' is a command group. Available subcommands:[/yellow]\n")
    for name in sorted(group.list_commands(ctx)):
        cmd = group.get_command(ctx, name)
        if cmd is None or cmd.hidden:
            continue
        first_line = (cmd.help or "").strip().split("\n")[0]
        console.print(f"  [bold]{name:<24}[/bold] {first_line}")
    console.print(f"\n[dim]Run: {cmd_path} --help[/dim]\n")


def cli() -> None:
    """Entry point that wraps the Typer app with clean error handling.

    Catches NetskopeError and generic exceptions, prints a clean one-line
    error with a hint (no traceback), and exits with the appropriate code.
    """
    global _error_displayed
    _error_displayed = False
    sys.argv = _hoist_global_options(sys.argv)

    # Treat "help" as "--help" anywhere in the command line so that
    # e.g. `netskope help`, `netskope config help` work as expected.
    if "help" in sys.argv:
        idx = sys.argv.index("help")
        sys.argv[idx] = "--help"

    try:
        app(standalone_mode=False)
    except typer.Exit as e:
        raise SystemExit(e.exit_code)
    except typer.Abort:
        raise SystemExit(130)
    except UsageError as exc:
        # Must be caught BEFORE NetskopeError / generic Exception so that
        # Click-generated usage errors (e.g. "No such option") are shown
        # exactly once and never double-printed.
        msg = exc.format_message()
        # When no subcommand is given, Typer/Click raises a UsageError with
        # "Missing command".  Treat this like --help: show help and exit 0.
        if not msg or "Missing command" in msg or "missing command" in msg.lower():
            # Help was already displayed by no_args_is_help or we triggered it.
            # Show available subcommands as a hint before exiting.
            if exc.ctx and isinstance(exc.ctx.command, TyperGroup):
                _show_group_hint(exc.ctx.command, exc.ctx.command_path)
            raise SystemExit(0)
        console = Console(stderr=True)
        # Use the actual command name from sys.argv[0] (e.g. "ntsk" or "netskope")
        cmd_name = Path(sys.argv[0]).name if sys.argv else "netskope"
        # Check for auth-related terms the user tried as top-level commands.
        # For these, show a clean redirect without the confusing Click error.
        _AUTH_REDIRECTS: dict[str, str] = {
            "login": f"{cmd_name} auth login",
            "logout": f"{cmd_name} auth logout",
            "token": f"{cmd_name} auth token",
            "set-token": f"{cmd_name} config set-token",
            "set-tenant": f"{cmd_name} config set-tenant",
            "setup": f"{cmd_name} config set-tenant HOSTNAME && {cmd_name} config set-token",
        }
        redirected = False
        if "No such command" in msg:
            for arg in sys.argv[1:]:
                if arg.startswith("-"):
                    continue
                if arg in _AUTH_REDIRECTS:
                    console.print(f"[dim]Hint:[/dim] Did you mean: [cyan]{_AUTH_REDIRECTS[arg]}[/cyan]?")
                    redirected = True
                break

        # Unknown option: replace Click's guess with the closest global or
        # subcommand option (Click only knows the options of one command).
        option_hint: str | None = None
        if "No such option" in msg:
            bad = re.search(r"No such option:? '?(-{1,2}[\w-]+)", msg)
            if bad:
                candidates = set(_GLOBAL_VALUE_FLAGS | _GLOBAL_BOOL_FLAGS)
                candidates.update(_local_option_names(_resolve_leaf_command(sys.argv)))
                close = difflib.get_close_matches(bad.group(1), sorted(candidates), n=1, cutoff=0.6)
                if close:
                    msg = re.sub(r"\s*Did you mean '[^']*'\?", "", msg)
                    option_hint = f"Did you mean [cyan]{close[0]}[/cyan]?"
                    if close[0] in ("--fields", "--where", "--sort", "--list-fields", "--api-fields"):
                        option_hint += " See 'ntsk docs fields' for the query options."

        if not redirected:
            # With standalone_mode=False, print the error ourselves (once).
            console.print(f"[bold red]Error:[/bold red] {msg}")
        if option_hint:
            console.print(f"[dim]Hint:[/dim] {option_hint}")

        # Issue 10: suggest close matches for unknown subcommands
        if not redirected and ("No such command" in msg or "Error" in msg):
            _known_commands = [
                "config",
                "auth",
                "aicc",
                "events",
                "alerts",
                "incidents",
                "policy",
                "services",
                "users",
                "dspm",
                "steering",
                "publishers",
                "rbac",
                "tokens",
                "devices",
                "spm",
                "notifications",
                "rbi",
                "enrollment",
                "docs",
                "atp",
                "ips",
                "intel",
                "dem",
                "dns",
                "ipsec",
                "status",
                "doctor",
                "npa",
                "tenant",
                "commands",
                "completion",
            ]
            _known_set = set(_known_commands)
            for arg in sys.argv[1:]:
                if arg.startswith("-"):
                    continue
                if arg in _known_set:
                    console.print(f"[dim]Hint:[/dim] Try: {cmd_name} {arg} --help")
                    break
                matches = difflib.get_close_matches(arg, _known_commands, n=1, cutoff=0.6)
                if matches:
                    console.print(f"[dim]Hint:[/dim] Unknown command '{arg}'. Did you mean '{matches[0]}'?")
                    break
        raise SystemExit(2)
    except NetskopeError as exc:
        if not _error_displayed:
            _error_displayed = True
            console = Console(stderr=True)
            console.print(f"[bold red]Error:[/bold red] {exc.message}")
            if exc.suggestion:
                if "\n" in exc.suggestion:
                    # Multi-line suggestion — print with blank line above.
                    console.print()
                    console.print(exc.suggestion)
                else:
                    console.print(f"[dim]Hint:[/dim] {exc.suggestion}")
        raise SystemExit(exc.exit_code)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1)


# Allow `python -m netskope_cli.main`
if __name__ == "__main__":
    cli()
