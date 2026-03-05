"""Tests for NPA tags commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestTagsListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/tags").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"tags": [{"tag_id": 1, "tag_name": "web"}]},
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "tags", "list"])
        assert result.exit_code == 0
        assert "web" in result.output

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/tags").mock(
            return_value=httpx.Response(200, json={"data": {"tags": []}, "status": "success", "total": 0})
        )
        result = runner.invoke(app, ["-o", "json", "npa", "tags", "list"])
        assert result.exit_code == 0


class TestTagsGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/tags/42").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"tag_id": 42, "tag_name": "production"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "tags", "get", "42"])
        assert result.exit_code == 0
        assert "production" in result.output


class TestTagsCreateCommand:
    @respx.mock
    def test_create_success(self, runner):
        respx.post(f"{BASE}/api/v2/steering/apps/private/tags").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"tags": [{"tag_id": 10, "tag_name": "web"}]},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "tags", "create", "--app-id", "123", "--tags", "web"])
        assert result.exit_code == 0


class TestTagsDeleteCommand:
    @respx.mock
    def test_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/steering/apps/private/tags/42").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "tags", "delete", "42", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestTagsPolicyCheckCommand:
    @respx.mock
    def test_policy_check_success(self, runner):
        respx.post(f"{BASE}/api/v2/steering/apps/private/tags/getpolicyinuse").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"tag_id": 42, "policies": []}], "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "tags", "policy-check", "--ids", "42"])
        assert result.exit_code == 0
