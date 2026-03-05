"""Tests for NPA apps commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestAppsListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "private_apps": [
                            {
                                "app_name": "test-app",
                                "app_id": 1,
                                "host": "test.local",
                                "clientless_access": False,
                                "use_publisher_dns": True,
                            }
                        ]
                    },
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "apps", "list"])
        assert result.exit_code == 0
        assert "test-app" in result.output

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(200, json={"data": {"private_apps": []}, "status": "success", "total": 0})
        )
        result = runner.invoke(app, ["-o", "json", "npa", "apps", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_count(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"private_apps": [{"app_name": "a", "app_id": 1}]},
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["-o", "json", "npa", "apps", "list", "--count"])
        assert result.exit_code == 0


class TestAppsGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"app_name": "my-app", "app_id": 42, "host": "internal.example.com"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "apps", "get", "42"])
        assert result.exit_code == 0
        assert "my-app" in result.output


class TestAppsDeleteCommand:
    @respx.mock
    def test_delete_with_yes_flag(self, runner):
        respx.delete(f"{BASE}/api/v2/steering/apps/private/1").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "apps", "delete", "1", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestAppsBulkDeleteCommand:
    @respx.mock
    def test_bulk_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "apps", "bulk-delete", "--ids", "1,2,3", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output


class TestAppsPolicyCheckCommand:
    @respx.mock
    def test_policy_check_success(self, runner):
        respx.post(f"{BASE}/api/v2/steering/apps/private/getpolicyinuse").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"app_id": 123, "policies": ["pol1"]}], "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "apps", "policy-check", "--ids", "123"])
        assert result.exit_code == 0
