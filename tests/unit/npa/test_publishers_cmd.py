"""Tests for NPA publishers commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestPublishersListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "publishers": [
                            {
                                "publisher_name": "pub1",
                                "publisher_id": 1,
                                "status": "connected",
                                "version": "100",
                                "apps_count": 5,
                            }
                        ]
                    },
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "list"])
        assert result.exit_code == 0
        assert "pub1" in result.output

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"publishers": []}, "status": "success", "total": 0},
            )
        )
        result = runner.invoke(app, ["-o", "json", "npa", "publishers", "list"])
        assert result.exit_code == 0


class TestPublishersGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"publisher_name": "pub-42", "publisher_id": 42, "status": "connected"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "get", "42"])
        assert result.exit_code == 0
        assert "pub-42" in result.output


class TestPublishersCreateCommand:
    @respx.mock
    def test_create_success(self, runner):
        respx.post(f"{BASE}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"publisher_name": "new-pub", "publisher_id": 99},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "create", "--name", "new-pub"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()


class TestPublishersDeleteCommand:
    @respx.mock
    def test_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/infrastructure/publishers/42").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "publishers", "delete", "42", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestPublishersAppsCommand:
    @respx.mock
    def test_apps_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/42/apps").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"app_name": "myapp", "app_id": 1, "host": "h.local", "protocol": "tcp"}],
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "apps", "42"])
        assert result.exit_code == 0


class TestPublishersRegistrationTokenCommand:
    @respx.mock
    def test_registration_token_success(self, runner):
        respx.post(f"{BASE}/api/v2/infrastructure/publishers/42/registration_token").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"token": "abc123"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "registration-token", "42"])
        assert result.exit_code == 0
        assert "generated" in result.output.lower() or "token" in result.output.lower()


class TestPublishersReleasesCommand:
    @respx.mock
    def test_releases_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/releases").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"version": "100", "docker_tag": "v100", "release_type": "Latest", "is_recommended": True}
                    ],
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "releases"])
        assert result.exit_code == 0


class TestPublishersUpgradeCommand:
    @respx.mock
    def test_upgrade_with_yes(self, runner):
        respx.put(f"{BASE}/api/v2/infrastructure/publishers/bulk").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "publishers", "upgrade", "--publisher-ids", "1,2", "--yes"])
        assert result.exit_code == 0
        assert "upgrade" in result.output.lower() or "triggered" in result.output.lower()
