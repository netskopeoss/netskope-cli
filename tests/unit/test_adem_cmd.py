"""Tests for ADEM (Application Digital Experience Monitoring) commands."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.main import app

BASE = "https://test.goskope.com"

# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

MOCK_APPLICATIONS = {
    "data": [
        {"appName": "Google Gmail", "expScore": 85},
        {"appName": "Slack", "expScore": 92},
    ]
}

MOCK_DEVICE_DETAILS = {
    "clientStatus": "Enabled",
    "clientVersion": "108.2.0.943",
    "cpu": "Apple M3 Pro x64",
    "deviceClassification": "Managed",
    "deviceName": "MacBook-Pro",
    "deviceOs": "MacOS",
    "deviceScore": 78,
    "gateway": "10.0.0.1",
    "geo": {
        "city": "Paris",
        "country": "FR",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "region": "Ile-De-France",
    },
    "lastActivity": 1710050000,
    "memory": "16000GB",
    "model": "MacBookPro18,3",
    "npaLastActivity": 1710049000,
    "npaLastConnectedPop": "FR-PAR2",
    "pop": "FR-PAR1",
    "predefinedAppLastActivity": 1710048000,
    "predefinedAppLastConnectedPop": "FR-PAR1",
    "privateIp": "192.168.1.100",
    "publicIp": "203.0.113.50",
}

MOCK_NPA_NETWORK_PATHS = {
    "nodes": [
        {"id": 1, "name": "MacBook-Pro", "type": "DEVICE"},
        {"id": 2, "name": "FR-PAR1", "type": "GATEWAY"},
        {"id": 3, "name": "stitcher-01", "type": "STITCHER"},
        {"id": 4, "name": "publisher-01", "type": "PUBLISHER"},
        {
            "id": 5,
            "name": "10.100.12.4",
            "type": "HOST",
            "npaHostDetails": {"npaApplications": ["internal-app"]},
        },
    ],
    "edges": [
        {"source": 1, "destination": 2, "avgLatency": 5, "medianLatency": 4, "noOfSessions": 10},
        {"source": 2, "destination": 3, "avgLatency": 12, "medianLatency": 11, "noOfSessions": 10},
        {"source": 3, "destination": 4, "avgLatency": 8, "medianLatency": 7, "noOfSessions": 10},
        {"source": 4, "destination": 5, "avgLatency": 3, "medianLatency": 2, "noOfSessions": 10},
    ],
}

MOCK_INFO = {
    "user": "alice@example.com",
    "expScore": 72,
    "lastActivity": 1710050000,
    "lastKnownLocation": "Paris, Ile-De-France, FR",
    "lastKnownLatitude": 48.8566,
    "lastKnownLongitude": 2.3522,
    "organizationUnit": "Engineering",
    "userGroup": "Developers",
    "deviceList": [{"deviceId": "DEV-1234", "deviceName": "MacBook-Pro", "deviceOs": "MacOS", "type": "DEVICE"}],
}

MOCK_DEVICES = [
    {"deviceId": "DEV-1234", "deviceName": "MacBook-Pro", "deviceOs": "MacOS", "expScore": 78, "type": "DEVICE"}
]

MOCK_SCORES = {
    "aggregationType": "avg",
    "metrics": {
        "appScore": 80,
        "deviceScore": 75,
        "expScore": 72,
        "networkScore": 68,
        "npaHostScore": 90,
    },
}

MOCK_RCA = {
    "CPU_SCORE": {"score": 45, "utilization": 82},
    "MEMORY_SCORE": {"score": 72, "utilization": 55},
    "DISK_SCORE": {"score": 88, "utilization": 30},
}

MOCK_NPA_HOSTS = {
    "npaHosts": [
        {
            "expScore": 90,
            "npaApplications": ["internal-app"],
            "npaHost": "10.100.12.4",
            "npaPorts": [443],
        }
    ],
    "totalCount": 1,
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
# applications
# ---------------------------------------------------------------------------


class TestApplications:
    @respx.mock
    def test_success(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/getapplications").mock(
            return_value=httpx.Response(200, json=MOCK_APPLICATIONS)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "applications",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/getapplications").mock(
            return_value=httpx.Response(200, json=MOCK_APPLICATIONS)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "applications",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    @respx.mock
    def test_request_body(self, runner):
        route = respx.post(f"{BASE}/api/v2/adem/users/getapplications").mock(
            return_value=httpx.Response(200, json=MOCK_APPLICATIONS)
        )
        runner.invoke(
            app,
            [
                "dem",
                "users",
                "applications",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["user"] == "alice@example.com"
        assert body["starttime"] == 1710000000
        assert body["endtime"] == 1710086400
        assert "deviceId" not in body


# ---------------------------------------------------------------------------
# device-details
# ---------------------------------------------------------------------------


class TestDeviceDetails:
    @respx.mock
    def test_success(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/device/getdetails").mock(
            return_value=httpx.Response(200, json=MOCK_DEVICE_DETAILS)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "device-details",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/device/getdetails").mock(
            return_value=httpx.Response(200, json=MOCK_DEVICE_DETAILS)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "device-details",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["clientVersion"] == "108.2.0.943"

    @respx.mock
    def test_request_body(self, runner):
        route = respx.post(f"{BASE}/api/v2/adem/users/device/getdetails").mock(
            return_value=httpx.Response(200, json=MOCK_DEVICE_DETAILS)
        )
        runner.invoke(
            app,
            [
                "dem",
                "users",
                "device-details",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["user"] == "alice@example.com"
        assert body["deviceId"] == "DEV-1234"
        assert body["starttime"] == 1710000000
        assert body["endtime"] == 1710086400


# ---------------------------------------------------------------------------
# npa-network-paths
# ---------------------------------------------------------------------------


class TestNpaNetworkPaths:
    @respx.mock
    def test_success(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/npa/getnetworkpaths").mock(
            return_value=httpx.Response(200, json=MOCK_NPA_NETWORK_PATHS)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "npa-network-paths",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--npa-host",
                "10.100.12.4",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/npa/getnetworkpaths").mock(
            return_value=httpx.Response(200, json=MOCK_NPA_NETWORK_PATHS)
        )
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "npa-network-paths",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--npa-host",
                "10.100.12.4",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "nodes" in data
        assert "edges" in data

    @respx.mock
    def test_request_body_includes_npa_host(self, runner):
        route = respx.post(f"{BASE}/api/v2/adem/users/npa/getnetworkpaths").mock(
            return_value=httpx.Response(200, json=MOCK_NPA_NETWORK_PATHS)
        )
        runner.invoke(
            app,
            [
                "dem",
                "users",
                "npa-network-paths",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--npa-host",
                "10.100.12.4",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["npaHost"] == "10.100.12.4"
        assert body["user"] == "alice@example.com"
        assert body["deviceId"] == "DEV-1234"


# ---------------------------------------------------------------------------
# diagnose
# ---------------------------------------------------------------------------


class TestDiagnose:
    def _mock_all_endpoints(self):
        """Set up respx mocks for all endpoints used by diagnose."""
        respx.post(f"{BASE}/api/v2/adem/users/getinfo").mock(return_value=httpx.Response(200, json=MOCK_INFO))
        respx.post(f"{BASE}/api/v2/adem/users/getapplications").mock(
            return_value=httpx.Response(200, json=MOCK_APPLICATIONS)
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getlist").mock(return_value=httpx.Response(200, json=MOCK_DEVICES))
        respx.post(f"{BASE}/api/v2/adem/users/device/getdetails").mock(
            return_value=httpx.Response(200, json=MOCK_DEVICE_DETAILS)
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getaggregatedscores").mock(
            return_value=httpx.Response(200, json=MOCK_SCORES)
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getrca").mock(return_value=httpx.Response(200, json=MOCK_RCA))

    def _mock_npa_endpoints(self):
        """Set up respx mocks for NPA endpoints."""
        respx.post(f"{BASE}/api/v2/adem/users/npa/getnpahosts").mock(
            return_value=httpx.Response(200, json=MOCK_NPA_HOSTS)
        )
        respx.post(f"{BASE}/api/v2/adem/users/npa/getnetworkpaths").mock(
            return_value=httpx.Response(200, json=MOCK_NPA_NETWORK_PATHS)
        )

    @respx.mock
    def test_diagnose_single_device(self, runner):
        """With --device-id, should skip device/getlist and query the specified device."""
        self._mock_all_endpoints()
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        # getlist should NOT be called when --device-id is specified
        getlist_calls = [c for c in respx.calls if "/device/getlist" in str(c.request.url)]
        assert len(getlist_calls) == 0
        # getdetails should be called for the specified device
        detail_calls = [c for c in respx.calls if "/device/getdetails" in str(c.request.url)]
        assert len(detail_calls) == 1

    @respx.mock
    def test_diagnose_auto_discover(self, runner):
        """Without --device-id, should call device/getlist and query each device."""
        self._mock_all_endpoints()
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        # getlist should be called
        getlist_calls = [c for c in respx.calls if "/device/getlist" in str(c.request.url)]
        assert len(getlist_calls) == 1

    @respx.mock
    def test_diagnose_with_npa(self, runner):
        """--include-npa should trigger NPA host and network path calls."""
        self._mock_all_endpoints()
        self._mock_npa_endpoints()
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
                "--include-npa",
            ],
        )
        assert result.exit_code == 0
        npa_calls = [c for c in respx.calls if "/npa/getnpahosts" in str(c.request.url)]
        assert len(npa_calls) == 1
        path_calls = [c for c in respx.calls if "/npa/getnetworkpaths" in str(c.request.url)]
        assert len(path_calls) == 1

    @respx.mock
    def test_diagnose_json_output(self, runner):
        """JSON output should contain nested user_info, applications, devices."""
        self._mock_all_endpoints()
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "user_info" in data
        assert "applications" in data
        assert "devices" in data
        assert len(data["devices"]) == 1
        assert data["devices"][0]["device_id"] == "DEV-1234"
        assert "details" in data["devices"][0]
        assert "scores" in data["devices"][0]
        assert "rca" in data["devices"][0]

    @respx.mock
    def test_diagnose_with_application(self, runner):
        """--application should filter the applications list."""
        self._mock_all_endpoints()
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
                "--application",
                "Gmail",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        apps = data.get("applications", [])
        if isinstance(apps, dict):
            apps = apps.get("data", [])
        # Should filter to only Gmail
        assert len(apps) == 1
        assert "Gmail" in apps[0]["appName"]

    @respx.mock
    def test_diagnose_partial_failure(self, runner):
        """If one sub-API fails, the command should still succeed with partial data."""
        respx.post(f"{BASE}/api/v2/adem/users/getinfo").mock(return_value=httpx.Response(200, json=MOCK_INFO))
        # getapplications returns 404
        respx.post(f"{BASE}/api/v2/adem/users/getapplications").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getdetails").mock(
            return_value=httpx.Response(200, json=MOCK_DEVICE_DETAILS)
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getaggregatedscores").mock(
            return_value=httpx.Response(200, json=MOCK_SCORES)
        )
        respx.post(f"{BASE}/api/v2/adem/users/device/getrca").mock(return_value=httpx.Response(200, json=MOCK_RCA))
        result = runner.invoke(
            app,
            [
                "-o",
                "json",
                "dem",
                "users",
                "diagnose",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0
        # Output may contain WARNING/Suggestion lines on stderr mixed in;
        # extract the JSON object which starts with '{'
        raw = result.output.strip()
        json_start = raw.index("{")
        data = json.loads(raw[json_start:])
        # user_info should be present
        assert data["user_info"] is not None
        # applications should be None due to 404
        assert data["applications"] is None
        # device data should still be present
        assert len(data["devices"]) == 1


# ---------------------------------------------------------------------------
# Existing ADEM command regression
# ---------------------------------------------------------------------------


class TestExistingAdemRegression:
    @respx.mock
    def test_devices_still_works(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/device/getlist").mock(return_value=httpx.Response(200, json=MOCK_DEVICES))
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "devices",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_info_still_works(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/getinfo").mock(return_value=httpx.Response(200, json=MOCK_INFO))
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "info",
                "--user",
                "alice@example.com",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    @respx.mock
    def test_scores_still_works(self, runner):
        respx.post(f"{BASE}/api/v2/adem/users/device/getaggregatedscores").mock(
            return_value=httpx.Response(200, json=MOCK_SCORES)
        )
        result = runner.invoke(
            app,
            [
                "dem",
                "users",
                "scores",
                "--user",
                "alice@example.com",
                "--device-id",
                "DEV-1234",
                "--start-time",
                "1710000000",
                "--end-time",
                "1710086400",
            ],
        )
        assert result.exit_code == 0

    def test_dem_users_help_shows_new_commands(self, runner):
        result = runner.invoke(app, ["dem", "users", "--help"])
        assert result.exit_code == 0
        for cmd in ["applications", "device-details", "npa-network-paths", "diagnose"]:
            assert cmd in result.output
