"""Tests for netskope_cli.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest
import toml

from netskope_cli.core.config import (
    DEFAULT_PROFILE_NAME,
    NetskopeConfig,
    ProfileConfig,
    _build_base_url,
    cache_dir,
    config_dir,
    config_file_path,
    data_dir,
    delete_session_cookie,
    get_active_profile,
    get_api_token,
    get_session_cookie,
    get_tenant_url,
    load_config,
    save_config,
    save_session_cookie,
)

# ---------------------------------------------------------------------------
# XDG directory helpers
# ---------------------------------------------------------------------------


class TestXDGDirectories:
    def test_config_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = config_dir()
        assert result == Path.home() / ".config" / "netskope"

    def test_config_dir_custom(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert config_dir() == tmp_path / "netskope"

    def test_cache_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert cache_dir() == Path.home() / ".cache" / "netskope"

    def test_cache_dir_custom(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert cache_dir() == tmp_path / "netskope"

    def test_data_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert data_dir() == Path.home() / ".local" / "share" / "netskope"

    def test_data_dir_custom(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert data_dir() == tmp_path / "netskope"

    def test_config_file_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert config_file_path() == tmp_path / "netskope" / "config.toml"


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------


class TestLoadSaveConfig:
    def test_load_config_missing_file_returns_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = load_config()
        assert cfg.active_profile == DEFAULT_PROFILE_NAME
        assert cfg.output_format == "table"
        assert cfg.no_color is False
        assert DEFAULT_PROFILE_NAME in cfg.profiles

    def test_save_and_load_roundtrip(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        cfg = NetskopeConfig(
            active_profile="production",
            output_format="json",
            no_color=True,
            profiles={
                "production": ProfileConfig(tenant="prod.goskope.com", auth_type="token"),
                "staging": ProfileConfig(tenant="staging.goskope.com", auth_type="session"),
            },
        )
        written_path = save_config(cfg)
        assert written_path.exists()

        loaded = load_config()
        assert loaded.active_profile == "production"
        assert loaded.output_format == "json"
        assert loaded.no_color is True
        assert "production" in loaded.profiles
        assert "staging" in loaded.profiles
        assert loaded.profiles["production"].tenant == "prod.goskope.com"

    def test_save_config_strips_none_api_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = NetskopeConfig(
            profiles={"default": ProfileConfig(tenant="t.com", api_token=None)},
        )
        path = save_config(cfg)
        raw = toml.load(path)
        assert "api_token" not in raw["profiles"]["default"]

    def test_load_config_creates_default_profile_if_no_profiles(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If no [profiles.*] sub-tables exist, a default profile is created."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg_path = tmp_path / "netskope" / "config.toml"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text('active_profile = "default"\n')
        loaded = load_config()
        assert DEFAULT_PROFILE_NAME in loaded.profiles

    def test_load_config_with_profile_subtable(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Profile sub-tables under [profiles.*] are loaded correctly."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg_path = tmp_path / "netskope" / "config.toml"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text('active_profile = "prod"\n\n' "[profiles.prod]\n" 'tenant = "prod.goskope.com"\n')
        loaded = load_config()
        assert "prod" in loaded.profiles
        assert loaded.profiles["prod"].tenant == "prod.goskope.com"


# ---------------------------------------------------------------------------
# get_active_profile
# ---------------------------------------------------------------------------


class TestGetActiveProfile:
    def test_cli_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)
        cfg = NetskopeConfig(active_profile="from-config")
        assert get_active_profile(cfg, cli_profile="from-cli") == "from-cli"

    def test_env_var_over_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETSKOPE_PROFILE", "from-env")
        cfg = NetskopeConfig(active_profile="from-config")
        assert get_active_profile(cfg) == "from-env"

    def test_config_value_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)
        cfg = NetskopeConfig(active_profile="custom")
        assert get_active_profile(cfg) == "custom"

    def test_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert get_active_profile() == DEFAULT_PROFILE_NAME


# ---------------------------------------------------------------------------
# get_tenant_url
# ---------------------------------------------------------------------------


class TestGetTenantUrl:
    def test_plain_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_TENANT", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="mytenant.goskope.com")})
        assert get_tenant_url(cfg=cfg) == "https://mytenant.goskope.com"

    def test_strips_https_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_TENANT", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="https://mytenant.goskope.com/")})
        assert get_tenant_url(cfg=cfg) == "https://mytenant.goskope.com"

    def test_strips_http_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_TENANT", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="http://mytenant.goskope.com")})
        assert get_tenant_url(cfg=cfg) == "https://mytenant.goskope.com"

    def test_cli_tenant_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_TENANT", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="config-tenant.com")})
        assert get_tenant_url(cfg=cfg, cli_tenant="cli-tenant.com") == "https://cli-tenant.com"

    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETSKOPE_TENANT", "env-tenant.com")
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="config-tenant.com")})
        assert get_tenant_url(cfg=cfg) == "https://env-tenant.com"

    def test_raises_when_no_tenant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_TENANT", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(tenant="")})
        with pytest.raises(ValueError, match="No tenant configured"):
            get_tenant_url(cfg=cfg)


# ---------------------------------------------------------------------------
# get_api_token
# ---------------------------------------------------------------------------


class TestGetApiToken:
    def test_cli_token_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_API_TOKEN", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(api_token="config-token")})
        assert get_api_token(cfg=cfg, cli_token="cli-token") == "cli-token"

    def test_env_var_overrides_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "env-token")
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(api_token="config-token")})
        assert get_api_token(cfg=cfg) == "env-token"

    def test_config_token_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_API_TOKEN", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig(api_token="config-token")})
        assert get_api_token(cfg=cfg) == "config-token"

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_API_TOKEN", raising=False)
        cfg = NetskopeConfig(profiles={"default": ProfileConfig()})
        assert get_api_token(cfg=cfg) is None


# ---------------------------------------------------------------------------
# Session cookie helpers
# ---------------------------------------------------------------------------


class TestSessionCookie:
    def test_save_read_roundtrip(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)

        cfg = NetskopeConfig()
        save_session_cookie("abc123", cfg=cfg)
        assert get_session_cookie(cfg=cfg) == "abc123"

    def test_read_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)

        cfg = NetskopeConfig()
        assert get_session_cookie(cfg=cfg) is None

    def test_delete_returns_true_when_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)

        cfg = NetskopeConfig()
        save_session_cookie("token", cfg=cfg)
        assert delete_session_cookie(cfg=cfg) is True
        assert get_session_cookie(cfg=cfg) is None

    def test_delete_returns_false_when_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)

        cfg = NetskopeConfig()
        assert delete_session_cookie(cfg=cfg) is False

    def test_save_restricts_permissions(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.delenv("NETSKOPE_PROFILE", raising=False)

        cfg = NetskopeConfig()
        path = save_session_cookie("secret", cfg=cfg)
        assert path.stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# _build_base_url
# ---------------------------------------------------------------------------


class TestBuildBaseUrl:
    def test_plain_hostname(self) -> None:
        assert _build_base_url("tenant.goskope.com") == "https://tenant.goskope.com"

    def test_strips_trailing_slash(self) -> None:
        assert _build_base_url("tenant.goskope.com/") == "https://tenant.goskope.com"

    def test_strips_https(self) -> None:
        assert _build_base_url("https://tenant.goskope.com") == "https://tenant.goskope.com"

    def test_strips_http(self) -> None:
        assert _build_base_url("http://tenant.goskope.com") == "https://tenant.goskope.com"

    def test_strips_whitespace(self) -> None:
        assert _build_base_url("  tenant.goskope.com  ") == "https://tenant.goskope.com"
