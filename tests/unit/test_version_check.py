"""Tests for netskope_cli.core.version_check."""

from __future__ import annotations

import io
import json
import time
from unittest.mock import patch

import pytest

from netskope_cli.core.version_check import (
    _detect_install_method,
    _parse_version,
    _read_cache,
    _write_cache,
    maybe_show_update_notice,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    """Redirect the cache directory to a temp path."""
    monkeypatch.setattr("netskope_cli.core.version_check.cache_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def fresh_cache(cache_dir):
    """Write a fresh cache file indicating an update is available."""
    data = {"last_check": time.time(), "latest_version": "99.0.0"}
    (cache_dir / "version_check.json").write_text(json.dumps(data))
    return cache_dir


@pytest.fixture()
def stale_cache(cache_dir):
    """Write a stale cache file (older than 24h)."""
    data = {"last_check": time.time() - 100_000, "latest_version": "99.0.0"}
    (cache_dir / "version_check.json").write_text(json.dumps(data))
    return cache_dir


@pytest.fixture()
def console_and_output():
    """Create a console that writes to a StringIO for easy assertion."""
    from rich.console import Console

    buf = io.StringIO()
    console = Console(file=buf, no_color=True)
    return console, buf


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_two_part(self):
        assert _parse_version("1.0") == (1, 0)

    def test_comparison(self):
        assert _parse_version("0.3.0") > _parse_version("0.2.24")
        assert _parse_version("0.2.24") == _parse_version("0.2.24")
        assert _parse_version("0.2.24") < _parse_version("0.2.25")


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


class TestCacheIO:
    def test_read_missing(self, cache_dir):
        assert _read_cache() is None

    def test_write_and_read(self, cache_dir):
        _write_cache("1.2.3")
        cache = _read_cache()
        assert cache is not None
        assert cache["latest_version"] == "1.2.3"
        assert cache["last_check"] <= time.time()

    def test_corrupt_cache(self, cache_dir):
        (cache_dir / "version_check.json").write_text("not json")
        assert _read_cache() is None

    def test_incomplete_cache(self, cache_dir):
        (cache_dir / "version_check.json").write_text('{"last_check": 1}')
        assert _read_cache() is None


# ---------------------------------------------------------------------------
# Install method detection
# ---------------------------------------------------------------------------


class TestDetectInstallMethod:
    def test_pipx_path(self, monkeypatch):
        monkeypatch.setattr("sys.executable", "/home/user/.local/pipx/venvs/netskope/bin/python")
        # Ensure INSTALLER check doesn't interfere
        (
            monkeypatch.setattr(
                "netskope_cli.core.version_check.distribution",
                None,
            )
            if False
            else None
        )
        with patch("netskope_cli.core.version_check._detect_install_method") as _:
            pass
        # Just test the path heuristic by mocking the metadata lookup to fail
        with patch("importlib.metadata.distribution", side_effect=Exception):
            assert _detect_install_method() == "pipx upgrade netskope"

    def test_brew_path(self, monkeypatch):
        monkeypatch.setattr("sys.executable", "/opt/homebrew/Cellar/python@3.12/bin/python3")
        with patch("importlib.metadata.distribution", side_effect=Exception):
            assert _detect_install_method() == "brew upgrade netskope"

    def test_uv_path(self, monkeypatch):
        monkeypatch.setattr("sys.executable", "/home/user/.local/share/uv/tools/netskope/bin/python")
        with patch("importlib.metadata.distribution", side_effect=Exception):
            assert _detect_install_method() == "uv tool upgrade netskope"

    def test_pip_fallback(self, monkeypatch):
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        with patch("importlib.metadata.distribution", side_effect=Exception):
            assert _detect_install_method() == "pip install --upgrade netskope"

    def test_uv_installer_metadata(self, monkeypatch):
        """INSTALLER file containing 'uv' should be detected."""

        class FakeDist:
            def read_text(self, name):
                if name == "INSTALLER":
                    return "uv\n"
                return None

        with patch("importlib.metadata.distribution", return_value=FakeDist()):
            assert _detect_install_method() == "uv tool upgrade netskope"


# ---------------------------------------------------------------------------
# maybe_show_update_notice
# ---------------------------------------------------------------------------


class TestMaybeShowUpdateNotice:
    @pytest.fixture(autouse=True)
    def _fake_tty(self, monkeypatch):
        """Bypass the stderr TTY gate so tests can exercise the logic."""
        monkeypatch.setattr("netskope_cli.core.version_check._stderr_is_tty", lambda: True)

    def test_fresh_cache_shows_notice(self, fresh_cache, console_and_output):
        console, buf = console_and_output
        maybe_show_update_notice(console, "0.2.24", quiet=False)
        output = buf.getvalue()
        assert "99.0.0" in output
        assert "Update available" in output

    def test_current_version_no_notice(self, cache_dir, console_and_output):
        console, buf = console_and_output
        data = {"last_check": time.time(), "latest_version": "0.2.24"}
        (cache_dir / "version_check.json").write_text(json.dumps(data))
        maybe_show_update_notice(console, "0.2.24", quiet=False)
        assert buf.getvalue() == ""

    def test_newer_local_no_notice(self, cache_dir, console_and_output):
        console, buf = console_and_output
        data = {"last_check": time.time(), "latest_version": "0.2.24"}
        (cache_dir / "version_check.json").write_text(json.dumps(data))
        maybe_show_update_notice(console, "0.3.0", quiet=False)
        assert buf.getvalue() == ""

    def test_stale_cache_spawns_thread_no_notice(self, stale_cache, console_and_output):
        console, buf = console_and_output
        with patch("netskope_cli.core.version_check.threading.Thread") as mock_thread:
            maybe_show_update_notice(console, "0.2.24", quiet=False)
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()
        assert buf.getvalue() == ""

    def test_missing_cache_spawns_thread(self, cache_dir, console_and_output):
        console, buf = console_and_output
        with patch("netskope_cli.core.version_check.threading.Thread") as mock_thread:
            maybe_show_update_notice(console, "0.2.24", quiet=False)
            mock_thread.assert_called_once()

    def test_env_var_disables(self, fresh_cache, console_and_output, monkeypatch):
        console, buf = console_and_output
        monkeypatch.setenv("NETSKOPE_NO_UPDATE_CHECK", "1")
        maybe_show_update_notice(console, "0.2.24", quiet=False)
        assert buf.getvalue() == ""

    def test_env_var_true_disables(self, fresh_cache, console_and_output, monkeypatch):
        console, buf = console_and_output
        monkeypatch.setenv("NETSKOPE_NO_UPDATE_CHECK", "true")
        maybe_show_update_notice(console, "0.2.24", quiet=False)
        assert buf.getvalue() == ""

    def test_quiet_disables(self, fresh_cache, console_and_output):
        console, buf = console_and_output
        maybe_show_update_notice(console, "0.2.24", quiet=True)
        assert buf.getvalue() == ""

    def test_non_tty_disables(self, fresh_cache, console_and_output, monkeypatch):
        console, buf = console_and_output
        monkeypatch.setattr("netskope_cli.core.version_check._stderr_is_tty", lambda: False)
        maybe_show_update_notice(console, "0.2.24", quiet=False)
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Background fetch
# ---------------------------------------------------------------------------


class TestBackgroundFetch:
    def test_fetch_writes_cache(self, cache_dir):
        from netskope_cli.core.version_check import _fetch_latest_version

        fake_response = type(
            "Resp",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"info": {"version": "1.0.0"}},
            },
        )()

        with patch("httpx.get", return_value=fake_response):
            _fetch_latest_version()

        cache = _read_cache()
        assert cache is not None
        assert cache["latest_version"] == "1.0.0"

    def test_fetch_network_error_silent(self, cache_dir):
        from netskope_cli.core.version_check import _fetch_latest_version

        with patch("httpx.get", side_effect=ConnectionError("no network")):
            _fetch_latest_version()  # Should not raise

        assert _read_cache() is None

    def test_fetch_malformed_response(self, cache_dir):
        from netskope_cli.core.version_check import _fetch_latest_version

        fake_response = type(
            "Resp",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"unexpected": "data"},
            },
        )()

        with patch("httpx.get", return_value=fake_response):
            _fetch_latest_version()  # Should not raise

        assert _read_cache() is None
