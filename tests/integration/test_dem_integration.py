"""Integration tests for DEM commands against a live Netskope tenant.

Run with:
    DEM_INTEGRATION_TESTS=1 poetry run pytest tests/integration/test_dem_integration.py -v
"""

from __future__ import annotations

import os
import time

import pytest
from typer.testing import CliRunner

from netskope_cli.main import app

pytestmark = pytest.mark.skipif(
    os.environ.get("DEM_INTEGRATION_TESTS") != "1",
    reason="Set DEM_INTEGRATION_TESTS=1 to run DEM integration tests",
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    tenant = os.environ.get("NETSKOPE_TENANT", "")
    token = os.environ.get("NETSKOPE_API_TOKEN", "")
    if not tenant or not token:
        pytest.skip("NETSKOPE_TENANT and NETSKOPE_API_TOKEN env vars required")
    monkeypatch.setenv("NETSKOPE_TENANT", tenant)
    monkeypatch.setenv("NETSKOPE_API_TOKEN", token)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


class TestFieldsListIntegration:
    def test_list_all(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "fields", "list"])
        assert result.exit_code == 0

    def test_list_with_source(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "fields", "list", "--source", "rum_steered"])
        assert result.exit_code == 0


class TestAppsListIntegration:
    def test_list_all(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "apps", "list"])
        assert result.exit_code == 0

    def test_list_predefined(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "apps", "list", "--type", "predefined", "--limit", "5"])
        assert result.exit_code == 0


class TestMetricsQueryIntegration:
    def test_query_ux_score(self, runner):
        now_ms = int(time.time() * 1000)
        day_ago_ms = now_ms - 86400000
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
                '["user_id", {"avg_score": ["avg", "score"]}]',
                "--groupby",
                "user_id",
                "--begin",
                str(day_ago_ms),
                "--end",
                str(now_ms),
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0


class TestEntitiesListIntegration:
    def test_list_recent(self, runner):
        now = int(time.time())
        hour_ago = now - 3600
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "entities",
                "list",
                "--start-time",
                str(hour_ago),
                "--end-time",
                str(now),
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0


class TestStatesQueryIntegration:
    def test_query_agent_status(self, runner):
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "states",
                "query",
                "--data-source",
                "agent_status",
                "--select",
                '["user_id", "status"]',
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0


class TestExperienceAlertsSearchIntegration:
    def test_search(self, runner):
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "experience-alerts",
                "search",
                "--limit",
                "5",
            ],
        )
        assert result.exit_code == 0


class TestExistingDemIntegration:
    def test_probes_list(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "probes", "list"])
        assert result.exit_code == 0

    def test_alerts_list(self, runner):
        result = runner.invoke(app, ["-o", "json", "dem", "alerts", "list"])
        assert result.exit_code == 0
