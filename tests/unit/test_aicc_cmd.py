"""Tests for the AICC (AI Command Center) command group."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.commands.aicc._common import (
    add_filters,
    build_sort,
    extract_items,
    parse_fields,
    to_iso_utc,
    unwrap_data,
)
from netskope_cli.main import app

BASE = "https://test.goskope.com"
AICC = f"{BASE}/api/v2/aicc"


def envelope(data: dict) -> dict:
    return {"success": True, "metadata": {"requestId": "req-1", "timestamp": "2026-08-18T00:00:00Z"}, "data": data}


def page(items: list, total: int | None = None, offset: int = 0, limit: int = 50) -> dict:
    return envelope(
        {
            "total": total if total is not None else len(items),
            "offset": offset,
            "limit": limit,
            "items": items,
            "time_range": {"start_time": "2026-08-11T00:00:00Z", "end_time": "2026-08-18T00:00:00Z"},
        }
    )


APP_ROW = {
    "name": "Anthropic Claude",
    "category": "Conversation",
    "status": "Sanctioned",
    "ccl": "High",
    "cci_score": 84,
    "identities": 8,
    "uploaded_bytes": 100,
    "downloaded_bytes": 200,
    "sessions": 250,
    "transactions": 17378,
    "first_seen": "2026-06-23T12:00:04Z",
    "last_seen": "2026-08-18T20:27:10Z",
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


def _query(route, call_index: int = 0) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(route.calls[call_index].request.url)).query)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_to_iso_utc(self):
        assert to_iso_utc(0) == "1970-01-01T00:00:00Z"
        assert to_iso_utc(1750000000) == "2025-06-15T15:06:40Z"

    def test_build_sort(self):
        assert build_sort(None, "desc") is None
        assert json.loads(build_sort("bytes", "desc")) == {"field": "bytes", "order": "desc"}

    def test_add_filters_skips_empty(self):
        params: dict = {}
        add_filters(params, a=None, b=[], c=False, d="x", e=["y"], f=True)
        assert params == {"d": "x", "e": ["y"], "f": True}

    def test_unwrap_data(self):
        assert unwrap_data({"data": {"x": 1}}) == {"x": 1}
        assert unwrap_data([1, 2]) == [1, 2]

    def test_extract_items_variants(self):
        rows, meta = extract_items({"total": 5, "offset": 0, "limit": 2, "items": [{"a": 1}]})
        assert rows == [{"a": 1}]
        assert meta["total"] == 5
        rows, meta = extract_items({"total": 3, "violations": [{"v": 1}]})
        assert rows == [{"v": 1}]
        assert meta["total"] == 3
        rows, meta = extract_items({"no_rows": True})
        assert rows == []

    def test_parse_fields(self):
        assert parse_fields(None) is None
        assert parse_fields(" a, b ,") == ["a", "b"]


# ---------------------------------------------------------------------------
# Inventory list commands
# ---------------------------------------------------------------------------


class TestAppsList:
    @respx.mock
    def test_list_params_and_output(self, runner):
        route = respx.get(f"{AICC}/inventory/ai-applications").mock(
            return_value=httpx.Response(200, json=page([APP_ROW], total=66))
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "aicc",
                "apps",
                "list",
                "--start",
                "2026-08-01",
                "--end",
                "2026-08-18",
                "--status",
                "Sanctioned",
                "--ccl",
                "High",
                "--sort-by",
                "bytes",
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0
        q = _query(route)
        assert q["start_time"] == ["2026-08-01T00:00:00Z"]
        assert q["end_time"] == ["2026-08-18T00:00:00Z"]
        assert q["status"] == ["Sanctioned"]
        assert q["ccl"] == ["High"]
        assert json.loads(q["sort"][0]) == {"field": "bytes", "order": "desc"}
        assert q["limit"] == ["5"]
        assert q["offset"] == ["0"]
        rows = json.loads(result.stdout)
        assert rows[0]["name"] == "Anthropic Claude"

    @respx.mock
    def test_list_all_paginates(self, runner):
        page_one = [dict(APP_ROW, name=f"App {i}") for i in range(100)]
        page_two = [dict(APP_ROW, name="Last App")]
        route = respx.get(f"{AICC}/inventory/ai-applications").mock(
            side_effect=[
                httpx.Response(200, json=page(page_one, total=101, limit=100)),
                httpx.Response(200, json=page(page_two, total=101, offset=100, limit=100)),
            ]
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "apps", "list", "--all"])
        assert result.exit_code == 0
        assert route.call_count == 2
        assert _query(route, 1)["offset"] == ["100"]
        rows = json.loads(result.stdout)
        assert len(rows) == 101
        assert rows[-1]["name"] == "Last App"

    @respx.mock
    def test_invalid_time_exits(self, runner):
        result = runner.invoke(app, ["aicc", "apps", "list", "--start", "bogus"])
        assert result.exit_code == 2


class TestAppDetail:
    @respx.mock
    def test_get_encodes_name(self, runner):
        route = respx.get(f"{AICC}/inventory/ai-applications/Anthropic%20Claude").mock(
            return_value=httpx.Response(200, json=envelope({"metadata": {"name": "Anthropic Claude"}}))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "apps", "get", "Anthropic Claude"])
        assert result.exit_code == 0
        assert route.called
        assert json.loads(result.stdout)["metadata"]["name"] == "Anthropic Claude"

    @respx.mock
    def test_trend_kinds(self, runner):
        traffic = respx.get(f"{AICC}/inventory/ai-applications/ChatGPT/traffic-trend").mock(
            return_value=httpx.Response(200, json=envelope({"resolution": "1d", "data": [{"value": 1}]}))
        )
        risk = respx.get(f"{AICC}/inventory/ai-applications/ChatGPT/risk-trend").mock(
            return_value=httpx.Response(200, json=envelope({"resolution": "1d", "data": [{"value": 2}]}))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "apps", "trend", "ChatGPT"])
        assert result.exit_code == 0
        assert _query(traffic)["timezone"] == ["UTC"]
        assert json.loads(result.stdout) == [{"value": 1}]

        result = runner.invoke(app, ["-o", "json", "aicc", "apps", "trend", "ChatGPT", "--kind", "risk"])
        assert result.exit_code == 0
        assert "timezone" not in _query(risk)

    @respx.mock
    def test_deployments_requires_type(self, runner):
        result = runner.invoke(app, ["aicc", "apps", "deployments", "ChatGPT"])
        assert result.exit_code != 0

    @respx.mock
    def test_identities_sort_params(self, runner):
        route = respx.get(f"{AICC}/inventory/ai-applications/ChatGPT/identities").mock(
            return_value=httpx.Response(200, json=page([{"name": "alice@example.com"}]))
        )
        result = runner.invoke(
            app,
            ["-o", "json", "aicc", "apps", "identities", "ChatGPT", "--sort-by", "uploaded_bytes"],
        )
        assert result.exit_code == 0
        q = _query(route)
        assert q["sort_by"] == ["uploaded_bytes"]
        assert q["sort_dir"] == ["desc"]


class TestIdentities:
    @respx.mock
    def test_list_type_filter(self, runner):
        route = respx.get(f"{AICC}/inventory/identities").mock(
            return_value=httpx.Response(200, json=page([{"user_id": "10.0.0.1", "type": "unknown"}]))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "identities", "list", "--type", "unknown"])
        assert result.exit_code == 0
        assert _query(route)["type"] == ["unknown"]

    @respx.mock
    def test_identity_sub_resource(self, runner):
        route = respx.get(f"{AICC}/inventory/identities/alice%40example.com/mcp-servers").mock(
            return_value=httpx.Response(200, json=page([{"name": "Globalping MCP"}]))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "identities", "mcp", "alice@example.com"])
        assert result.exit_code == 0
        assert _query(route)["sort_by"] == ["bytes"]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class TestAnalytics:
    @respx.mock
    def test_breakdown_valid(self, runner):
        route = respx.get(f"{AICC}/analytics/ai-applications").mock(
            return_value=httpx.Response(200, json=envelope({"segments": [{"label": "Unsanctioned", "value": 65}]}))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "analytics", "breakdown", "apps", "-d", "status"])
        assert result.exit_code == 0
        q = _query(route)
        assert q["dimension"] == ["status"]
        assert q["metric"] == ["count"]
        assert json.loads(result.stdout)[0]["label"] == "Unsanctioned"

    def test_breakdown_invalid_dimension(self, runner):
        result = runner.invoke(app, ["aicc", "analytics", "breakdown", "apps", "-d", "provider"])
        assert result.exit_code != 0
        assert "Invalid dimension" in result.output

    def test_breakdown_invalid_metric(self, runner):
        result = runner.invoke(app, ["aicc", "analytics", "breakdown", "mcp", "-d", "ccl", "-m", "bytes"])
        assert result.exit_code != 0
        assert "Invalid metric" in result.output

    @respx.mock
    def test_counts_requires_type_param(self, runner):
        route = respx.get(f"{AICC}/analytics/counts").mock(
            return_value=httpx.Response(200, json=envelope({"value": 92, "trend": None, "data": []}))
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "analytics", "counts", "identities"])
        assert result.exit_code == 0
        q = _query(route)
        assert q["type"] == ["identities"]
        assert q["timezone"] == ["UTC"]

    @respx.mock
    def test_alert_policies_rows(self, runner):
        respx.get(f"{AICC}/analytics/alerts/policies").mock(
            return_value=httpx.Response(
                200,
                json=envelope(
                    {"total_alerts": 49, "items": [{"policy": "PII Profile", "severity": "critical", "count": 24}]}
                ),
            )
        )
        result = runner.invoke(app, ["-o", "json", "aicc", "analytics", "alert-policies"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)[0]["policy"] == "PII Profile"


# ---------------------------------------------------------------------------
# Data protection
# ---------------------------------------------------------------------------


class TestDataProtection:
    @respx.mock
    def test_violations_uses_violations_key(self, runner):
        route = respx.get(f"{AICC}/provider/anthropic/data-protection/violations").mock(
            return_value=httpx.Response(
                200,
                json=envelope(
                    {
                        "total": 10565,
                        "offset": 0,
                        "limit": 50,
                        "violations": [{"severity": "critical", "user": "alice@example.com"}],
                    }
                ),
            )
        )
        result = runner.invoke(
            app,
            ["-o", "json", "aicc", "data-protection", "violations", "anthropic", "--severity", "critical"],
        )
        assert result.exit_code == 0
        assert _query(route)["severity"] == ["critical"]
        assert json.loads(result.stdout)[0]["user"] == "alice@example.com"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    @respx.mock
    def test_404_shows_license_hint(self, runner):
        respx.get(f"{AICC}/inventory/ai-applications").mock(return_value=httpx.Response(404, json={}))
        result = runner.invoke(app, ["aicc", "apps", "list"])
        assert result.exit_code == 1
        assert "ai_security_discovery" in result.output

    @respx.mock
    def test_403_shows_scope_hint(self, runner):
        respx.get(f"{AICC}/inventory/ai-applications").mock(return_value=httpx.Response(403, json={}))
        result = runner.invoke(app, ["aicc", "apps", "list"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Overview & report
# ---------------------------------------------------------------------------


def _mock_report_endpoints() -> None:
    respx.get(f"{AICC}/data-coverage").mock(
        return_value=httpx.Response(200, json=envelope({"data_available_since": "2026-06-19T09:36:43Z"}))
    )
    respx.get(f"{AICC}/analytics/entity-counts").mock(
        return_value=httpx.Response(
            200,
            json=envelope(
                {"applications": 66, "mcp_servers": 49, "agents": 8, "models": 11, "users": 88, "nhi": 0, "unknown": 4}
            ),
        )
    )
    respx.get(f"{AICC}/analytics/sums").mock(
        return_value=httpx.Response(
            200, json=envelope({"value": 10099060016, "previous_value": 2908529906, "trend": 247.2, "data": []})
        )
    )
    respx.get(f"{AICC}/analytics/counts").mock(
        return_value=httpx.Response(200, json=envelope({"value": 49, "previous_value": 10, "trend": 390.0}))
    )
    respx.get(f"{AICC}/analytics/ai-applications").mock(
        return_value=httpx.Response(
            200,
            json=envelope({"segments": [{"label": "Unsanctioned", "value": 65}, {"label": "Sanctioned", "value": 1}]}),
        )
    )
    respx.get(f"{AICC}/inventory/ai-applications").mock(return_value=httpx.Response(200, json=page([APP_ROW])))
    respx.get(f"{AICC}/inventory/mcp-servers").mock(
        return_value=httpx.Response(
            200, json=page([{"name": "Globalping MCP", "sessions": 22, "ccl": "Medium", "cci_score": 64}])
        )
    )
    respx.get(f"{AICC}/inventory/identities").mock(
        return_value=httpx.Response(
            200, json=page([{"user_id": "alice@example.com", "type": "user", "downloaded_bytes": 999}])
        )
    )
    respx.get(f"{AICC}/analytics/alerts/matrix").mock(
        return_value=httpx.Response(
            200, json=envelope({"items": [{"asset": "AI App", "detection": "DLP", "count": 42}]})
        )
    )
    respx.get(f"{AICC}/analytics/alerts/policies").mock(
        return_value=httpx.Response(
            200,
            json=envelope(
                {"total_alerts": 49, "items": [{"policy": "PII Profile", "severity": "critical", "count": 24}]}
            ),
        )
    )


class TestOverviewAndReport:
    @respx.mock
    def test_overview(self, runner):
        _mock_report_endpoints()
        result = runner.invoke(app, ["-o", "json", "aicc", "overview"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["entities"]["applications"] == 66
        assert data["traffic_bytes"]["trend"] == 247.2
        assert data["data_available_since"] == "2026-06-19T09:36:43Z"

    @respx.mock
    def test_report_json(self, runner):
        _mock_report_endpoints()
        result = runner.invoke(app, ["aicc", "report", "--top", "5"])
        assert result.exit_code == 0
        doc = json.loads(result.stdout)
        assert doc["executive_summary"]["unsanctioned_applications"] == 65
        assert doc["applications"][0]["name"] == "Anthropic Claude"
        assert doc["alerts"]["total_alerts"] == 49
        assert doc["key_findings"]["top_app_by_sessions"].startswith("Anthropic Claude")

    @respx.mock
    def test_report_markdown_to_file(self, runner, tmp_path):
        _mock_report_endpoints()
        out = tmp_path / "airr.md"
        result = runner.invoke(app, ["aicc", "report", "--format", "markdown", "--out", str(out)])
        assert result.exit_code == 0
        text = out.read_text()
        assert "# Netskope AI Risk Report" in text
        assert "Anthropic Claude" in text
        assert "## Executive Summary" in text
