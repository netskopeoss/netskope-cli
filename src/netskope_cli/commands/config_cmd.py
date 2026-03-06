"""Configuration commands for the Netskope CLI.

Manages profiles, tenant hostnames, and API token storage.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from netskope_cli.core.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CONFIG_DIR = Path.home() / ".config" / "netskope"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
config_app = typer.Typer(
    name="config",
    help=(
        "Manage CLI configuration profiles, tenant hostnames, and API tokens.\n\n"
        "Configuration is stored in ~/.config/netskope/config.toml. Profiles allow "
        "you to maintain separate credentials and settings for different Netskope "
        "tenants (e.g. production, staging). API tokens are stored securely in the "
        "system keyring. Use 'set-tenant' and 'set-token' to get started, or "
        "'create-profile' for multi-tenant setups."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    """Load the TOML configuration file, returning an empty dict if missing."""
    import toml

    if not _CONFIG_FILE.exists():
        return {}
    return toml.loads(_CONFIG_FILE.read_text())


def _save_config(cfg: dict) -> None:
    """Persist the configuration dict to the TOML file."""
    import toml

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(toml.dumps(cfg))


def _active_profile(cfg: dict) -> str:
    """Return the name of the currently active profile."""
    return cfg.get("active_profile", "default")


def _get_profile_section(cfg: dict, profile: str) -> dict:
    """Return the config dict for a given profile, creating it if needed."""
    profiles = cfg.setdefault("profiles", {})
    return profiles.setdefault(profile, {})


def _mask_token(token: str) -> str:
    """Return a masked representation of a token for display.

    Only reveals partial characters when the token is long enough that
    the revealed portion represents a small fraction of the total entropy.
    """
    if len(token) < 20:
        return "****"
    return token[:4] + "****" + token[-4:]


def _store_token(profile: str, token: str, console: Console | None = None) -> bool:
    """Store the API token, preferring the system keyring with config fallback.

    Returns True if stored in keyring, False if fell back to config file.
    """
    try:
        import keyring
        from keyring.errors import NoKeyringError

        keyring.set_password("netskope-cli", profile, token)
        return True
    except ImportError:
        pass
    except NoKeyringError:
        pass
    except Exception:
        pass

    # Fallback: store in config file (plaintext)
    if console:
        console.print(
            "[yellow]WARNING: No keyring backend available. "
            "Token will be stored in plaintext in the config file.\n"
            "Install a keyring backend for secure storage: "
            "pip install keyring keyrings.alt[/yellow]"
        )
    cfg = _load_config()
    section = _get_profile_section(cfg, profile)
    section["api_token"] = token
    _save_config(cfg)
    return False


def _get_token(profile: str) -> str | None:
    """Retrieve the API token from keyring, falling back to config file."""
    # Try keyring first
    try:
        import keyring

        token = keyring.get_password("netskope-cli", profile)
        if token:
            return token
    except Exception:
        pass

    # Fallback: check config file
    cfg = _load_config()
    profiles = cfg.get("profiles", {})
    section = profiles.get(profile, {})
    return section.get("api_token")


def _delete_token(profile: str) -> None:
    """Delete the API token from the system keyring."""
    try:
        import keyring

        keyring.delete_password("netskope-cli", profile)
    except Exception:
        pass  # Token may not exist — that is fine


def _resolve_profile(ctx: typer.Context) -> str:
    """Return the profile to operate on, respecting the global --profile flag.

    Resolution: explicit --profile flag > NETSKOPE_PROFILE env var >
    active_profile in config > "default".
    When --profile is not passed, state.profile is None (not "default"), so we
    fall through to the env var and then the config file's active_profile setting.
    """
    state = ctx.obj
    if state is not None and state.profile is not None:
        return state.profile
    env_profile = os.environ.get("NETSKOPE_PROFILE")
    if env_profile:
        return env_profile
    cfg = _load_config()
    return _active_profile(cfg)


def _get_console(ctx: typer.Context) -> Console:
    """Build a Console, respecting global --no-color."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@config_app.command("set-tenant")
def set_tenant(
    ctx: typer.Context,
    hostname: str = typer.Argument(
        ...,
        help=(
            "Fully qualified tenant hostname for your Netskope instance. "
            "For example: 'mytenant.goskope.com' or 'company.eu.goskope.com'. "
            "This is the base URL used for all API calls."
        ),
    ),
) -> None:
    """Set the Netskope tenant hostname for the active profile.

    Saves the tenant hostname to the profile configuration. This must be set
    before running any API commands. The hostname identifies your Netskope
    tenant instance.

    Examples:
        netskope config set-tenant mytenant.goskope.com
        netskope config set-tenant company.eu.goskope.com --profile staging
    """
    profile = _resolve_profile(ctx)
    cfg = _load_config()

    # First-run: if no profiles exist yet, create the "default" profile and
    # set it as active so the getting-started flow is smooth.
    if not cfg.get("profiles"):
        cfg["profiles"] = {}
    if "active_profile" not in cfg:
        cfg["active_profile"] = profile

    section = _get_profile_section(cfg, profile)
    section["tenant"] = hostname
    _save_config(cfg)

    console = _get_console(ctx)
    console.print(
        f"[green]Tenant set to[/green] [bold]{hostname}[/bold] " f"[green]for profile[/green] [bold]'{profile}'[/bold]."
    )


@config_app.command("set-token")
def set_token(
    ctx: typer.Context,
    token_arg: Optional[str] = typer.Argument(
        None,
        help=("API token value (positional). You can also use --token or the " "interactive prompt instead."),
        show_default=False,
    ),
    token_opt: Optional[str] = typer.Option(
        None,
        "--token",
        help=(
            "API token value. When provided, skips the interactive prompt. "
            "For CI/CD you can also pipe via stdin: "
            "echo $TOKEN | netskope config set-token"
        ),
    ),
) -> None:
    """Securely store an API token for the active profile.

    Four ways to provide the token (most secure first):

    \b
    1. Interactive prompt (default): netskope config set-token
    2. Pipe via stdin:              echo "$TOKEN" | netskope config set-token
    3. Inline flag:                 netskope config set-token --token "$TOKEN"
    4. Positional argument:         netskope config set-token "$TOKEN"

    The token is stored in the system keyring when available, with a plaintext
    config-file fallback (with a warning).  Obtain tokens from the Netskope
    admin console under Settings > Tools > REST API.  You can also skip
    storage entirely by setting the NETSKOPE_API_TOKEN environment variable.

    Examples:
        netskope config set-token
        netskope config set-token --token "$NETSKOPE_API_TOKEN"
        echo "$TOKEN" | netskope config set-token
        netskope config set-token "$TOKEN"
        netskope config set-token --profile production
    """
    profile = _resolve_profile(ctx)
    console = _get_console(ctx)

    # Determine token value: --token flag > positional arg > stdin pipe > interactive prompt
    token: str | None = token_opt or token_arg
    if token is None and not sys.stdin.isatty():
        token = sys.stdin.read().strip()
    if token is None:
        console.print(f"Storing API token for profile [bold]{profile}[/bold].")
        token = getpass.getpass("API token: ")

    if not token or not token.strip():
        console.print("[red]Token cannot be empty.[/red]")
        raise typer.Exit(code=1)

    token = token.strip()
    used_keyring = _store_token(profile, token, console=console)
    if used_keyring:
        console.print(f"[green]Token stored in keyring for profile[/green] " f"[bold]'{profile}'[/bold].")
    else:
        console.print(f"[green]Token stored for profile[/green] [bold]'{profile}'[/bold].")


@config_app.command("set-ca-bundle")
def set_ca_bundle(
    ctx: typer.Context,
    path: Optional[str] = typer.Argument(
        None,
        help=(
            "Path to a CA certificate bundle file (PEM format). "
            "Used when the Netskope client is performing SSL inspection. "
            "Pass 'auto' to search well-known paths, or 'clear' to remove."
        ),
    ),
) -> None:
    """Set a custom CA certificate bundle for SSL verification.

    Required when the Netskope client performs SSL inspection and Python's
    default certificate store doesn't include the Netskope proxy CA.

    \b
    Examples:
        netskope config set-ca-bundle /path/to/nscacert.pem
        netskope config set-ca-bundle auto          # auto-detect
        netskope config set-ca-bundle clear          # remove setting
        export NETSKOPE_CA_BUNDLE=/path/to/cert.pem  # env var alternative
    """
    from netskope_cli.core.config import find_netskope_ca_cert

    profile = _resolve_profile(ctx)
    console = _get_console(ctx)
    cfg = _load_config()
    section = _get_profile_section(cfg, profile)

    if path is None:
        # Interactive: try auto-detect
        detected = find_netskope_ca_cert()
        if detected:
            console.print(f"[green]Found Netskope CA cert:[/green] {detected}")
            path = detected
        else:
            console.print("[yellow]No Netskope CA cert found in well-known paths.[/yellow]")
            console.print("Please provide the path to your CA bundle file:")
            console.print("  [cyan]netskope config set-ca-bundle /path/to/nscacert.pem[/cyan]")
            raise typer.Exit(code=1)

    if path == "clear":
        section.pop("ca_bundle", None)
        _save_config(cfg)
        console.print(f"[green]CA bundle cleared for profile[/green] [bold]'{profile}'[/bold].")
        return

    if path == "auto":
        detected = find_netskope_ca_cert()
        if detected:
            path = detected
            console.print(f"[green]Auto-detected:[/green] {path}")
        else:
            console.print("[red]Could not find Netskope CA cert in well-known paths.[/red]")
            console.print("Provide the path manually: netskope config set-ca-bundle /path/to/cert.pem")
            raise typer.Exit(code=1)

    # Validate the file exists
    ca_path = Path(path)
    if not ca_path.is_file():
        console.print(f"[red]File not found:[/red] {path}")
        raise typer.Exit(code=1)

    section["ca_bundle"] = str(ca_path.resolve())
    _save_config(cfg)
    console.print(
        f"[green]CA bundle set to[/green] [bold]{ca_path.resolve()}[/bold] "
        f"[green]for profile[/green] [bold]'{profile}'[/bold]."
    )


@config_app.command("show")
def show(
    ctx: typer.Context,
) -> None:
    """Display the current configuration for the active profile with secrets masked.

    Shows the profile name, tenant hostname, API token status (masked), and any
    additional configuration keys. Use this to verify your setup or debug
    configuration issues.

    Examples:
        netskope config show
        netskope config show --profile staging
    """
    profile = _resolve_profile(ctx)
    cfg = _load_config()
    section = _get_profile_section(cfg, profile)
    console = _get_console(ctx)

    table = Table(title=f"Configuration — profile '{profile}'", show_lines=True)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Source", style="dim")

    table.add_row("profile", profile, "config")

    # Tenant: check env var override
    env_tenant = os.environ.get("NETSKOPE_TENANT")
    config_tenant = section.get("tenant")
    if env_tenant:
        table.add_row("tenant", env_tenant, "env var (NETSKOPE_TENANT)")
    elif config_tenant:
        table.add_row("tenant", config_tenant, "config")
    else:
        table.add_row("tenant", "[dim]not set[/dim]", "")

    # Token: check env var, then keyring, then config file
    env_token = os.environ.get("NETSKOPE_API_TOKEN")
    keyring_token = _get_token(profile)
    if env_token:
        table.add_row("token", _mask_token(env_token), "env var (NETSKOPE_API_TOKEN)")
    elif keyring_token:
        # Determine if from keyring or config file
        token_source = "keyring"
        try:
            import keyring as _kr

            kr_val = _kr.get_password("netskope-cli", profile)
            if not kr_val:
                token_source = "config file"
        except Exception:
            token_source = "config file"
        table.add_row("token", _mask_token(keyring_token), token_source)
    else:
        table.add_row("token", "[dim]not set[/dim]", "")

    # Show any extra keys stored in the profile section
    for key, value in sorted(section.items()):
        if key in ("tenant", "api_token"):
            continue
        table.add_row(key, str(value), "config")

    console.print(table)


@config_app.command("profiles")
def profiles(
    ctx: typer.Context,
) -> None:
    """List all configured profiles with their tenant hostnames.

    Displays a table of all profiles showing name, tenant hostname, and which
    profile is currently active (marked with *). Use this to see all available
    profiles and switch between them with 'netskope config use-profile'.

    Examples:
        netskope config profiles
    """
    cfg = _load_config()
    active = _active_profile(cfg)
    all_profiles = cfg.get("profiles", {})
    console = _get_console(ctx)

    if not all_profiles:
        console.print("[dim]No profiles configured yet. Create one with:[/dim]")
        console.print("  netskope config create-profile NAME --tenant HOSTNAME")
        return

    table = Table(title="Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Tenant", style="white")
    table.add_column("Active", style="green")

    for name in sorted(all_profiles):
        section = all_profiles[name]
        marker = "*" if name == active else ""
        table.add_row(name, section.get("tenant", ""), marker)

    console.print(table)


@config_app.command("use-profile")
def use_profile(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "Name of the profile to switch to. Must be an existing profile. "
            "View available profiles with 'netskope config profiles'."
        ),
    ),
) -> None:
    """Switch the active configuration profile.

    Changes which profile is used by default for all commands. The active
    profile determines the tenant, API token, and other settings. Use profiles
    to manage multiple Netskope tenants (e.g. production, staging).

    Examples:
        netskope config use-profile production
        netskope config use-profile staging
    """
    cfg = _load_config()
    all_profiles = cfg.get("profiles", {})
    console = _get_console(ctx)

    if name not in all_profiles:
        console.print(f"[red]Profile '{name}' does not exist.[/red]")
        console.print("[dim]Available profiles:[/dim]", ", ".join(sorted(all_profiles)) or "(none)")
        raise typer.Exit(code=1)

    cfg["active_profile"] = name
    _save_config(cfg)
    console.print(f"[green]Switched to profile[/green] [bold]{name}[/bold].")


@config_app.command("create-profile")
def create_profile(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "Name for the new profile. Use a descriptive name like 'production', "
            "'staging', or 'dev'. Must be unique across all profiles."
        ),
    ),
    tenant: Optional[str] = typer.Option(
        None,
        "--tenant",
        "-t",
        help=(
            "Tenant hostname to associate with this profile. For example: "
            "'mytenant.goskope.com'. Can be set later with 'netskope config set-tenant'."
        ),
    ),
) -> None:
    """Create a new configuration profile for a Netskope tenant.

    Profiles store tenant-specific settings and credentials. If this is the
    first profile created, it automatically becomes the active profile. After
    creating a profile, set credentials with 'netskope config set-token' or
    'netskope auth login'.

    Examples:
        netskope config create-profile production --tenant prod.goskope.com
        netskope config create-profile staging --tenant staging.goskope.com
        netskope config create-profile dev
    """
    cfg = _load_config()
    all_profiles = cfg.setdefault("profiles", {})
    console = _get_console(ctx)

    if name in all_profiles:
        console.print(f"[red]Profile '{name}' already exists.[/red]")
        raise typer.Exit(code=1)

    section: dict = {}
    if tenant:
        section["tenant"] = tenant

    all_profiles[name] = section

    # If this is the very first profile, make it active
    if "active_profile" not in cfg:
        cfg["active_profile"] = name

    _save_config(cfg)
    console.print(f"[green]Profile '{name}' created.[/green]")
    if tenant:
        console.print(f"  Tenant: [bold]{tenant}[/bold]")


@config_app.command("setup")
def setup(
    ctx: typer.Context,
    profile_name: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile name to create or configure. Defaults to 'default'.",
    ),
    tenant: Optional[str] = typer.Option(
        None,
        "--tenant",
        "-t",
        help="Tenant hostname. If not provided, you will be prompted.",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="API token. If not provided, you will be prompted interactively.",
    ),
) -> None:
    """Interactive setup wizard — configure tenant, token, and profile in one step.

    Guides you through creating a profile, setting the tenant hostname, and
    storing the API token. Replaces the need to run create-profile, set-tenant,
    and set-token as separate commands.

    \b
    Examples:
        netskope config setup
        netskope config setup --tenant mytenant.goskope.com
        netskope config setup --profile production --tenant prod.goskope.com
        echo "$TOKEN" | netskope config setup --tenant mytenant.goskope.com
    """
    console = _get_console(ctx)
    cfg = _load_config()

    # 1. Profile
    profile = profile_name or _resolve_profile(ctx)
    all_profiles = cfg.setdefault("profiles", {})
    if profile not in all_profiles:
        all_profiles[profile] = {}
        console.print(f"[green]Created profile[/green] [bold]'{profile}'[/bold].")
    else:
        console.print(f"Using existing profile [bold]'{profile}'[/bold].")

    if "active_profile" not in cfg:
        cfg["active_profile"] = profile

    section = _get_profile_section(cfg, profile)

    # 2. Tenant
    if tenant is None:
        existing = section.get("tenant")
        prompt_msg = "Tenant hostname"
        if existing:
            prompt_msg += f" [{existing}]"
        prompt_msg += ": "
        tenant_input = input(prompt_msg).strip()
        if tenant_input:
            tenant = tenant_input
        elif existing:
            tenant = existing
        else:
            console.print("[red]Tenant hostname is required.[/red]")
            raise typer.Exit(code=1)

    section["tenant"] = tenant
    _save_config(cfg)
    console.print(f"[green]Tenant set to[/green] [bold]{tenant}[/bold].")

    # 3. Token
    if token is None and not sys.stdin.isatty():
        token = sys.stdin.read().strip()
    if token is None:
        console.print()
        console.print("Set your API token (from Settings > Tools > REST API v2).")
        token = getpass.getpass("API token: ")

    if not token or not token.strip():
        console.print("[yellow]No token provided — skipping token setup.[/yellow]")
        console.print("[dim]Run 'netskope config set-token' later to add credentials.[/dim]")
    else:
        token = token.strip()
        used_keyring = _store_token(profile, token, console=console)
        storage = "keyring" if used_keyring else "config"
        console.print(f"[green]Token stored ({storage}) for profile[/green] [bold]'{profile}'[/bold].")

    # 4. Summary
    console.print()
    console.print("[bold green]Setup complete![/bold green]")
    console.print(f"  Profile: [bold]{profile}[/bold]")
    console.print(f"  Tenant:  [bold]{tenant}[/bold]")
    console.print()
    console.print("[dim]Try: netskope alerts list --limit 5[/dim]")


@config_app.command("test")
def test_config(
    ctx: typer.Context,
) -> None:
    """Test API connectivity with the current profile credentials.

    Makes a lightweight API call (GET /api/v2/events/data/audit with limit=1)
    to verify that the configured tenant hostname and API token are valid and
    working. Use this to quickly check your setup after configuring a new
    profile or rotating credentials.

    Examples:
        netskope config test
        netskope config test --profile staging
    """
    from netskope_cli.core.client import NetskopeClient
    from netskope_cli.core.config import (
        get_active_profile,
        get_api_token,
        get_session_cookie,
        get_tenant_url,
        load_config,
    )

    profile = _resolve_profile(ctx)
    console = _get_console(ctx)

    cfg = load_config()
    active = get_active_profile(cfg, cli_profile=profile)

    try:
        base_url = get_tenant_url(profile=active, cfg=cfg)
    except (ValueError, ConfigError) as exc:
        console.print(f"[bold red]FAIL[/bold red] {exc}")
        console.print("[dim]Hint: Run `netskope config set-tenant HOSTNAME` first.[/dim]")
        raise typer.Exit(code=1)

    api_token = get_api_token(profile=active, cfg=cfg)
    ci_session = get_session_cookie(profile=active, cfg=cfg)

    if not api_token and not ci_session:
        console.print("[bold red]FAIL[/bold red] No credentials configured for " f"profile '{active}'.")
        console.print("[dim]Hint: Run `netskope config set-token` or " "`netskope auth login`.[/dim]")
        raise typer.Exit(code=1)

    client = NetskopeClient(
        base_url=base_url,
        api_token=api_token,
        ci_session=ci_session,
    )

    import time

    now = int(time.time())

    try:
        client.request(
            "GET",
            "/api/v2/events/data/audit",
            params={"starttime": now - 3600, "endtime": now, "limit": 1},
        )
        console.print(
            f"[bold green]OK[/bold green] Successfully connected to "
            f"[bold]{base_url}[/bold] using profile '{active}'."
        )
    except Exception as exc:
        console.print(f"[bold red]FAIL[/bold red] API call failed: {exc}")
        console.print("[dim]Hint: Check your tenant hostname and API token. " "Use --verbose for more details.[/dim]")
        raise typer.Exit(code=1)
