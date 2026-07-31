"""Tests for incident commands, focused on 'incidents update'.

The update API is unusually easy to call incorrectly: it answers HTTP 200 both for
input it rejected and for payload entries it discarded, and it distinguishes an
incident ID from an object ID only by which key you put it under. These tests pin
down the request the CLI builds and the failures it must surface.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.main import app

BASE = "https://test.goskope.com"
UPDATE_URL = f"{BASE}/api/v2/incidents/update"

# Larger than 2**53, like a real incident ID.
INCIDENT_ID = "1807262583165050077"
OBJECT_ID = "hash_user@example.com_4d9112d50346e25c84a3b357fc054d2f_2bcd4a9b6568"

OK_ONE = {"ok": 1, "result": "1"}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("NETSKOPE_TENANT", "test.goskope.com")
    monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken123")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _entry(route):
    """Return the single payload entry the CLI sent."""
    body = json.loads(route.calls[0].request.content)
    assert len(body["payload"]) == 1
    return body["payload"][0]


def _message(result) -> str:
    """Everything the user would see, lowercased.

    CliRunner drives the Typer app directly rather than the cli() wrapper that
    renders NetskopeError, so a raised error lands on result.exception instead of
    result.output. Check both.
    """
    return (result.output + "\n" + str(result.exception or "")).lower()


# ---------------------------------------------------------------------------
# incidents update — targeting a single incident
# ---------------------------------------------------------------------------


class TestUpdateByIncidentId:
    @respx.mock
    def test_sends_incident_id_not_object_id(self, runner):
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "in_progress",
                "--user",
                "analyst@example.com",
            ],
        )
        assert result.exit_code == 0
        entry = _entry(route)
        # Putting the incident ID under object_id is the bug this command had: the
        # tenant matches nothing and answers 500 "please try later".
        assert "object_id" not in entry
        assert entry["field"] == "status"
        assert entry["new_value"] == "in_progress"
        assert entry["user"] == "analyst@example.com"

    @respx.mock
    def test_incident_id_serialises_as_json_integer(self, runner):
        """A quoted ID is rejected with 'incident_id attribute needs to be integer'."""
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "analyst@example.com",
            ],
        )
        raw = route.calls[0].request.content.decode()
        assert f'"incident_id": {INCIDENT_ID}' in raw.replace('"incident_id":', '"incident_id": ')
        assert f'"{INCIDENT_ID}"' not in raw
        # Full precision survives: the ID exceeds 2**53 and must not be rounded.
        assert _entry(route)["incident_id"] == int(INCIDENT_ID)

    @respx.mock
    def test_old_value_is_accepted_but_warned_about(self, runner):
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--old-value",
                "new",
                "--new-value",
                "resolved",
                "--user",
                "analyst@example.com",
            ],
        )
        assert result.exit_code == 0
        assert "old_value" not in _entry(route)
        assert "ignored" in _message(result)

    def test_rejects_non_numeric_id(self, runner):
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                "INC-123",
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "analyst@example.com",
            ],
        )
        assert result.exit_code != 0
        assert "--object-id" in _message(result)

    def test_requires_a_target(self, runner):
        result = runner.invoke(
            app,
            ["incidents", "update", "--field", "status", "--new-value", "closed", "--user", "a@b.com"],
        )
        assert result.exit_code != 0

    def test_rejects_both_targets(self, runner):
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--object-id",
                OBJECT_ID,
                "--field",
                "status",
                "--old-value",
                "new",
                "--new-value",
                "closed",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "not both" in _message(result)


# ---------------------------------------------------------------------------
# incidents update — value checking
# ---------------------------------------------------------------------------


class TestUpdateValueValidation:
    def test_rejects_unknown_status(self, runner):
        """The tenant stores an unrecognised status verbatim, so catch it here."""
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "Closed",  # wrong case; the API would accept and store it
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "in_progress" in _message(result)

    def test_rejects_lowercase_severity(self, runner):
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "severity",
                "--new-value",
                "high",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "critical" in _message(result)

    @respx.mock
    def test_force_bypasses_value_check(self, runner):
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "awaiting_legal",
                "--user",
                "a@b.com",
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert _entry(route)["new_value"] == "awaiting_legal"

    @respx.mock
    def test_assignee_value_is_not_constrained(self, runner):
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "assignee",
                "--new-value",
                "responder@example.com",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code == 0
        assert _entry(route)["new_value"] == "responder@example.com"

    def test_rejects_unknown_field(self, runner):
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "priority",
                "--new-value",
                "high",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "severity" in _message(result)


# ---------------------------------------------------------------------------
# incidents update — bulk object path
# ---------------------------------------------------------------------------


class TestUpdateByObjectId:
    @respx.mock
    def test_sends_object_id_with_old_value(self, runner):
        route = respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                "--object-id",
                OBJECT_ID,
                "--field",
                "status",
                "--old-value",
                "new",
                "--new-value",
                "in_progress",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code == 0
        entry = _entry(route)
        assert entry["object_id"] == OBJECT_ID
        assert entry["old_value"] == "new"
        assert "incident_id" not in entry

    @respx.mock
    def test_warns_that_it_is_a_bulk_update(self, runner):
        respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                "--object-id",
                OBJECT_ID,
                "--field",
                "status",
                "--old-value",
                "new",
                "--new-value",
                "in_progress",
                "--user",
                "a@b.com",
            ],
        )
        assert "every incident" in _message(result)

    def test_requires_old_value(self, runner):
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                "--object-id",
                OBJECT_ID,
                "--field",
                "status",
                "--new-value",
                "in_progress",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "--old-value" in _message(result)


# ---------------------------------------------------------------------------
# incidents update — responses that look like success but are not
# ---------------------------------------------------------------------------


class TestUpdateResponseHandling:
    @respx.mock
    def test_ok_zero_on_http_200_is_a_failure(self, runner):
        respx.patch(UPDATE_URL).mock(
            return_value=httpx.Response(200, json={"ok": 0, "result": "incident_id attribute needs to be integer"})
        )
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "needs to be integer" in _message(result)

    @respx.mock
    def test_result_zero_is_a_failure(self, runner):
        """{"ok": 1, "result": "0"} means every payload entry was silently discarded."""
        respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json={"ok": 1, "result": "0"}))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "nothing was updated" in _message(result)

    @respx.mock
    def test_500_explains_that_retrying_will_not_help(self, runner):
        respx.patch(UPDATE_URL).mock(
            return_value=httpx.Response(500, json={"ok": 0, "result": "Failed to update incidents, please try later."})
        )
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code != 0
        assert "no incident matching" in _message(result)
        assert "will not help" in _message(result)

    @respx.mock
    def test_success_claims_acceptance_not_a_change(self, runner):
        """An ID matching no incident also returns {"ok": 1, "result": "1"}.

        `result` counts accepted payload entries, so the success line must not
        promise that an incident actually changed.
        """
        respx.patch(UPDATE_URL).mock(return_value=httpx.Response(200, json=OK_ONE))
        result = runner.invoke(
            app,
            [
                "incidents",
                "update",
                INCIDENT_ID,
                "--field",
                "status",
                "--new-value",
                "closed",
                "--user",
                "a@b.com",
            ],
        )
        assert result.exit_code == 0
        assert INCIDENT_ID in result.output
        assert "accepted" in _message(result)
        assert "changed" not in _message(result)
