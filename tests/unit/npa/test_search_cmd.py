"""Tests for NPA search and validate-name commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestValidateNameCommand:
    @respx.mock
    def test_validate_name_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/npa/namevalidation").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"valid": True, "message": "Name is available"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "validate-name", "--resource-type", "publisher", "--name", "My Publisher"])
        assert result.exit_code == 0

    @respx.mock
    def test_validate_name_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/npa/namevalidation").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"valid": False, "message": "Name already in use"}, "status": "success"},
            )
        )
        result = runner.invoke(
            app, ["-o", "json", "npa", "validate-name", "--resource-type", "private_app", "--name", "dup"]
        )
        assert result.exit_code == 0

    def test_validate_name_invalid_resource_type(self, runner):
        result = runner.invoke(app, ["npa", "validate-name", "--resource-type", "bogus", "--name", "test"])
        assert result.exit_code != 0


class TestSearchCommand:
    @respx.mock
    def test_search_publishers_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/npa/search/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"publisher_name": "prod-pub", "publisher_id": 1}],
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "search", "publishers", "--query", "prod"])
        assert result.exit_code == 0

    @respx.mock
    def test_search_private_apps_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/npa/search/private_apps").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"app_name": "ssh-server", "app_id": 10}],
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "search", "private_apps", "--query", "ssh"])
        assert result.exit_code == 0

    def test_search_invalid_resource_type(self, runner):
        result = runner.invoke(app, ["npa", "search", "bogus_type", "--query", "test"])
        assert result.exit_code != 0
