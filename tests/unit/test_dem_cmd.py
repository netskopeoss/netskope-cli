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
        for sub in [
            "metrics",
            "dataset",
            "sites",
            "entities",
            "states",
            "traceroute",
            "fields",
            "experience-alerts",
            "apps",
        ]:
            assert sub in result.output


# ---------------------------------------------------------------------------
# dem dataset query (public getdataset endpoint)
# ---------------------------------------------------------------------------

DATASET_URL = f"{BASE}/api/v2/dem/query/getdataset"

MOCK_HTTP_SITE_ROWS = {
    "data": [
        {
            "site_name": "",
            "avg_dns_ms": 63.519,
            "avg_proxy_connect_ms": 84.02,
            "apps_reached": 9,
            "apps": ["Slack", "Salesforce.com"],
            "pops": ["FR-PAR2", "PT-LIS1"],
            "http_requests": 11324,
        },
        {
            "site_name": "Paris",
            "avg_dns_ms": 27.094713,
            "avg_proxy_connect_ms": 12.5,
            "apps_reached": 4,
            "apps": ["Slack"],
            "pops": ["FR-PAR2"],
            "http_requests": 2000,
        },
        {
            "site_name": "Melbourne",
            "avg_dns_ms": 305.78,
            "avg_proxy_connect_ms": 40.0,
            "apps_reached": 4,
            "apps": ["Slack"],
            "pops": ["AU-SYD2"],
            "http_requests": 1974,
        },
    ],
    "meta": {"fields": ["site_name", "avg_dns_ms"]},
}

MOCK_TR_SITE_ROWS = {
    "data": [
        {
            "site_name": "",
            "avg_isp_latency_ms": 15.392,
            "avg_isp_latency_furthest_ms": 13.7,
            "avg_packet_loss": 0.00104,
            "pops": ["FR-PAR3", "FR-PAR2"],
            "traceroutes": 1595,
        },
        {
            "site_name": "Paris",
            "avg_isp_latency_ms": 8.383,
            "avg_isp_latency_furthest_ms": 8.0,
            "avg_packet_loss": 0.0,
            "pops": ["FR-PAR2"],
            "traceroutes": 380,
        },
        {
            "site_name": "Londres",
            "avg_isp_latency_ms": 4.337,
            "avg_isp_latency_furthest_ms": 4.0,
            "avg_packet_loss": None,
            "pops": ["UK-LON2"],
            "traceroutes": 360,
        },
    ],
    "meta": {},
}


class TestDatasetQuery:
    @respx.mock
    def test_query_success(self, runner):
        route = respx.post(DATASET_URL).mock(return_value=httpx.Response(200, json=MOCK_HTTP_SITE_ROWS))
        result = runner.invoke(
            app,
            [
                "dem",
                "dataset",
                "query",
                "--data-source",
                "http_steered",
                "--select",
                '["site_name", {"avg_dns_ms": ["/", ["avg", "dns_time"], 1000]}]',
                "--groupby",
                "site_name",
                "--orderby",
                '[["avg_dns_ms", "desc"]]',
                "--where",
                '["=", "country", ["$", "France"]]',
                "--begin",
                "1725364316000",
                "--end",
                "1725450716000",
                "--limit",
                "50000",
            ],
        )
        assert result.exit_code == 0, result.output
        sent = json.loads(route.calls[0].request.content)
        assert sent["from"] == "http_steered"
        assert sent["select"] == ["site_name", {"avg_dns_ms": ["/", ["avg", "dns_time"], 1000]}]
        assert sent["groupby"] == ["site_name"]
        assert sent["orderby"] == [["avg_dns_ms", "desc"]]
        assert sent["where"] == ["=", "country", ["$", "France"]]
        assert sent["begin"] == 1725364316000
        assert sent["end"] == 1725450716000
        assert sent["limit"] == 9999  # capped at getdataset's exclusiveMaximum

    @respx.mock
    def test_query_json_output(self, runner):
        respx.post(DATASET_URL).mock(return_value=httpx.Response(200, json=MOCK_HTTP_SITE_ROWS))
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "dataset",
                "query",
                "-d",
                "traceroute_pop",
                "-s",
                '["site_name"]',
                "-b",
                "1725364316000",
                "-e",
                "1725450716000",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data[1]["site_name"] == "Paris"

    def test_query_rejects_non_dataset_source(self, runner):
        result = runner.invoke(
            app,
            ["dem", "dataset", "query", "-d", "ux_score", "-s", '["user_id"]', "-b", "1", "-e", "2"],
        )
        assert result.exit_code != 0
        assert "Invalid data source" in str(result.exception)
        assert "dem metrics query" in str(result.exception.suggestion)

    def test_query_rejects_window_over_48h(self, runner):
        begin = 1725364316000
        result = runner.invoke(
            app,
            [
                "dem",
                "dataset",
                "query",
                "-d",
                "http_steered",
                "-s",
                '["site_name"]',
                "-b",
                str(begin),
                "-e",
                str(begin + 172_800_001),
            ],
        )
        assert result.exit_code != 0
        assert "48-hour" in str(result.exception)

    def test_query_rejects_end_before_begin(self, runner):
        result = runner.invoke(
            app,
            ["dem", "dataset", "query", "-d", "http_steered", "-s", '["site_name"]', "-b", "20", "-e", "10"],
        )
        assert result.exit_code != 0
        assert "--end must be greater" in str(result.exception)


# ---------------------------------------------------------------------------
# dem sites summary
# ---------------------------------------------------------------------------


class TestSitesSummary:
    @respx.mock
    def test_summary_joins_both_sources(self, runner):
        route = respx.post(DATASET_URL).mock(
            side_effect=[
                httpx.Response(200, json=MOCK_HTTP_SITE_ROWS),
                httpx.Response(200, json=MOCK_TR_SITE_ROWS),
            ]
        )
        result = runner.invoke(
            app,
            ["-o", "json", "dem", "sites", "summary", "--begin", "1725364316000", "--end", "1725450716000"],
        )
        assert result.exit_code == 0, result.output
        assert route.call_count == 2
        http_body = json.loads(route.calls[0].request.content)
        tr_body = json.loads(route.calls[1].request.content)
        assert http_body["from"] == "http_steered"
        assert tr_body["from"] == "traceroute_pop"
        for body in (http_body, tr_body):
            assert body["groupby"] == ["site_name"]
            assert body["begin"] == 1725364316000
            assert body["end"] == 1725450716000
            assert body["limit"] == 100
            assert "where" not in body
        # Exact function names the API accepts (countDistinct, not count_distinct)
        assert {"apps_reached": ["countDistinct", "application_name"]} in http_body["select"]
        assert {"avg_isp_latency_ms": ["/", ["avg", "rtt_e2e"], 1000]} in tr_body["select"]

        rows = json.loads(result.output)
        by_site = {r["site_name"]: r for r in rows}
        assert set(by_site) == {"Remote", "Paris", "Melbourne", "Londres"}

        remote = by_site["Remote"]
        assert remote["avg_dns_ms"] == 63.52
        assert remote["avg_isp_latency_ms"] == 15.39
        assert remote["pops"] == ["FR-PAR2", "FR-PAR3", "PT-LIS1"]  # union of both sources
        assert remote["pops_used"] == 3
        assert remote["apps_reached"] == 9
        assert remote["avg_packet_loss_pct"] == 0.104
        assert remote["http_requests"] == 11324
        assert remote["traceroutes"] == 1595

        # Site only in traceroute data: HTTP columns stay empty
        londres = by_site["Londres"]
        assert londres["avg_dns_ms"] is None
        assert londres["apps_reached"] == 0
        assert londres["avg_packet_loss_pct"] is None
        assert londres["avg_isp_latency_ms"] == 4.34

        # Site only in HTTP data sorts last (no ISP latency)
        assert rows[-1]["site_name"] == "Melbourne"
        assert rows[-1]["avg_isp_latency_ms"] is None
        # Otherwise sorted by ISP latency descending
        assert [r["site_name"] for r in rows[:3]] == ["Remote", "Paris", "Londres"]

    @respx.mock
    def test_summary_defaults_to_last_24h(self, runner, monkeypatch):
        import netskope_cli.commands.dem_cmd as dem_cmd

        monkeypatch.setattr(dem_cmd, "_now_ms", lambda: 1_725_450_716_000)
        route = respx.post(DATASET_URL).mock(return_value=httpx.Response(200, json={"data": []}))
        result = runner.invoke(app, ["-o", "json", "dem", "sites", "summary"])
        assert result.exit_code == 0, result.output
        body = json.loads(route.calls[0].request.content)
        assert body["end"] == 1_725_450_716_000
        assert body["begin"] == 1_725_450_716_000 - 86_400_000

    @respx.mock
    def test_summary_where_and_limit_apply_to_both_queries(self, runner):
        route = respx.post(DATASET_URL).mock(return_value=httpx.Response(200, json={"data": []}))
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "sites",
                "summary",
                "-b",
                "1725364316000",
                "-e",
                "1725450716000",
                "--where",
                '["=", "country", ["$", "France"]]',
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0, result.output
        for call in route.calls:
            body = json.loads(call.request.content)
            assert body["where"] == ["=", "country", ["$", "France"]]
            assert body["limit"] == 5

    def test_summary_rejects_window_over_48h(self, runner):
        result = runner.invoke(
            app, ["dem", "sites", "summary", "-b", "1725364316000", "-e", str(1725364316000 + 172_800_001)]
        )
        assert result.exit_code != 0
        assert "48-hour" in str(result.exception)

    @respx.mock
    def test_summary_surfaces_upstream_error(self, runner):
        respx.post(DATASET_URL).mock(
            return_value=httpx.Response(422, json={"detail": [{"msg": "Cannot find function 'count_distinct'"}]})
        )
        result = runner.invoke(app, ["dem", "sites", "summary", "-b", "1725364316000", "-e", "1725450716000"])
        assert result.exit_code != 0
        assert "count_distinct" in str(result.exception)
