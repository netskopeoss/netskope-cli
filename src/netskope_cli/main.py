"""Netskope CLI — manage your Netskope tenant from the command line.

This is the main entry point. It creates the top-level Typer application,
registers all command-group sub-apps, and wires up global options and error
handling.
"""

from __future__ import annotations

import difflib
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import click.exceptions
import typer
from rich.console import Console

from netskope_cli.core.exceptions import NetskopeError

# ---------------------------------------------------------------------------
# Version — single source of truth
# ---------------------------------------------------------------------------
__version__ = "0.2.10"

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
    no_color: bool = False
    raw: bool = False
    epoch: bool = False
    count: bool = False

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
        "  netskope config set-tenant mytenant.goskope.com\n"
        "  netskope config set-token\n"
        "  netskope alerts list --limit 10\n\n"
        "[bold]Output formats:[/bold]  --output json | table | csv | yaml | jsonl\n\n"
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
            "and CI/CD pipelines. Defaults to False."
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
            "Print only the total record count instead of full results. "
            "Works with any command that returns a list of records. "
            "Saves bandwidth by skipping full record retrieval when you only need the count."
        ),
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
    state = State(
        profile=profile,
        output=output,
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        raw=raw,
        epoch=epoch,
        count=count,
    )
    ctx.obj = state

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


# ---------------------------------------------------------------------------
# First-run setup hint
# ---------------------------------------------------------------------------

# Commands that do NOT require auth — suppress the setup banner for these.
_SETUP_COMMANDS = {"config", "auth", "doctor", "tenant", "docs", "commands", "help", "--help", "--version"}


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
        args = ctx.protected_params.get("args") or sys.argv[1:]
        for arg in args if isinstance(args, list) else [args]:
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

    # 7. API connectivity test
    if has_tenant and (token or session):
        client = NetskopeClient(base_url=base_url, api_token=token, ci_session=session)
        now = int(time.time())
        try:
            client.request(
                "GET",
                "/api/v2/events/data/audit",
                params={"starttime": now - 3600, "endtime": now, "limit": 1},
            )
            console.print("  [green]\u2713[/green] API connectivity: [green]OK[/green]")
        except Exception as exc:
            msg = str(exc).split("\n")[0]
            console.print(f"  [red]\u2717[/red] API connectivity: [red]FAILED[/red] — {msg}")
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
    from netskope_cli.core.output import OutputFormatter

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

    formatter = OutputFormatter()
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

# Config & Auth — always available
from netskope_cli.commands.auth_cmd import auth_app  # noqa: E402
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
        "Digital Experience Management — application probes, network probes, and alert rules.",
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
_error_displayed = False


def _hoist_global_options(argv: list[str]) -> list[str]:
    """Move --output/-o (and other global flags) to before the subcommand.

    Users naturally write ``netskope alerts list -o json`` but Typer/Click
    requires global options before the subcommand name.  This function
    rewrites *argv* so the option appears in the global position, making
    both orderings work transparently.
    """
    if len(argv) < 2:
        return argv

    # Flags that take a value and should be hoisted to the global position.
    _VALUE_FLAGS = {"--output", "-o", "--profile"}
    # Boolean flags that should be hoisted.
    _BOOL_FLAGS = {"--quiet", "-q", "--no-color", "--verbose", "-v", "--raw", "--epoch", "--count"}

    result = [argv[0]]
    hoisted: list[str] = []
    rest: list[str] = []

    i = 1
    while i < len(argv):
        arg = argv[i]

        # Handle --output=json style
        if any(arg.startswith(f"{f}=") for f in _VALUE_FLAGS):
            hoisted.append(arg)
            i += 1
            continue

        if arg in _VALUE_FLAGS:
            hoisted.append(arg)
            if i + 1 < len(argv):
                hoisted.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue

        if arg in _BOOL_FLAGS:
            hoisted.append(arg)
            i += 1
            continue

        rest.append(arg)
        i += 1

    return result + hoisted + rest


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
    except click.exceptions.Exit as e:
        raise SystemExit(e.exit_code)
    except click.exceptions.Abort:
        raise SystemExit(130)
    except click.exceptions.UsageError as exc:
        # Must be caught BEFORE NetskopeError / generic Exception so that
        # Click-generated usage errors (e.g. "No such option") are shown
        # exactly once and never double-printed.
        msg = exc.format_message()
        # When no subcommand is given, Typer/Click raises a UsageError with
        # "Missing command".  Treat this like --help: show help and exit 0.
        if not msg or "Missing command" in msg or "missing command" in msg.lower():
            # Help was already displayed by no_args_is_help or we triggered it.
            # Exit cleanly with code 0 — showing help is not an error.
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

        if not redirected:
            # With standalone_mode=False, print the error ourselves (once).
            console.print(f"[bold red]Error:[/bold red] {msg}")

        # Issue 10: suggest close matches for unknown subcommands
        if not redirected and ("No such command" in msg or "Error" in msg):
            _known_commands = [
                "config",
                "auth",
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
