"""Integration tests for the Netskope CLI.

Exercises the CLI end-to-end through typer.testing.CliRunner, verifying
command output, exit codes, and side-effects (config files on disk).
HTTP calls are mocked at the NetskopeClient.request boundary so no real
network traffic is generated.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from netskope_cli.main import __version__, app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect all config / data directories to a temporary directory.

    This patches both the XDG-based paths used by ``core.config`` and the
    hardcoded ``_CONFIG_DIR`` / ``_CONFIG_FILE`` used by ``config_cmd``.
    """
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    cache_home = tmp_path / "cache"

    config_home.mkdir()
    data_home.mkdir()
    cache_home.mkdir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    # Also patch config_cmd module-level constants so they use tmp_path
    ns_config_dir = config_home / "netskope"
    ns_config_file = ns_config_dir / "config.toml"
    monkeypatch.setattr("netskope_cli.commands.config_cmd._CONFIG_DIR", ns_config_dir)
    monkeypatch.setattr("netskope_cli.commands.config_cmd._CONFIG_FILE", ns_config_file)

    # Clear any env vars that might interfere with config resolution
    for var in (
        "NETSKOPE_TENANT",
        "NETSKOPE_API_TOKEN",
        "NETSKOPE_PROFILE",
        "NETSKOPE_OUTPUT_FORMAT",
        "NETSKOPE_NO_COLOR",
        "NO_COLOR",
    ):
        monkeypatch.delenv(var, raising=False)


# ===================================================================
# 1. CLI basics
# ===================================================================


class TestCLIBasics:
    """Verify top-level CLI behaviour: version, help, subcommand listing."""

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert f"netskope-cli {__version__}" in result.stdout

    def test_help_lists_command_groups(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # The help text must mention at least the always-available groups
        assert "config" in result.stdout
        assert "auth" in result.stdout

    def test_config_help_lists_subcommands(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        for sub in ("create-profile", "profiles", "use-profile", "show", "set-tenant", "set-token"):
            assert sub in result.stdout

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # Typer's no_args_is_help may return exit code 0 or 2 depending on version
        combined = result.stdout + result.stderr
        assert "config" in combined


# ===================================================================
# 2. Config commands
# ===================================================================


class TestConfigCommands:
    """Test the config subcommand group for profile and tenant management."""

    def test_create_profile(self):
        result = runner.invoke(
            app,
            ["config", "create-profile", "test", "--tenant", "test.goskope.com"],
        )
        assert result.exit_code == 0
        # Output goes to stderr via Rich console
        assert "test" in result.stderr or "test" in result.stdout

    def test_profiles_lists_created_profile(self):
        # Create a profile first
        runner.invoke(
            app,
            ["config", "create-profile", "myprof", "--tenant", "my.goskope.com"],
        )
        result = runner.invoke(app, ["config", "profiles"])
        assert result.exit_code == 0
        # The profile name should appear somewhere in the output
        combined = result.stdout + result.stderr
        assert "myprof" in combined

    def test_use_profile_switches_active(self):
        # Create two profiles
        runner.invoke(
            app,
            ["config", "create-profile", "alpha", "--tenant", "alpha.goskope.com"],
        )
        runner.invoke(
            app,
            ["config", "create-profile", "beta", "--tenant", "beta.goskope.com"],
        )
        result = runner.invoke(app, ["config", "use-profile", "beta"])
        assert result.exit_code == 0
        combined = result.stdout + result.stderr
        assert "beta" in combined

    def test_use_profile_nonexistent_fails(self):
        result = runner.invoke(app, ["config", "use-profile", "nope"])
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "nope" in combined

    def test_show_displays_config(self):
        # Create a profile so there is something to show
        runner.invoke(
            app,
            ["config", "create-profile", "showme", "--tenant", "show.goskope.com"],
        )
        result = runner.invoke(app, ["--profile", "showme", "config", "show"])
        assert result.exit_code == 0
        combined = result.stdout + result.stderr
        assert "showme" in combined
        assert "show.goskope.com" in combined

    def test_set_tenant_updates_tenant(self):
        runner.invoke(
            app,
            ["config", "create-profile", "ten", "--tenant", "old.goskope.com"],
        )
        result = runner.invoke(
            app,
            ["--profile", "ten", "config", "set-tenant", "new.goskope.com"],
        )
        assert result.exit_code == 0
        combined = result.stdout + result.stderr
        assert "new.goskope.com" in combined

    def test_create_duplicate_profile_fails(self):
        runner.invoke(
            app,
            ["config", "create-profile", "dup", "--tenant", "dup.goskope.com"],
        )
        result = runner.invoke(
            app,
            ["config", "create-profile", "dup", "--tenant", "dup2.goskope.com"],
        )
        assert result.exit_code == 1
        combined = result.stdout + result.stderr
        assert "already exists" in combined

    def test_profiles_empty_shows_hint(self):
        result = runner.invoke(app, ["config", "profiles"])
        assert result.exit_code == 0
        combined = result.stdout + result.stderr
        assert "No profiles configured" in combined or "create-profile" in combined


# ===================================================================
# 3. Auth commands
# ===================================================================


class TestAuthCommands:
    """Test auth subcommands for status and logout."""

    def test_auth_status_no_credentials(self):
        """auth status should succeed and indicate no credentials are set."""
        # Patch the session cookie lookup and keyring so they return None
        with (
            patch("netskope_cli.commands.auth_cmd._get_token", return_value=None),
            patch("netskope_cli.core.config.get_session_cookie", return_value=None),
        ):
            result = runner.invoke(app, ["auth", "status"])
            assert result.exit_code == 0
            combined = result.stdout + result.stderr
            assert "not" in combined.lower() or "status" in combined.lower()

    def test_auth_logout_no_credentials(self):
        """auth logout with no stored credentials should exit cleanly."""
        with (
            patch("netskope_cli.commands.auth_cmd._get_token", return_value=None),
            patch("netskope_cli.commands.auth_cmd._delete_token"),
            patch("netskope_cli.core.config.delete_session_cookie", return_value=False),
        ):
            result = runner.invoke(app, ["auth", "logout"])
            assert result.exit_code == 0
            combined = result.stdout + result.stderr
            assert "no credentials" in combined.lower() or "removed" in combined.lower()

    def test_auth_help(self):
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "login" in result.stdout
        assert "logout" in result.stdout
        assert "status" in result.stdout
        assert "token" in result.stdout


# ===================================================================
# 4. Events commands with mocked HTTP
# ===================================================================


class TestEventsCommands:
    """Test events subcommands with HTTP calls mocked at NetskopeClient.request."""

    @pytest.fixture(autouse=True)
    def _setup_config_with_token(self, tmp_path: Path):
        """Write a valid config and patch token retrieval so _build_client works."""
        # Set env vars that core.config will pick up
        import os

        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        ns_dir = Path(xdg_config) / "netskope"
        ns_dir.mkdir(parents=True, exist_ok=True)
        config_file = ns_dir / "config.toml"
        config_file.write_text(
            "[profiles.default]\n"
            'tenant = "test.goskope.com"\n'
            'api_token = "fake-token-for-testing"\n'
            'auth_type = "token"\n'
            "\n"
            'active_profile = "default"\n'
        )

    def test_events_alerts_with_mock(self):
        """Invoke `events alerts` and verify the mocked API data is rendered."""
        mock_response = {
            "ok": True,
            "result": [
                {
                    "alert_id": "A001",
                    "alert_type": "DLP",
                    "severity": "high",
                    "timestamp": 1700000000,
                },
                {
                    "alert_id": "A002",
                    "alert_type": "DLP",
                    "severity": "medium",
                    "timestamp": 1700000100,
                },
            ],
            "total": 2,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "events",
                    "alerts",
                    "--query",
                    "alert_type eq DLP",
                    "--limit",
                    "5",
                ],
            )
            assert result.exit_code == 0

            # The mock should have been called with the right endpoint
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/api/v2/events/datasearch/alert"
            assert call_args[1]["params"]["query"] == "alert_type eq DLP"
            assert call_args[1]["params"]["limit"] == 5

            # stdout should contain the JSON-rendered data
            assert "A001" in result.stdout
            assert "DLP" in result.stdout

    def test_events_application_with_mock(self):
        """Invoke `events application` and verify correct endpoint is used."""
        mock_response = {
            "ok": True,
            "result": [{"app_name": "Slack", "action": "allow"}],
            "total": 1,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                ["--output", "json", "--quiet", "events", "application", "--limit", "10"],
            )
            assert result.exit_code == 0
            mock_req.assert_called_once()
            assert mock_req.call_args[0][1] == "/api/v2/events/datasearch/application"
            assert "Slack" in result.stdout

    def test_events_network_with_mock(self):
        mock_response = {
            "ok": True,
            "result": [{"src_ip": "10.0.0.1", "dst_ip": "8.8.8.8"}],
            "total": 1,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                ["--output", "json", "--quiet", "events", "network"],
            )
            assert result.exit_code == 0
            assert mock_req.call_args[0][1] == "/api/v2/events/datasearch/network"
            assert "10.0.0.1" in result.stdout

    def test_events_alerts_json_output_format(self):
        """Verify --output json produces parseable JSON."""
        import json

        mock_response = {
            "ok": True,
            "result": [{"id": "X1", "type": "malware"}],
            "total": 1,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ):
            result = runner.invoke(
                app,
                ["--output", "json", "--quiet", "events", "alerts"],
            )
            assert result.exit_code == 0
            # The output should be valid JSON containing our mock result
            parsed = json.loads(result.stdout)
            assert isinstance(parsed, list)
            assert parsed[0]["id"] == "X1"

    def test_events_alerts_with_fields_selection(self):
        """Verify --fields filters the output columns."""
        import json

        mock_response = {
            "ok": True,
            "result": [
                {"alert_id": "F1", "severity": "high", "extra": "data"},
            ],
            "total": 1,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "--quiet",
                    "events",
                    "alerts",
                    "--fields",
                    "alert_id,severity",
                ],
            )
            assert result.exit_code == 0
            # Check the fields param was passed to the API
            assert "alert_id,severity" in mock_req.call_args[1]["params"]["fields"]

            # The rendered output should have field-selected data
            parsed = json.loads(result.stdout)
            assert isinstance(parsed, list)
            assert "alert_id" in parsed[0]
            assert "severity" in parsed[0]
            # "extra" should be filtered out by field selection
            assert "extra" not in parsed[0]

    def test_events_help(self):
        result = runner.invoke(app, ["events", "--help"])
        assert result.exit_code == 0
        for sub in ("alerts", "application", "network", "page", "audit"):
            assert sub in result.stdout


# ===================================================================
# 5. Error handling
# ===================================================================


class TestErrorHandling:
    """Verify the CLI produces clean error output for common failure modes."""

    def test_events_without_credentials_shows_error(self):
        """Running events without any credentials should produce an error."""
        # With no config file and no env vars, _build_client should raise
        result = runner.invoke(
            app,
            ["--quiet", "events", "alerts"],
        )
        # Should fail because there's no tenant or token configured
        assert result.exit_code != 0

    def test_invalid_subcommand_shows_error(self):
        result = runner.invoke(app, ["config", "nonexistent-cmd"])
        assert result.exit_code != 0

    def test_events_alerts_api_error(self):
        """When the API returns ok=false, the CLI should raise an error."""
        import os

        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        ns_dir = Path(xdg_config) / "netskope"
        ns_dir.mkdir(parents=True, exist_ok=True)
        config_file = ns_dir / "config.toml"
        config_file.write_text(
            "[profiles.default]\n"
            'tenant = "test.goskope.com"\n'
            'api_token = "fake-token"\n'
            'auth_type = "token"\n'
            "\n"
            'active_profile = "default"\n'
        )

        mock_response = {
            "ok": False,
            "message": "Invalid query syntax",
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ):
            result = runner.invoke(
                app,
                ["--output", "json", "--quiet", "events", "alerts", "--query", "bad query"],
            )
            # The NetskopeError should propagate as a non-zero exit
            assert result.exit_code != 0

    def test_auth_token_without_token_raises(self):
        """auth token command when no token is stored should exit non-zero."""
        with patch("netskope_cli.commands.auth_cmd._get_token", return_value=None):
            result = runner.invoke(app, ["auth", "token"])
            # AuthError is raised which becomes non-zero exit
            assert result.exit_code != 0

    def test_missing_required_argument(self):
        """Commands with required arguments should fail when arg is missing."""
        result = runner.invoke(app, ["config", "set-tenant"])
        assert result.exit_code != 0


# ===================================================================
# 6. Policy commands (with mocked HTTP)
# ===================================================================


class TestPolicyCommands:
    """Test policy subcommands with HTTP calls mocked."""

    @pytest.fixture(autouse=True)
    def _setup_config_with_token(self):
        import os

        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        ns_dir = Path(xdg_config) / "netskope"
        ns_dir.mkdir(parents=True, exist_ok=True)
        config_file = ns_dir / "config.toml"
        config_file.write_text(
            "[profiles.default]\n"
            'tenant = "test.goskope.com"\n'
            'api_token = "fake-token-for-testing"\n'
            'auth_type = "token"\n'
            "\n"
            'active_profile = "default"\n'
        )

    def test_policy_help(self):
        result = runner.invoke(app, ["policy", "--help"])
        assert result.exit_code == 0
        assert "url-list" in result.stdout
        assert "deploy" in result.stdout

    def test_policy_url_list_list(self):
        mock_response = [
            {"id": 1, "name": "blocklist", "type": "exact"},
            {"id": 2, "name": "allowlist", "type": "exact"},
        ]

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                ["--output", "json", "policy", "url-list", "list"],
            )
            assert result.exit_code == 0
            mock_req.assert_called_once()
            assert mock_req.call_args[0][0] == "GET"
            assert mock_req.call_args[0][1] == "/api/v2/policy/urllist"
            assert "blocklist" in result.stdout

    def test_policy_url_list_create(self):
        mock_response = {"id": 99, "name": "newlist", "urls": ["evil.com"]}

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "policy",
                    "url-list",
                    "create",
                    "newlist",
                    "--urls",
                    "evil.com,bad.com",
                ],
            )
            assert result.exit_code == 0
            mock_req.assert_called_once()
            assert mock_req.call_args[0][0] == "POST"
            assert mock_req.call_args[0][1] == "/api/v2/policy/urllist"
            # Verify the body was constructed correctly
            body = mock_req.call_args[1]["json_data"]
            assert body["data"]["name"] == "newlist"
            assert "evil.com" in body["data"]["urls"]
            assert "bad.com" in body["data"]["urls"]


# ===================================================================
# 7. Users commands (with mocked HTTP)
# ===================================================================


class TestUsersCommands:
    """Test users subcommands with HTTP calls mocked."""

    @pytest.fixture(autouse=True)
    def _setup_config_with_token(self):
        import os

        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        ns_dir = Path(xdg_config) / "netskope"
        ns_dir.mkdir(parents=True, exist_ok=True)
        config_file = ns_dir / "config.toml"
        config_file.write_text(
            "[profiles.default]\n"
            'tenant = "test.goskope.com"\n'
            'api_token = "fake-token-for-testing"\n'
            'auth_type = "token"\n'
            "\n"
            'active_profile = "default"\n'
        )

    def test_users_help(self):
        result = runner.invoke(app, ["users", "--help"])
        assert result.exit_code == 0
        for sub in ("list", "get", "create", "update", "delete", "groups"):
            assert sub in result.stdout

    def test_users_list(self):
        mock_response = {
            "totalResults": 1,
            "Resources": [{"id": "u1", "userName": "alice@example.com", "active": True}],
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                ["--output", "json", "users", "list"],
            )
            assert result.exit_code == 0
            mock_req.assert_called_once()
            assert mock_req.call_args[0][0] == "GET"
            assert mock_req.call_args[0][1] == "/api/v2/scim/Users"
            assert "alice@example.com" in result.stdout

    def test_users_get(self):
        mock_response = {
            "id": "u42",
            "userName": "bob@example.com",
            "active": True,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ):
            result = runner.invoke(
                app,
                ["--output", "json", "users", "get", "u42"],
            )
            assert result.exit_code == 0
            assert "bob@example.com" in result.stdout

    def test_users_create(self):
        mock_response = {
            "id": "u100",
            "userName": "new@example.com",
            "active": True,
        }

        with patch.object(
            __import__("netskope_cli.core.client", fromlist=["NetskopeClient"]).NetskopeClient,
            "request",
            return_value=mock_response,
        ) as mock_req:
            result = runner.invoke(
                app,
                [
                    "--output",
                    "json",
                    "users",
                    "create",
                    "--username",
                    "new@example.com",
                    "--email",
                    "new@example.com",
                ],
            )
            assert result.exit_code == 0
            mock_req.assert_called_once()
            body = mock_req.call_args[1]["json_data"]
            assert body["userName"] == "new@example.com"
            assert body["emails"][0]["value"] == "new@example.com"
