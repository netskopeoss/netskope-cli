"""Tests for NPA policy rules and groups commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestRulesListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/policy/npa/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "rules": [
                            {
                                "rule_id": 1,
                                "rule_name": "Allow SSH",
                                "enabled": "1",
                                "group_name": "Default",
                                "action": "allow",
                            }
                        ]
                    },
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "policy", "rules", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/policy/npa/rules").mock(
            return_value=httpx.Response(200, json={"data": {"rules": []}, "status": "success", "total": 0})
        )
        result = runner.invoke(app, ["-o", "json", "npa", "policy", "rules", "list"])
        assert result.exit_code == 0


class TestRulesGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/policy/npa/rules/42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"rule_id": 42, "rule_name": "Allow Web", "enabled": "1"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "policy", "rules", "get", "42"])
        assert result.exit_code == 0


class TestRulesDeleteCommand:
    @respx.mock
    def test_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/policy/npa/rules/42").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "policy", "rules", "delete", "42", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestGroupsListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/policy/npa/policygroups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"policygroups": [{"group_id": 1, "group_name": "Default"}]},
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "policy", "groups", "list"])
        assert result.exit_code == 0


class TestGroupsGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/policy/npa/policygroups/5").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"group_id": 5, "group_name": "Engineering"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "policy", "groups", "get", "5"])
        assert result.exit_code == 0


class TestGroupsCreateCommand:
    @respx.mock
    def test_create_success(self, runner):
        respx.post(f"{BASE}/api/v2/policy/npa/policygroups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"group_id": 10, "group_name": "New Group"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "policy", "groups", "create", "--group-name", "New Group"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()
