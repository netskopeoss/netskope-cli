"""Tests for netskope_cli.commands.status_cmd."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from netskope_cli.commands.status_cmd import (
    EventCount,
    _fetch_event_count,
    _fetch_publishers,
    _fetch_resource_total,
    _gather_status,
)

BASE_URL = "https://tenant.goskope.com"
HEADERS = {"Accept": "application/json", "Netskope-Api-Token": "testtoken"}


# ---------------------------------------------------------------------------
# _fetch_event_count
# ---------------------------------------------------------------------------


class TestFetchEventCount:
    @pytest.mark.asyncio
    async def test_returns_count_from_status(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": [{"id": 1}],
                    "status": {"count": 42, "execution": "SUCCESS", "status_code": 200},
                },
            )
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(42, False)

    @pytest.mark.asyncio
    async def test_falls_back_to_result_length(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(200, json={"result": [{"id": 1}, {"id": 2}, {"id": 3}]})
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(3, False)

    @pytest.mark.asyncio
    async def test_full_page_is_flagged_capped(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(200, json={"result": [{"id": i} for i in range(100)]})
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(100, True)

    @pytest.mark.asyncio
    async def test_full_page_with_status_count_equal_to_rows_is_capped(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(200, json={"result": [{"id": i} for i in range(100)], "status": {"count": 100}})
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(100, True)

    @pytest.mark.asyncio
    async def test_full_page_with_larger_status_count_is_a_lower_bound(self, respx_mock):
        """Same rule as ``--count``: only total/totalResults/status.total are exact."""
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(
                200, json={"result": [{"id": i} for i in range(100)], "status": {"count": 5000}}
            )
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(5000, True)

    @pytest.mark.asyncio
    async def test_full_page_with_a_stated_total_is_exact(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(
                200, json={"result": [{"id": i} for i in range(100)], "status": {"count": 100, "total": 5000}}
            )
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(5000, False)

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(None, False)

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(side_effect=httpx.ConnectError("fail"))
        count = await _fetch_event_count(BASE_URL, HEADERS, "/api/v2/events/datasearch/alert", {"limit": 100})
        assert count == EventCount(None, False)


# ---------------------------------------------------------------------------
# _fetch_resource_total
# ---------------------------------------------------------------------------


class TestFetchResourceTotal:
    @pytest.mark.asyncio
    async def test_returns_total_field(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(200, json={"data": {"private_apps": []}, "status": "success", "total": 40})
        )
        total = await _fetch_resource_total(
            BASE_URL, HEADERS, "/api/v2/steering/apps/private", {"limit": 1, "offset": 0}
        )
        assert total == 40

    @pytest.mark.asyncio
    async def test_returns_total_results_for_scim(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/scim/Users").mock(
            return_value=httpx.Response(
                200,
                json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": 9456},
            )
        )
        total = await _fetch_resource_total(BASE_URL, HEADERS, "/api/v2/scim/Users", {"count": 1})
        assert total == 9456

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )
        total = await _fetch_resource_total(
            BASE_URL, HEADERS, "/api/v2/steering/apps/private", {"limit": 1, "offset": 0}
        )
        assert total is None


# ---------------------------------------------------------------------------
# _fetch_publishers
# ---------------------------------------------------------------------------


class TestFetchPublishers:
    @pytest.mark.asyncio
    async def test_returns_publisher_breakdown(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "publishers": [
                            {"publisher_name": "pub1", "status": "connected"},
                            {"publisher_name": "pub2", "status": "connected"},
                            {"publisher_name": "pub3", "status": "not_connected"},
                        ]
                    },
                    "status": "success",
                    "total": 3,
                },
            )
        )
        result = await _fetch_publishers(BASE_URL, HEADERS)
        assert result["total"] == 3
        assert result["connected"] == 2
        assert result["not_connected"] == 1

    @pytest.mark.asyncio
    async def test_all_connected(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"publishers": [{"publisher_name": "pub1", "status": "connected"}]},
                    "status": "success",
                    "total": 1,
                },
            )
        )
        result = await _fetch_publishers(BASE_URL, HEADERS)
        assert result["total"] == 1
        assert result["connected"] == 1
        assert result["not_connected"] == 0

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, respx_mock):
        respx_mock.get(f"{BASE_URL}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(500, json={"error": "fail"})
        )
        result = await _fetch_publishers(BASE_URL, HEADERS)
        assert result["total"] is None


# ---------------------------------------------------------------------------
# _gather_status
# ---------------------------------------------------------------------------


class TestGatherStatus:
    @pytest.mark.asyncio
    async def test_gathers_all_metrics(self, respx_mock):
        time_params = {"starttime": 1000, "endtime": 2000}

        # Mock event endpoints
        for etype in ["alert", "application", "network", "page", "incident"]:
            respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/{etype}").mock(
                return_value=httpx.Response(
                    200,
                    json={"result": [{"id": 1}], "status": {"count": 10, "execution": "SUCCESS", "status_code": 200}},
                )
            )

        # Publishers
        respx_mock.get(f"{BASE_URL}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"publishers": [{"publisher_name": "p1", "status": "connected"}]},
                    "status": "success",
                    "total": 1,
                },
            )
        )

        # Private apps
        respx_mock.get(f"{BASE_URL}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(200, json={"data": {"private_apps": []}, "status": "success", "total": 5})
        )

        # SCIM users
        respx_mock.get(f"{BASE_URL}/api/v2/scim/Users").mock(
            return_value=httpx.Response(200, json={"totalResults": 100})
        )

        metrics, errors = await _gather_status(BASE_URL, HEADERS, time_params)

        assert metrics["alert_events_24h"] == 10
        assert metrics["alert_events_capped"] is False
        assert metrics["application_events_24h"] == 10
        assert metrics["network_events_24h"] == 10
        assert metrics["page_events_24h"] == 10
        assert metrics["incident_events_24h"] == 10
        assert metrics["publishers"]["total"] == 1
        assert metrics["publishers"]["connected"] == 1
        assert metrics["private_apps"] == 5
        assert metrics["users"] == 100
        assert errors == []

    @pytest.mark.asyncio
    async def test_handles_partial_failures(self, respx_mock):
        time_params = {"starttime": 1000, "endtime": 2000}

        # Some succeed, some fail
        respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(
                200, json={"result": [], "status": {"count": 0, "execution": "SUCCESS", "status_code": 200}}
            )
        )
        for etype in ["application", "network", "page", "incident"]:
            respx_mock.get(f"{BASE_URL}/api/v2/events/datasearch/{etype}").mock(
                return_value=httpx.Response(500, json={"error": "fail"})
            )
        respx_mock.get(f"{BASE_URL}/api/v2/infrastructure/publishers").mock(
            return_value=httpx.Response(500, json={"error": "fail"})
        )
        respx_mock.get(f"{BASE_URL}/api/v2/steering/apps/private").mock(
            return_value=httpx.Response(200, json={"total": 3, "data": {"private_apps": []}})
        )
        respx_mock.get(f"{BASE_URL}/api/v2/scim/Users").mock(return_value=httpx.Response(500, json={"error": "fail"}))

        metrics, errors = await _gather_status(BASE_URL, HEADERS, time_params)

        assert metrics["alert_events_24h"] == 0
        assert metrics["application_events_24h"] is None
        assert metrics["application_events_capped"] is False
        assert metrics["publishers"]["total"] is None
        assert metrics["private_apps"] == 3
        assert metrics["users"] is None
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# CLI integration (via Typer runner)
# ---------------------------------------------------------------------------


class TestStatusCLI:
    """Test the status command through the Typer CLI runner."""

    def test_status_table_output(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from netskope_cli.main import app

        runner = CliRunner()

        monkeypatch.setenv("NETSKOPE_TENANT", "https://test.goskope.com")
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken")
        # Isolate config
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

        async def mock_gather(base_url, headers, time_params, cookies=None, extended=False):
            return (
                {
                    "alert_events_24h": 100,
                    "application_events_24h": 200,
                    "network_events_24h": 300,
                    "page_events_24h": 50,
                    "incident_events_24h": 5,
                    "publishers": {"total": 3, "connected": 2, "not_connected": 1},
                    "private_apps": 10,
                    "users": 500,
                },
                [],
            )

        with patch("netskope_cli.commands.status_cmd._gather_status", side_effect=mock_gather):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Tenant Status" in result.output
        assert "Publishers" in result.output
        assert "Private Apps" in result.output
        assert "Users" in result.output
        assert "Alerts" in result.output

    def test_status_json_output(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from netskope_cli.main import app

        runner = CliRunner()

        monkeypatch.setenv("NETSKOPE_TENANT", "https://test.goskope.com")
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

        async def mock_gather(base_url, headers, time_params, cookies=None, extended=False):
            return (
                {
                    "alert_events_24h": 100,
                    "application_events_24h": 200,
                    "network_events_24h": 300,
                    "page_events_24h": 50,
                    "incident_events_24h": 5,
                    "publishers": {"total": 3, "connected": 2, "not_connected": 1},
                    "private_apps": 10,
                    "users": 500,
                },
                [],
            )

        with patch("netskope_cli.commands.status_cmd._gather_status", side_effect=mock_gather):
            result = runner.invoke(app, ["-o", "json", "status"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["tenant"] == "https://test.goskope.com"
        assert data["infrastructure"]["publishers"]["total"] == 3
        assert data["infrastructure"]["publishers"]["connected"] == 2
        assert data["infrastructure"]["publishers"]["not_connected"] == 1
        assert data["infrastructure"]["private_apps"] == 10
        assert data["infrastructure"]["users_scim"] == 500
        assert data["events"]["alerts"] == 100
        assert data["events"]["incidents"] == 5

    def test_status_custom_period(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from netskope_cli.main import app

        runner = CliRunner()

        monkeypatch.setenv("NETSKOPE_TENANT", "https://test.goskope.com")
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

        async def mock_gather(base_url, headers, time_params, cookies=None, extended=False):
            return (
                {
                    "alert_events_24h": 10,
                    "application_events_24h": 20,
                    "network_events_24h": 30,
                    "page_events_24h": 5,
                    "incident_events_24h": 1,
                    "publishers": {"total": 1, "connected": 1, "not_connected": 0},
                    "private_apps": 2,
                    "users": 50,
                },
                [],
            )

        with patch("netskope_cli.commands.status_cmd._gather_status", side_effect=mock_gather):
            result = runner.invoke(app, ["-o", "json", "status", "--period", "7d"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["period"] == "7d"


class TestStatusCapped:
    """A count that hit the datasearch page cap is rendered as a lower bound."""

    @staticmethod
    def _metrics(capped: bool) -> dict:
        return {
            "alert_events_24h": 10000,
            "alert_events_capped": capped,
            "application_events_24h": 200,
            "network_events_24h": 300,
            "page_events_24h": 50,
            "incident_events_24h": 5,
            "publishers": {"total": 3, "connected": 2, "not_connected": 1},
            "private_apps": 10,
            "users": 500,
        }

    def _run(self, tmp_path, monkeypatch, capped: bool, *argv: str):
        from typer.testing import CliRunner

        from netskope_cli.main import app

        monkeypatch.setenv("NETSKOPE_TENANT", "https://test.goskope.com")
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

        async def mock_gather(base_url, headers, time_params, cookies=None, extended=False):
            return self._metrics(capped), []

        with patch("netskope_cli.commands.status_cmd._gather_status", side_effect=mock_gather):
            return CliRunner().invoke(app, list(argv))

    def test_json_reports_capped_flags(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch, True, "-o", "json", "status")
        assert result.exit_code == 0, result.output
        events = json.loads(result.output)["events"]
        assert events["alerts"] == 10000 and events["alerts_capped"] is True
        assert events["incidents_capped"] is False

        result = self._run(tmp_path, monkeypatch, False, "-o", "json", "status")
        assert json.loads(result.output)["events"]["alerts_capped"] is False

    def test_q6_all_failed_hint_survives_the_capped_flags(self, tmp_path, monkeypatch):
        """The *_capped booleans must not stop the 'All API calls failed' diagnostic."""
        from typer.testing import CliRunner

        from netskope_cli.main import app

        monkeypatch.setenv("NETSKOPE_TENANT", "https://test.goskope.com")
        monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        failed = {k: (False if k.endswith("_capped") else None) for k in self._metrics(False)}
        failed["publishers"] = {"total": None, "connected": None, "not_connected": None}

        async def mock_gather(base_url, headers, time_params, cookies=None, extended=False):
            return failed, ["/api/v2/events/datasearch/alert: HTTP 500"]

        with patch("netskope_cli.commands.status_cmd._gather_status", side_effect=mock_gather):
            result = CliRunner().invoke(app, ["--no-color", "status"])
        assert "All API calls failed" in result.output

    def test_table_marks_lower_bound(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch, True, "--no-color", "status")
        assert result.exit_code == 0, result.output
        assert "\u226510,000" in result.output
        assert "page cap" in result.output

        result = self._run(tmp_path, monkeypatch, False, "--no-color", "status")
        assert "\u2265" not in result.output
        assert "10,000" in result.output
