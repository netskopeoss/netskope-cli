"""Authentication commands for the Netskope CLI.

Provides login, logout, status, and token-info subcommands.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from netskope_cli.core.exceptions import AuthError, ConfigError

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
auth_app = typer.Typer(
    name="auth",
    help=(
        "Authenticate with Netskope and manage credentials.\n\n"
        "This command group handles authentication lifecycle: browser-based login, "
        "credential status checks, token inspection, and logout. Credentials are "
        "stored securely in the system keyring. Each profile maintains its own "
        "set of credentials."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers (re-uses config_cmd helpers for profile/token management)
# ---------------------------------------------------------------------------


def _get_console(ctx: typer.Context) -> Console:
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def _resolve_profile(ctx: typer.Context) -> str:
    """Return the effective profile name."""
    from netskope_cli.commands.config_cmd import _active_profile, _load_config

    state = ctx.obj
    if state is not None and state.profile is not None:
        return state.profile
    cfg = _load_config()
    return _active_profile(cfg)


def _get_token(profile: str) -> str | None:
    """Retrieve token from keyring."""
    try:
        import keyring

        return keyring.get_password("netskope-cli", profile)
    except Exception:
        return None


def _delete_token(profile: str) -> None:
    """Remove token from keyring."""
    try:
        import keyring

        keyring.delete_password("netskope-cli", profile)
    except Exception:
        pass


def _mask_token(token: str) -> str:
    if len(token) < 20:
        return "****"
    return token[:4] + "****" + token[-4:]


def _get_tenant(profile: str) -> str | None:
    """Return the tenant hostname for the given profile, or None.

    Uses the core config module's ``get_tenant_url`` which properly checks
    env vars (``NETSKOPE_TENANT``) before falling back to the profile config.
    """
    try:
        from netskope_cli.core.config import get_tenant_url, load_config

        cfg = load_config()
        url = get_tenant_url(profile=profile, cfg=cfg)
        # get_tenant_url returns "https://hostname" — strip the scheme
        return url.removeprefix("https://").removeprefix("http://")
    except (ValueError, Exception):
        # Fall back to direct config lookup
        from netskope_cli.commands.config_cmd import _get_profile_section, _load_config

        cfg = _load_config()
        section = _get_profile_section(cfg, profile)
        return section.get("tenant")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@auth_app.command("login")
def login(
    ctx: typer.Context,
    headless: bool = typer.Option(
        False,
        "--headless",
        help=(
            "Run the authentication browser in headless mode (no visible window). "
            "Useful for automated environments where a display is not available. "
            "Defaults to False (opens a visible browser window)."
        ),
    ),
    timeout: int = typer.Option(
        120,
        "--timeout",
        help=(
            "Maximum number of seconds to wait for the login to complete. If the user "
            "does not finish authenticating within this time, the operation fails. "
            "Defaults to 120 seconds."
        ),
    ),
) -> None:
    """Authenticate via browser-based login to your Netskope tenant.

    Opens the Netskope tenant login page in your default browser and captures
    the session cookie for API access. The session is saved to the system
    keyring under the active profile. You must configure a tenant first with
    'netskope config set-tenant'.

    Examples:
        netskope auth login
        netskope auth login --headless --timeout 60
        netskope auth login --profile staging
    """
    from netskope_cli.core.browser_auth import browser_login

    profile = _resolve_profile(ctx)
    tenant = _get_tenant(profile)
    console = _get_console(ctx)

    if not tenant:
        console.print(f"[yellow]No tenant configured for profile '{profile}'.[/yellow]")
        tenant = typer.prompt("Enter your Netskope tenant hostname (e.g. mytenant.goskope.com)")
        tenant = tenant.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        if not tenant:
            raise ConfigError(
                "No tenant provided.",
                suggestion="Run `netskope config set-tenant HOSTNAME` to configure.",
            )
        # Persist the tenant so the user doesn't have to enter it again
        from netskope_cli.core.config import load_config as _load_cfg
        from netskope_cli.core.config import save_config as _save_cfg

        cfg = _load_cfg()
        if profile not in cfg.profiles:
            from netskope_cli.core.config import ProfileConfig

            cfg.profiles[profile] = ProfileConfig()
        cfg.profiles[profile].tenant = tenant
        _save_cfg(cfg)
        console.print(f"[green]Tenant saved[/green] for profile '{profile}'.")

    console.print(f"Logging in to [bold]{tenant}[/bold] (profile: {profile})...")
    console.print("[dim]A browser window will open. Complete the login there.[/dim]")

    browser_login(
        tenant_url=f"https://{tenant}",
        profile=profile,
        headless=headless,
        timeout_seconds=timeout,
    )

    console.print(f"[green]Login successful![/green] Session saved for profile '{profile}'.")


@auth_app.command("status")
def status(
    ctx: typer.Context,
) -> None:
    """Show the current authentication status for the active profile.

    Displays whether a tenant is configured, an API token is stored, and a
    session cookie is available. Use this to verify that credentials are set up
    correctly before running other commands.

    Examples:
        netskope auth status
        netskope auth status --profile production
    """
    profile = _resolve_profile(ctx)
    tenant = _get_tenant(profile)
    keyring_token = _get_token(profile)
    console = _get_console(ctx)

    # Determine the effective token and its source using the same resolution
    # order that actual API commands use (env var > keyring/config).
    from netskope_cli.core.config import get_api_token, get_session_cookie, load_config

    cfg = load_config()
    env_token = os.environ.get("NETSKOPE_API_TOKEN")
    effective_token = get_api_token(profile=profile, cfg=cfg)

    # Figure out which source provided the effective token.
    if env_token and effective_token == env_token:
        token_source = "NETSKOPE_API_TOKEN env var"
    elif keyring_token and effective_token == keyring_token:
        token_source = "keyring"
    elif effective_token:
        token_source = "profile config"
    else:
        token_source = None

    table = Table(title=f"Auth Status \u2014 profile '{profile}'", show_lines=True)
    table.add_column("Item", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")

    # Tenant
    if tenant:
        table.add_row("Tenant", tenant)
    else:
        table.add_row("Tenant", "[red]not configured[/red]")

    # Token – show effective token and its source
    if effective_token:
        table.add_row("API token", f"[green]set[/green] (source: {token_source})")
    else:
        table.add_row("API token", "[red]not set[/red]")

    # Session cookie
    session = get_session_cookie(profile, cfg)
    if session:
        table.add_row("Session cookie", "[green]set[/green]")
    else:
        table.add_row("Session cookie", "[dim]not set[/dim]")

    table.add_row("Checked at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

    console.print(table)
    console.print("[dim]Tip: Run 'netskope config test' to verify your credentials work.[/dim]")


@auth_app.command("logout")
def logout(
    ctx: typer.Context,
) -> None:
    """Clear all stored credentials (token and session) for the active profile.

    Removes the API token from the system keyring and deletes any stored session
    cookies. After logout, you will need to re-authenticate with 'netskope auth
    login' or set a new token with 'netskope config set-token'.

    Examples:
        netskope auth logout
        netskope auth logout --profile staging
    """
    profile = _resolve_profile(ctx)
    console = _get_console(ctx)

    from netskope_cli.core.config import delete_session_cookie, load_config, save_config

    token = _get_token(profile)
    cfg = load_config()

    # Check for config-file fallback token
    config_token = cfg.profiles.get(profile)
    has_config_token = config_token and config_token.api_token

    had_session = False
    try:
        had_session = delete_session_cookie(profile, cfg)
    except Exception:
        pass

    if not token and not has_config_token and not had_session:
        console.print(f"[dim]No credentials stored for profile '{profile}'.[/dim]")
        return

    # Clear keyring token
    if token:
        _delete_token(profile)

    # Clear config-file fallback token
    if has_config_token:
        cfg.profiles[profile].api_token = None
        save_config(cfg)

    console.print(f"[green]Credentials for profile '{profile}' have been removed.[/green]")


@auth_app.command("token")
def token_info(
    ctx: typer.Context,
) -> None:
    """Display the current API token information with the value masked.

    Shows the token's profile, associated tenant, a masked token preview (first
    and last 4 characters), and token length. The full token is never displayed.
    Use this to verify which token is configured without exposing secrets.

    Examples:
        netskope auth token
        netskope auth token --profile production
    """
    profile = _resolve_profile(ctx)
    token = _get_token(profile)
    tenant = _get_tenant(profile)
    console = _get_console(ctx)

    if not token:
        raise AuthError(
            f"No token stored for profile '{profile}'.",
            suggestion="Run `netskope config set-token` or `netskope auth login`.",
        )

    table = Table(title=f"Token Info — profile '{profile}'", show_lines=True)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Profile", profile)
    table.add_row("Tenant", tenant or "[dim]not set[/dim]")
    table.add_row("Token (masked)", _mask_token(token))
    table.add_row("Length", str(len(token)))

    console.print(table)
