"""Tests for DEM (Digital Experience Monitoring) query, alert, and app commands."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.main import app

BASE = "https://test.goskope.com"

MOCK_METRICS_RESPONSE = {
    "data": [{"user_id": "alice@example.com", "avg_score": 85.2}],
    "meta": {"total": 1},
}

MOCK_ENTITIES_RESPONSE = {
    "data": [
        {
            "user_id": "alice@example.com",
            "user_score": 82,
            "device_os": "MacOS",
        }
    ],
    "total": 1,
}

MOCK_STATES_RESPONSE = {
    "data": [{"user_id": "alice@example.com", "status": "connected"}],
    "meta": {"total": 1},
}

MOCK_TRACEROUTE_RESPONSE = {
    "data": [{"hop": 1, "ip": "10.0.0.1", "latency": 5}],
}

MOCK_FIELDS_RESPONSE = {
    "metrics": [{"name": "score", "type": "float"}],
    "keys": [{"name": "user_id", "type": "string"}],
    "functions": ["avg", "sum", "min", "max"],
}

MOCK_ALERT = {
    "alertId": "alert-123",
    "alertCategory": "User Experience",
    "severity": "critical",
    "status": "open",
}

MOCK_ALERTS_SEARCH = {
    "data": [MOCK_ALERT],
    "total": 1,
}

MOCK_ALERT_ENTITIES = {
    "data": [{"user_id": "alice@example.com", "device": "MacBook-Pro"}],
    "total": 1,
}

MOCK_APPS_RESPONSE = {
    "data": [
        {
            "appName": "Google Gmail",
            "appType": "predefined",
            "id": "app-1",
        }
    ],
    "total": 1,
}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("NETSKOPE_TENANT", "test.goskope.com")
    monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken123")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


# ---------------------------------------------------------------------------
# metrics query
# ---------------------------------------------------------------------------


class TestMetricsQuery:
    @respx.mock
    def test_query_success(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getdata").mock(
            return_value=httpx.Response(200, json=MOCK_METRICS_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "metrics",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                '["user_id", {"avg_score": ["avg", "score"]}]',
                "--groupby",
                "user_id",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
                "--limit",
                "25",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["from"] == "ux_score"
        assert sent_body["select"] == ["user_id", {"avg_score": ["avg", "score"]}]
        assert sent_body["groupby"] == ["user_id"]
        assert sent_body["begin"] == 1711929600000
        assert sent_body["end"] == 1712016000000
        assert sent_body["limit"] == 25

    @respx.mock
    def test_query_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/getdata").mock(
            return_value=httpx.Response(200, json=MOCK_METRICS_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "metrics",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                '["user_id"]',
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_query_invalid_data_source(self, runner):
        result = runner.invoke(
            app,
            [
                "dem",
                "metrics",
                "query",
                "--data-source",
                "invalid_source",
                "--select",
                '["user_id"]',
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code != 0
        assert "invalid" in str(result.exception).lower()

    def test_query_invalid_select_json(self, runner):
        result = runner.invoke(
            app,
            [
                "dem",
                "metrics",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                "not json",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code != 0

    @respx.mock
    def test_query_minimal_params(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/getdata").mock(
            return_value=httpx.Response(200, json=MOCK_METRICS_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "metrics",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                '["user_id"]',
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_query_with_where_and_orderby(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getdata").mock(
            return_value=httpx.Response(200, json=MOCK_METRICS_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "metrics",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                '["user_id"]',
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
                "--where",
                '["=", "user_id", ["$", "alice@example.com"]]',
                "--orderby",
                '[["user_id", "asc"]]',
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["where"] == ["=", "user_id", ["$", "alice@example.com"]]
        assert sent_body["orderby"] == [["user_id", "asc"]]


# ---------------------------------------------------------------------------
# entities list
# ---------------------------------------------------------------------------


class TestEntitiesList:
    @respx.mock
    def test_list_success(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/getentities").mock(
            return_value=httpx.Response(200, json=MOCK_ENTITIES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "entities",
                "list",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    def test_list_exceeds_48h_window(self, runner):
        result = runner.invoke(
            app,
            [
                "dem",
                "entities",
                "list",
                "--start-time",
                "1710000000",
                "--end-time",
                str(1710000000 + 200000),  # ~55 hours
            ],
        )
        assert result.exit_code != 0
        assert "48" in str(result.exception)

    @respx.mock
    def test_list_with_filters(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getentities").mock(
            return_value=httpx.Response(200, json=MOCK_ENTITIES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "entities",
                "list",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
                "--user",
                "alice@example.com",
                "--applications",
                "Google Gmail,Twitter",
                "--device-os",
                "MacOS,Windows",
                "--exp-score",
                "0~30,31~70",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["user"] == "alice@example.com"
        assert sent_body["applications"] == ["Google Gmail", "Twitter"]
        assert sent_body["deviceOs"] == ["MacOS", "Windows"]
        assert sent_body["expScore"] == ["0~30", "31~70"]

    @respx.mock
    def test_list_with_pagination(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getentities").mock(
            return_value=httpx.Response(200, json=MOCK_ENTITIES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "entities",
                "list",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
                "--limit",
                "25",
                "--offset",
                "10",
                "--sort-order",
                "desc",
            ],
        )
        assert result.exit_code == 0
        req = route.calls[0].request
        assert "limit=25" in str(req.url)
        assert "offset=10" in str(req.url)
        assert "sortorder=desc" in str(req.url)

    @respx.mock
    def test_list_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/getentities").mock(
            return_value=httpx.Response(200, json=MOCK_ENTITIES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "entities",
                "list",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# states query
# ---------------------------------------------------------------------------


class TestStatesQuery:
    @respx.mock
    def test_query_agent_status(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getstates").mock(
            return_value=httpx.Response(200, json=MOCK_STATES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "states",
                "query",
                "--data-source",
                "agent_status",
                "--select",
                '["user_id", "status"]',
                "--limit",
                "100",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["from"] == "agent_status"
        assert sent_body["select"] == ["user_id", "status"]

    @respx.mock
    def test_query_client_status(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/getstates").mock(
            return_value=httpx.Response(200, json=MOCK_STATES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "states",
                "query",
                "--data-source",
                "client_status",
                "--select",
                '["user_id"]',
            ],
        )
        assert result.exit_code == 0

    def test_query_invalid_data_source(self, runner):
        result = runner.invoke(
            app,
            [
                "dem",
                "states",
                "query",
                "--data-source",
                "ux_score",
                "--select",
                '["user_id"]',
            ],
        )
        assert result.exit_code != 0

    @respx.mock
    def test_query_with_where(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/getstates").mock(
            return_value=httpx.Response(200, json=MOCK_STATES_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "states",
                "query",
                "--data-source",
                "agent_status",
                "--select",
                '["user_id"]',
                "--where",
                '["=", "user_id", ["$", "alice@example.com"]]',
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["where"] == ["=", "user_id", ["$", "alice@example.com"]]


# ---------------------------------------------------------------------------
# traceroute query
# ---------------------------------------------------------------------------


class TestTracerouteQuery:
    @respx.mock
    def test_query_traceroute_pop(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/gettraceroute").mock(
            return_value=httpx.Response(200, json=MOCK_TRACEROUTE_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "traceroute",
                "query",
                "--data-source",
                "traceroute_pop",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["from"] == "traceroute_pop"

    def test_query_invalid_data_source(self, runner):
        result = runner.invoke(
            app,
            [
                "dem",
                "traceroute",
                "query",
                "--data-source",
                "ux_score",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code != 0

    @respx.mock
    def test_query_with_where_and_orderby(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/query/gettraceroute").mock(
            return_value=httpx.Response(200, json=MOCK_TRACEROUTE_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "traceroute",
                "query",
                "--data-source",
                "traceroute_pop",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
                "--where",
                '["=", "user_id", ["$", "alice@example.com"]]',
                "--orderby",
                '[["latency", "desc"]]',
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["where"] == ["=", "user_id", ["$", "alice@example.com"]]
        assert sent_body["orderby"] == [["latency", "desc"]]

    @respx.mock
    def test_query_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/dem/query/gettraceroute").mock(
            return_value=httpx.Response(200, json=MOCK_TRACEROUTE_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "traceroute",
                "query",
                "--data-source",
                "traceroute_bypassed",
                "--begin",
                "1711929600000",
                "--end",
                "1712016000000",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# fields list
# ---------------------------------------------------------------------------


class TestFieldsList:
    @respx.mock
    def test_list_all(self, runner):
        respx.get(f"{BASE}/api/v2/dem/query/definitions").mock(
            return_value=httpx.Response(200, json=MOCK_FIELDS_RESPONSE)
        )
        result = runner.invoke(app, ["dem", "fields", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_with_source(self, runner):
        route = respx.get(f"{BASE}/api/v2/dem/query/definitions").mock(
            return_value=httpx.Response(200, json=MOCK_FIELDS_RESPONSE)
        )
        result = runner.invoke(app, ["dem", "fields", "list", "--source", "rum_steered"])
        assert result.exit_code == 0
        assert "source=rum_steered" in str(route.calls[0].request.url)

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/dem/query/definitions").mock(
            return_value=httpx.Response(200, json=MOCK_FIELDS_RESPONSE)
        )
        result = runner.invoke(app, ["-o", "json", "dem", "fields", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metrics" in data or isinstance(data, list)


# ---------------------------------------------------------------------------
# experience-alerts search
# ---------------------------------------------------------------------------


class TestExperienceAlertsSearch:
    @respx.mock
    def test_search_success(self, runner):
        respx.post(f"{BASE}/api/v2/dem/alerts/getalerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_SEARCH)
        )
        result = runner.invoke(app, ["dem", "experience-alerts", "search"])
        assert result.exit_code == 0

    @respx.mock
    def test_search_with_filters(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/alerts/getalerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_SEARCH)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "experience-alerts",
                "search",
                "--alert-category",
                "Network,User Experience",
                "--alert-type",
                "Experience Score",
                "--severity",
                "critical,high",
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["alertCategory"] == ["Network", "User Experience"]
        assert sent_body["alertType"] == ["Experience Score"]
        assert sent_body["severity"] == ["critical", "high"]
        assert sent_body["limit"] == 5

    @respx.mock
    def test_search_with_sort(self, runner):
        route = respx.post(f"{BASE}/api/v2/dem/alerts/getalerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_SEARCH)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "experience-alerts",
                "search",
                "--sort-field",
                "severity",
                "--sort-asc",
            ],
        )
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["sortBy"] == {"field": "severity", "desc": False}

    @respx.mock
    def test_search_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/dem/alerts/getalerts").mock(
            return_value=httpx.Response(200, json=MOCK_ALERTS_SEARCH)
        )
        result = runner.invoke(app, ["-o", "json", "dem", "experience-alerts", "search"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# experience-alerts get
# ---------------------------------------------------------------------------


class TestExperienceAlertsGet:
    @respx.mock
    def test_get_success(self, runner):
        respx.get(f"{BASE}/api/v2/dem/alerts/alert-123").mock(return_value=httpx.Response(200, json=MOCK_ALERT))
        result = runner.invoke(app, ["dem", "experience-alerts", "get", "alert-123"])
        assert result.exit_code == 0

    @respx.mock
    def test_get_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/dem/alerts/alert-123").mock(return_value=httpx.Response(200, json=MOCK_ALERT))
        result = runner.invoke(app, ["-o", "json", "dem", "experience-alerts", "get", "alert-123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["alertId"] == "alert-123"

    def test_get_missing_id(self, runner):
        result = runner.invoke(app, ["dem", "experience-alerts", "get"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# experience-alerts entities
# ---------------------------------------------------------------------------


class TestExperienceAlertsEntities:
    @respx.mock
    def test_entities_success(self, runner):
        respx.get(f"{BASE}/api/v2/dem/alerts/alert-123/entities").mock(
            return_value=httpx.Response(200, json=MOCK_ALERT_ENTITIES)
        )
        result = runner.invoke(app, ["dem", "experience-alerts", "entities", "alert-123"])
        assert result.exit_code == 0

    @respx.mock
    def test_entities_with_pagination(self, runner):
        route = respx.get(f"{BASE}/api/v2/dem/alerts/alert-123/entities").mock(
            return_value=httpx.Response(200, json=MOCK_ALERT_ENTITIES)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "experience-alerts",
                "entities",
                "alert-123",
                "--limit",
                "25",
                "--offset",
                "10",
                "--sortby",
                "user_id",
                "--sort-order",
                "asc",
            ],
        )
        assert result.exit_code == 0
        url = str(route.calls[0].request.url)
        assert "limit=25" in url
        assert "offset=10" in url
        assert "sortby=user_id" in url
        assert "sortorder=asc" in url

    @respx.mock
    def test_entities_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/dem/alerts/alert-123/entities").mock(
            return_value=httpx.Response(200, json=MOCK_ALERT_ENTITIES)
        )
        result = runner.invoke(app, ["-o", "json", "dem", "experience-alerts", "entities", "alert-123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# apps list
# ---------------------------------------------------------------------------


class TestAppsList:
    @respx.mock
    def test_list_success(self, runner):
        respx.get(f"{BASE}/api/v2/dem/apps").mock(return_value=httpx.Response(200, json=MOCK_APPS_RESPONSE))
        result = runner.invoke(app, ["dem", "apps", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_list_with_type_filter(self, runner):
        route = respx.get(f"{BASE}/api/v2/dem/apps").mock(return_value=httpx.Response(200, json=MOCK_APPS_RESPONSE))
        result = runner.invoke(app, ["dem", "apps", "list", "--type", "predefined"])
        assert result.exit_code == 0
        assert "type=predefined" in str(route.calls[0].request.url)

    @respx.mock
    def test_list_with_name_filter(self, runner):
        route = respx.get(f"{BASE}/api/v2/dem/apps").mock(return_value=httpx.Response(200, json=MOCK_APPS_RESPONSE))
        result = runner.invoke(app, ["dem", "apps", "list", "--name", "Gmail"])
        assert result.exit_code == 0
        assert "name=Gmail" in str(route.calls[0].request.url)

    @respx.mock
    def test_list_json_output(self, runner):
        respx.get(f"{BASE}/api/v2/dem/apps").mock(return_value=httpx.Response(200, json=MOCK_APPS_RESPONSE))
        result = runner.invoke(app, ["-o", "json", "dem", "apps", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Existing DEM commands regression
# ---------------------------------------------------------------------------


class TestExistingDemCommands:
    @respx.mock
    def test_probes_list_still_works(self, runner):
        respx.get(f"{BASE}/api/v2/dem/appprobes").mock(return_value=httpx.Response(200, json={"data": [], "total": 0}))
        result = runner.invoke(app, ["dem", "probes", "list"])
        assert result.exit_code == 0

    @respx.mock
    def test_alerts_list_still_works(self, runner):
        respx.get(f"{BASE}/api/v2/dem/alert/rules").mock(
            return_value=httpx.Response(200, json={"data": [], "total": 0})
        )
        result = runner.invoke(app, ["dem", "alerts", "list"])
        assert result.exit_code == 0

    def test_dem_help_shows_new_subcommands(self, runner):
        result = runner.invoke(app, ["dem", "--help"])
        assert result.exit_code == 0
        for sub in ["metrics", "entities", "states", "traceroute", "fields", "experience-alerts", "apps"]:
            assert sub in result.output
