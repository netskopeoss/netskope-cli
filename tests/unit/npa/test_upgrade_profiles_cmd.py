"""Tests for NPA upgrade profiles commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestUpgradeProfilesListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publisherupgradeprofiles").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "name": "Weekly Beta",
                            "enabled": True,
                            "frequency": "0 2 * * 0",
                            "timezone": "UTC",
                            "release_type": "Beta",
                        }
                    ],
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "upgrade-profiles", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publisherupgradeprofiles").mock(
            return_value=httpx.Response(200, json={"data": [], "status": "success"})
        )
        result = runner.invoke(app, ["-o", "json", "npa", "publishers", "upgrade-profiles", "list"])
        assert result.exit_code == 0


class TestUpgradeProfilesGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publisherupgradeprofiles/5").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"id": 5, "name": "Nightly", "enabled": True},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "upgrade-profiles", "get", "5"])
        assert result.exit_code == 0


class TestUpgradeProfilesDeleteCommand:
    @respx.mock
    def test_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/infrastructure/publisherupgradeprofiles/5").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "publishers", "upgrade-profiles", "delete", "5", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestUpgradeProfilesAssignCommand:
    @respx.mock
    def test_assign_success(self, runner):
        respx.put(f"{BASE}/api/v2/infrastructure/publisherupgradeprofiles/bulk").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(
            app,
            ["npa", "publishers", "upgrade-profiles", "assign", "--profile-id", "5", "--publisher-ids", "1,2,3"],
        )
        assert result.exit_code == 0
        assert "assigned" in result.output.lower()
