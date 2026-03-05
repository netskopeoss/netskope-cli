"""Core configuration module for the Netskope CLI.

Provides XDG-compliant configuration management with support for multiple
tenant profiles, environment variable overrides, and a layered configuration
hierarchy: CLI flags > env vars > profile config > defaults.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import toml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# XDG base directories
# ---------------------------------------------------------------------------

_APP_NAME = "netskope"


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def config_dir() -> Path:
    """Return the Netskope config directory (~/.config/netskope/)."""
    return _xdg_config_home() / _APP_NAME


def cache_dir() -> Path:
    """Return the Netskope cache directory (~/.cache/netskope/)."""
    return _xdg_cache_home() / _APP_NAME


def data_dir() -> Path:
    """Return the Netskope data directory (~/.local/share/netskope/)."""
    return _xdg_data_home() / _APP_NAME


def config_file_path() -> Path:
    """Return the path to the TOML config file."""
    return config_dir() / "config.toml"


# ---------------------------------------------------------------------------
# Profile model
# ---------------------------------------------------------------------------

DEFAULT_PROFILE_NAME = "default"


class ProfileConfig(BaseModel):
    """A single tenant profile."""

    tenant: str = ""
    api_token: Optional[str] = None
    auth_type: str = Field(default="token", pattern=r"^(token|session)$")

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Top-level TOML file model
# ---------------------------------------------------------------------------


class NetskopeConfig(BaseModel):
    """Represents the full contents of config.toml."""

    active_profile: str = DEFAULT_PROFILE_NAME
    output_format: str = "table"
    no_color: bool = False
    profiles: dict[str, ProfileConfig] = Field(default_factory=lambda: {DEFAULT_PROFILE_NAME: ProfileConfig()})

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Environment-backed settings (pydantic-settings)
# ---------------------------------------------------------------------------


class EnvSettings(BaseSettings):
    """Settings populated from environment variables.

    These take precedence over values found in the config file.
    """

    netskope_tenant: Optional[str] = None
    netskope_api_token: Optional[str] = None
    netskope_profile: Optional[str] = None
    netskope_output_format: Optional[str] = None
    netskope_no_color: Optional[bool] = None

    model_config = SettingsConfigDict(
        env_prefix="",  # variable names already include the prefix
        case_sensitive=False,
    )


# ---------------------------------------------------------------------------
# Load / save helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> Path:
    """Create the directory (and parents) if it does not exist.

    Directories are created with mode 0o700 so that only the owning user
    can list or traverse them.
    """
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


# ---------------------------------------------------------------------------
# Profile name validation
# ---------------------------------------------------------------------------

_VALID_PROFILE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_profile_name(name: str) -> str:
    """Validate a profile name to prevent path traversal and injection.

    Raises ``ValueError`` if the name is invalid.
    """
    if not name or not _VALID_PROFILE_RE.match(name) or ".." in name:
        raise ValueError(
            f"Invalid profile name {name!r}. "
            "Profile names must start with a letter or digit and contain only "
            "letters, digits, dots, hyphens, and underscores."
        )
    return name


def load_config() -> NetskopeConfig:
    """Load the Netskope configuration from disk.

    If the config file does not exist, a default configuration is returned
    (but *not* written to disk automatically).
    """
    path = config_file_path()
    if not path.exists():
        return NetskopeConfig()

    raw = toml.load(path)

    # Normalise the profiles sub-table: each key under [profiles.*] becomes
    # a ProfileConfig.
    raw_profiles = raw.pop("profiles", {})
    profiles: dict[str, ProfileConfig] = {}
    for name, values in raw_profiles.items():
        if isinstance(values, dict):
            profiles[name] = ProfileConfig(**values)
        else:
            profiles[name] = ProfileConfig()

    if not profiles:
        profiles[DEFAULT_PROFILE_NAME] = ProfileConfig()

    return NetskopeConfig(profiles=profiles, **raw)


def save_config(cfg: NetskopeConfig) -> Path:
    """Persist the configuration to the TOML file on disk.

    Returns the path to the written file.
    """
    path = config_file_path()
    _ensure_dir(path.parent)

    data: dict[str, Any] = cfg.model_dump(exclude={"profiles"})
    # Serialise profiles as nested TOML tables.
    data["profiles"] = {}
    for name, profile in cfg.profiles.items():
        profile_data = profile.model_dump()
        # Strip None api_token so we never write placeholder secrets.
        if profile_data.get("api_token") is None:
            profile_data.pop("api_token", None)
        data["profiles"][name] = profile_data

    # Open with restrictive permissions (0o600) so only the owning user
    # can read the file — it may contain plaintext API tokens as a fallback.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            toml.dump(data, fh)
    except BaseException:
        os.close(fd)
        raise

    return path


# ---------------------------------------------------------------------------
# Profile accessors
# ---------------------------------------------------------------------------


def _resolve_env() -> EnvSettings:
    """Return current environment variable overrides."""
    return EnvSettings()


def get_active_profile(
    cfg: NetskopeConfig | None = None,
    cli_profile: str | None = None,
) -> str:
    """Determine the active profile name.

    Resolution order: *cli_profile* flag > ``NETSKOPE_PROFILE`` env var >
    ``active_profile`` in config file > ``"default"``.
    """
    if cli_profile:
        return cli_profile

    env = _resolve_env()
    if env.netskope_profile:
        return env.netskope_profile

    if cfg is None:
        cfg = load_config()
    return cfg.active_profile


def set_active_profile(name: str, cfg: NetskopeConfig | None = None) -> NetskopeConfig:
    """Set the active profile in the config and save to disk.

    If the profile does not exist yet it is created with empty defaults.
    Returns the updated configuration.
    """
    _validate_profile_name(name)
    if cfg is None:
        cfg = load_config()

    if name not in cfg.profiles:
        cfg.profiles[name] = ProfileConfig()

    cfg.active_profile = name
    save_config(cfg)
    return cfg


def _get_profile(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
) -> tuple[str, ProfileConfig]:
    """Return ``(profile_name, ProfileConfig)`` for the given or active profile."""
    if cfg is None:
        cfg = load_config()
    name = get_active_profile(cfg, cli_profile=profile)
    return name, cfg.profiles.get(name, ProfileConfig())


# ---------------------------------------------------------------------------
# Tenant / URL helpers
# ---------------------------------------------------------------------------


def get_tenant_url(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
    cli_tenant: str | None = None,
) -> str:
    """Return the base URL for the tenant of the given profile.

    Resolution order: *cli_tenant* flag > ``NETSKOPE_TENANT`` env var >
    profile config.

    The returned URL is always ``https://<hostname>`` with no trailing slash.
    """
    tenant = _resolve_tenant(profile=profile, cfg=cfg, cli_tenant=cli_tenant)
    if not tenant:
        raise ValueError(
            "No tenant configured. Set it via `netskope config set-tenant`, "
            "NETSKOPE_TENANT env var, or in your profile configuration."
        )
    return _build_base_url(tenant)


def _resolve_tenant(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
    cli_tenant: str | None = None,
) -> str:
    """Resolve the tenant hostname using the standard hierarchy."""
    if cli_tenant:
        return cli_tenant

    env = _resolve_env()
    if env.netskope_tenant:
        return env.netskope_tenant

    _, pcfg = _get_profile(profile, cfg)
    return pcfg.tenant


def _build_base_url(tenant: str) -> str:
    """Construct ``https://<tenant>`` from a raw hostname.

    If the caller already passed a full URL, strip the scheme so we always
    return a clean ``https://`` URL with no trailing slash.

    Shorthand names without a dot (e.g. ``sedemo``) are expanded to
    ``<name>.goskope.com`` automatically.
    """
    tenant = tenant.strip().rstrip("/")
    if tenant.startswith("https://"):
        tenant = tenant[len("https://") :]
    elif tenant.startswith("http://"):
        tenant = tenant[len("http://") :]
    # Auto-append default domain for shorthand names (no dots)
    if "." not in tenant:
        tenant = f"{tenant}.goskope.com"
    return f"https://{tenant}"


# ---------------------------------------------------------------------------
# API token helpers
# ---------------------------------------------------------------------------


def _get_keyring_token(profile_name: str) -> str | None:
    """Attempt to retrieve a token from the system keyring.

    Returns ``None`` if the keyring is unavailable or the token is not stored.
    """
    try:
        import keyring

        return keyring.get_password("netskope-cli", profile_name)
    except Exception:
        return None


def get_api_token(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
    cli_token: str | None = None,
) -> str | None:
    """Return the API token for a profile.

    Resolution order: *cli_token* flag > ``NETSKOPE_API_TOKEN`` env var >
    system keyring > profile config ``api_token``.

    Returns ``None`` if no token is available anywhere.
    """
    if cli_token:
        return cli_token

    env = _resolve_env()
    if env.netskope_api_token:
        return env.netskope_api_token

    name, pcfg = _get_profile(profile, cfg)

    # Try the system keyring first, then fall back to config file.
    keyring_token = _get_keyring_token(name)
    if keyring_token:
        return keyring_token

    return pcfg.api_token


# ---------------------------------------------------------------------------
# Session cookie helpers (stored in data dir)
# ---------------------------------------------------------------------------

_SESSION_FILENAME_TEMPLATE = "session_{profile}.json"


def _session_file(profile: str) -> Path:
    """Return the path to the session cookie file for *profile*."""
    _validate_profile_name(profile)
    return data_dir() / _SESSION_FILENAME_TEMPLATE.format(profile=profile)


def get_session_cookie(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
) -> str | None:
    """Read and return the stored session cookie for the profile.

    Returns ``None`` if no session file exists or the file is empty.
    """
    name, _ = _get_profile(profile, cfg)
    path = _session_file(name)
    if not path.exists():
        return None
    content = path.read_text().strip()
    return content if content else None


def save_session_cookie(
    cookie: str,
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
) -> Path:
    """Persist a session cookie to the data directory.

    Returns the path to the written file.
    """
    name, _ = _get_profile(profile, cfg)
    path = _session_file(name)
    _ensure_dir(path.parent)
    # Write with restrictive permissions from the start — avoid the race
    # condition of write-then-chmod where the file is briefly world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(cookie)
    except BaseException:
        os.close(fd)
        raise
    return path


def delete_session_cookie(
    profile: str | None = None,
    cfg: NetskopeConfig | None = None,
) -> bool:
    """Remove the session cookie file for the profile.

    Returns ``True`` if a file was deleted, ``False`` otherwise.
    """
    name, _ = _get_profile(profile, cfg)
    path = _session_file(name)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Convenience: merged effective settings
# ---------------------------------------------------------------------------


def get_effective_settings(
    cli_profile: str | None = None,
    cli_tenant: str | None = None,
    cli_token: str | None = None,
    cli_output_format: str | None = None,
    cli_no_color: bool | None = None,
) -> dict[str, Any]:
    """Return a flat dict of fully-resolved settings.

    This applies the full configuration hierarchy (CLI > env > profile >
    defaults) and is useful for commands that need all settings at once.
    """
    cfg = load_config()
    env = _resolve_env()

    profile_name = get_active_profile(cfg, cli_profile=cli_profile)
    pcfg = cfg.profiles.get(profile_name, ProfileConfig())

    # output_format
    output_format = cli_output_format or env.netskope_output_format or cfg.output_format or "table"

    # no_color
    if cli_no_color is not None:
        no_color = cli_no_color
    elif env.netskope_no_color is not None:
        no_color = env.netskope_no_color
    else:
        no_color = cfg.no_color

    return {
        "profile": profile_name,
        "tenant": _resolve_tenant(profile=profile_name, cfg=cfg, cli_tenant=cli_tenant),
        "api_token": get_api_token(profile=profile_name, cfg=cfg, cli_token=cli_token),
        "auth_type": pcfg.auth_type,
        "output_format": output_format,
        "no_color": no_color,
    }
