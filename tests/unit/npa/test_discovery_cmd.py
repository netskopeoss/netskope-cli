"""Tests for NPA discovery settings commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestDiscoveryGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/discoverysettings").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"enabled": True, "auto_publish": False},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "discovery", "get"])
        assert result.exit_code == 0

    @respx.mock
    def test_get_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/steering/apps/private/discoverysettings").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"enabled": False}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["-o", "json", "npa", "discovery", "get"])
        assert result.exit_code == 0
