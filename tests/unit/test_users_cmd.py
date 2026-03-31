"""Tests for user and group management commands (User Management API + SCIM CRUD)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.main import app

BASE = "https://test.goskope.com"

MOCK_UM_USER = {
    "id": "user-123",
    "givenName": "Alice",
    "familyName": "Smith",
    "emails": ["alice@example.com"],
    "accounts": [
        {
            "scimId": "scim-456",
            "userName": "alice@example.com",
            "active": True,
            "deleted": False,
            "parentGroups": ["Engineering", "All Users"],
            "ou": "/",
            "provisioner": "SCIM",
        }
    ],
}

MOCK_UM_GROUP = {
    "id": "grp-789",
    "scimId": "scim-grp-789",
    "displayName": "Engineering",
    "userCount": 42,
    "provisioner": "SCIM",
    "deleted": False,
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
# users list
# ---------------------------------------------------------------------------


class TestUsersListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["users", "list"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output

    @respx.mock
    def test_list_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["userName"] == "alice@example.com"

    @respx.mock
    def test_list_with_filter(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        filter_json = '{"and": [{"emails": {"eq": "alice@example.com"}}]}'
        result = runner.invoke(app, ["users", "list", "--filter", filter_json])
        assert result.exit_code == 0
        # Verify the filter was sent in the POST body
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"and": [{"emails": {"eq": "alice@example.com"}}]}

    @respx.mock
    def test_list_with_pagination(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [], "total": 0})
        )
        result = runner.invoke(app, ["users", "list", "--limit", "50", "--offset", "10"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["paging"] == {"offset": 10, "limit": 50}

    def test_list_invalid_filter_json(self, runner):
        result = runner.invoke(app, ["users", "list", "--filter", "not json"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# users get
# ---------------------------------------------------------------------------


class TestUsersGetCommand:
    @respx.mock
    def test_get_by_email(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "get", "alice@example.com"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"and": [{"emails": {"eq": "alice@example.com"}}]}

    @respx.mock
    def test_get_by_username(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "get", "alice", "--by", "username"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"and": [{"userName": {"eq": "alice"}}]}

    @respx.mock
    def test_get_not_found(self, runner):
        respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [], "total": 0})
        )
        result = runner.invoke(app, ["users", "get", "nobody@example.com"])
        assert result.exit_code != 0

    @respx.mock
    def test_get_auto_detects_username_without_at(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "get", "alice"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"and": [{"userName": {"eq": "alice"}}]}


# ---------------------------------------------------------------------------
# groups list
# ---------------------------------------------------------------------------


class TestGroupsListCommand:
    @respx.mock
    def test_list_success(self, runner):
        respx.post(f"{BASE}/api/v2/users/getgroups").mock(
            return_value=httpx.Response(200, json={"groups": [MOCK_UM_GROUP], "total": 1})
        )
        result = runner.invoke(app, ["users", "groups", "list"])
        assert result.exit_code == 0
        assert "Engineering" in result.output

    @respx.mock
    def test_list_with_filter(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getgroups").mock(
            return_value=httpx.Response(200, json={"groups": [MOCK_UM_GROUP], "total": 1})
        )
        result = runner.invoke(app, ["users", "groups", "list", "--filter", '{"deleted": {"eq": false}}'])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"deleted": {"eq": False}}

    @respx.mock
    def test_list_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/users/getgroups").mock(
            return_value=httpx.Response(200, json={"groups": [MOCK_UM_GROUP], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "groups", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["displayName"] == "Engineering"


# ---------------------------------------------------------------------------
# groups get
# ---------------------------------------------------------------------------


class TestGroupsGetCommand:
    @respx.mock
    def test_get_by_name(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getgroups").mock(
            return_value=httpx.Response(200, json={"groups": [MOCK_UM_GROUP], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "groups", "get", "Engineering"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"displayName": {"eq": "Engineering"}}

    @respx.mock
    def test_get_not_found(self, runner):
        respx.post(f"{BASE}/api/v2/users/getgroups").mock(
            return_value=httpx.Response(200, json={"groups": [], "total": 0})
        )
        result = runner.invoke(app, ["users", "groups", "get", "NonExistent"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# groups members
# ---------------------------------------------------------------------------


class TestGroupsMembersCommand:
    @respx.mock
    def test_members_success(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["users", "groups", "members", "Engineering"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["filter"] == {"accounts.parentGroups": {"in": ["Engineering"]}}

    @respx.mock
    def test_members_with_pagination(self, runner):
        route = respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [], "total": 0})
        )
        result = runner.invoke(app, ["users", "groups", "members", "Engineering", "--limit", "50", "--offset", "10"])
        assert result.exit_code == 0
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["query"]["paging"] == {"offset": 10, "limit": 50}

    @respx.mock
    def test_members_json_output(self, runner):
        respx.post(f"{BASE}/api/v2/users/getusers").mock(
            return_value=httpx.Response(200, json={"users": [MOCK_UM_USER], "total": 1})
        )
        result = runner.invoke(app, ["-o", "json", "users", "groups", "members", "Engineering"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# SCIM CRUD smoke tests (verify unchanged)
# ---------------------------------------------------------------------------


class TestScimCrudUnchanged:
    @respx.mock
    def test_user_create(self, runner):
        respx.post(f"{BASE}/api/v2/scim/Users").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "new-user-id",
                    "userName": "new@example.com",
                    "active": True,
                    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                },
            )
        )
        result = runner.invoke(app, ["users", "create", "--username", "new@example.com", "--email", "new@example.com"])
        assert result.exit_code == 0

    @respx.mock
    def test_group_create(self, runner):
        respx.post(f"{BASE}/api/v2/scim/Groups").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "new-group-id",
                    "displayName": "TestGroup",
                    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
                },
            )
        )
        result = runner.invoke(app, ["users", "groups", "create", "TestGroup"])
        assert result.exit_code == 0
