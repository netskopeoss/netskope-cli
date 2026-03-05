"""Tests for NPA local brokers commands."""

from __future__ import annotations

import httpx
import respx

from netskope_cli.main import app

BASE = "https://test.goskope.com"


class TestLocalBrokersListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/lbrokers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "lbrokers": [{"id": 1, "name": "broker-1", "common_name": "broker-1.local", "registered": True}]
                    },
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/lbrokers").mock(
            return_value=httpx.Response(200, json={"data": {"lbrokers": []}, "status": "success", "total": 0})
        )
        result = runner.invoke(app, ["-o", "json", "npa", "publishers", "local-brokers", "list"])
        assert result.exit_code == 0


class TestLocalBrokersGetCommand:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/lbrokers/10").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"id": 10, "name": "broker-10", "common_name": "b10.local"},
                    "status": "success",
                },
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "get", "10"])
        assert result.exit_code == 0


class TestLocalBrokersCreateCommand:
    @respx.mock
    def test_create_success(self, runner):
        respx.post(f"{BASE}/api/v2/infrastructure/lbrokers").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": 20, "name": "new-broker"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "create", "--name", "new-broker"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()


class TestLocalBrokersDeleteCommand:
    @respx.mock
    def test_delete_with_yes(self, runner):
        respx.delete(f"{BASE}/api/v2/infrastructure/lbrokers/10").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "delete", "10", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestLocalBrokersConfigGetCommand:
    @respx.mock
    def test_config_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/infrastructure/lbrokers/brokerconfig").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"hostname": "broker.example.com"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "config-get"])
        assert result.exit_code == 0


class TestLocalBrokersRegistrationTokenCommand:
    @respx.mock
    def test_registration_token_success(self, runner):
        respx.post(f"{BASE}/api/v2/infrastructure/lbrokers/10/registrationtoken").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"token": "reg-token-xyz"}, "status": "success"},
            )
        )
        result = runner.invoke(app, ["npa", "publishers", "local-brokers", "registration-token", "10"])
        assert result.exit_code == 0
        assert "generated" in result.output.lower() or "token" in result.output.lower()
