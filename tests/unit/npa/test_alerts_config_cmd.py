"""Tests for NPA alerts config commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestAlertsConfigGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/alertsconfiguration").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "adminUsers": ["admin@example.com"],
                        "eventTypes": ["UPGRADE_FAILED", "CONNECTION_FAILED"],
                    },
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "alerts-config", "get"])
        assert result.exit_code == 0

    @respx.mock
    def test_get_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/alertsconfiguration").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"adminUsers": [], "eventTypes": []}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["-o", "json", "npa", "alerts-config", "get"])
        assert result.exit_code == 0
