"""Tests for NPA app-publishers commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestAppPublishersAddCommand:
    @respx.mock
    def test_add_success(self, runner):
        respx.patch(f"{BASE}/api/v2/steering/apps/private/publishers").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"updated": True}, "status": "success"},
            )
        )
        result = runner.invoke(
            app, ["npa", "app-publishers", "add", "--app-ids", "123,456", "--publisher-ids", "10,20"]
        )
        assert result.exit_code == 0

    @respx.mock
    def test_add_json_output(self, runner):
        respx.patch(f"{BASE}/api/v2/steering/apps/private/publishers").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(
            app,
            ["-o", "json", "npa", "app-publishers", "add", "--app-ids", "1", "--publisher-ids", "2"],
        )
        assert result.exit_code == 0


class TestAppPublishersRemoveCommand:
    @respx.mock
    def test_remove_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/steering/apps/private/publishers").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(
            app,
            ["npa", "app-publishers", "remove", "--app-ids", "123", "--publisher-ids", "10", "--yes"],
        )
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    @respx.mock
    def test_remove_json_output(self, runner):
        respx.delete(f"{BASE}/api/v2/steering/apps/private/publishers").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(
            app,
            ["-o", "json", "npa", "app-publishers", "remove", "--app-ids", "1", "--publisher-ids", "2", "--yes"],
        )
        assert result.exit_code == 0
