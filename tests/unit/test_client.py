"""Tests for netskope_cli.core.client."""

from __future__ import annotations

import httpx
import pytest
import respx

from netskope_cli.core.client import NetskopeClient
from netskope_cli.core.exceptions import (
    APIError,
    AuthError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
)

BASE_URL = "https://tenant.goskope.com"


# ---------------------------------------------------------------------------
# Constructor and header building
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_base_url_strips_trailing_slash(self) -> None:
        client = NetskopeClient("https://tenant.goskope.com/")
        assert client.base_url == "https://tenant.goskope.com"

    def test_default_timeout(self) -> None:
        client = NetskopeClient(BASE_URL)
        assert client._timeout == 180

    def test_custom_timeout(self) -> None:
        client = NetskopeClient(BASE_URL, timeout=60)
        assert client._timeout == 60


class TestBuildHeaders:
    def test_default_headers(self) -> None:
        client = NetskopeClient(BASE_URL)
        headers = client._build_headers()
        assert headers["Accept"] == "application/json"
        assert headers["User-Agent"] == "netskope-cli"
        assert "Netskope-Api-Token" not in headers

    def test_api_token_header(self) -> None:
        client = NetskopeClient(BASE_URL, api_token="mytoken")
        headers = client._build_headers()
        assert headers["Netskope-Api-Token"] == "mytoken"


class TestBuildCookies:
    def test_no_cookies_by_default(self) -> None:
        client = NetskopeClient(BASE_URL)
        assert client._build_cookies() == {}

    def test_ci_session_cookie(self) -> None:
        client = NetskopeClient(BASE_URL, ci_session="session123")
        cookies = client._build_cookies()
        assert cookies["ci_session"] == "session123"


# ---------------------------------------------------------------------------
# _raise_for_status
# ---------------------------------------------------------------------------


class TestRaiseForStatus:
    def _client(self, **kwargs: str) -> NetskopeClient:
        """Create a minimal client instance for testing _raise_for_status."""
        return NetskopeClient(BASE_URL, **kwargs)

    @pytest.mark.parametrize("status_code", [200, 201, 204, 299])
    def test_2xx_does_not_raise(self, status_code: int) -> None:
        response = httpx.Response(status_code, json={"ok": True})
        self._client(api_token="tok")._raise_for_status(response)  # should not raise

    def test_401_raises_auth_error(self) -> None:
        response = httpx.Response(401, json={"message": "bad token"})
        with pytest.raises(AuthError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.details["status_code"] == 401

    def test_401_no_creds_specific_message(self) -> None:
        """When no credentials are configured, 401 should say so explicitly."""
        response = httpx.Response(401, json={"message": "Unauthorized"})
        with pytest.raises(AuthError) as exc_info:
            self._client()._raise_for_status(response)
        assert "No credentials were sent" in exc_info.value.message

    def test_403_raises_authorization_error(self) -> None:
        response = httpx.Response(403, json={"message": "forbidden"})
        with pytest.raises(AuthorizationError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.details["status_code"] == 403

    @pytest.mark.parametrize(
        "path, expected_fragment",
        [
            ("/api/v2/dspm/resources", "Data Security Posture Management"),
            ("/api/v2/spm/apps", "SaaS Security Posture Management"),
            ("/api/v2/dem/probes", "Digital Experience Management"),
            ("/api/v2/steering/config", "Steering"),
            ("/api/v2/npa/publishers", "Netskope Private Access"),
            ("/api/v2/policy/npa/rules", "NPA license"),
            ("/api/v2/rbi/apps", "Remote Browser Isolation"),
            ("/api/v2/dns/profiles", "DNS Security"),
            ("/api/v2/ips/rules", "Intrusion Prevention"),
            ("/api/v2/alerts/list", "required scopes"),  # fallback
        ],
    )
    def test_403_includes_license_hint(self, path: str, expected_fragment: str) -> None:
        """403 errors should include a contextual license/scope hint based on the URL path."""
        response = httpx.Response(403, json={"message": "forbidden"})
        with pytest.raises(AuthorizationError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response, request_path=path)
        assert expected_fragment in (exc_info.value.suggestion or "")

    def test_404_raises_not_found_error(self) -> None:
        response = httpx.Response(404, json={"message": "not found"})
        with pytest.raises(NotFoundError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.details["status_code"] == 404

    def test_429_raises_rate_limit_error(self) -> None:
        response = httpx.Response(
            429,
            json={"message": "rate limited"},
            headers={"Retry-After": "60"},
        )
        with pytest.raises(RateLimitError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.retry_after == 60

    def test_429_without_retry_after(self) -> None:
        response = httpx.Response(429, json={"message": "rate limited"})
        with pytest.raises(RateLimitError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.retry_after is None

    def test_500_raises_api_error(self) -> None:
        response = httpx.Response(500, json={"error": "internal"})
        with pytest.raises(APIError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert exc_info.value.status_code == 500

    def test_non_json_body(self) -> None:
        response = httpx.Response(502, text="Bad Gateway")
        with pytest.raises(APIError) as exc_info:
            self._client(api_token="tok")._raise_for_status(response)
        assert "Bad Gateway" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Async request methods (using respx)
# ---------------------------------------------------------------------------


class TestAsyncRequests:
    @respx.mock
    async def test_get_returns_json(self) -> None:
        route = respx.get(f"{BASE_URL}/api/v2/test").mock(return_value=httpx.Response(200, json={"data": "hello"}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.get("/api/v2/test")
        assert result == {"data": "hello"}
        assert route.called

    @respx.mock
    async def test_post_sends_json(self) -> None:
        route = respx.post(f"{BASE_URL}/api/v2/create").mock(return_value=httpx.Response(201, json={"id": 1}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.post("/api/v2/create", json_data={"name": "test"})
        assert result == {"id": 1}
        assert route.called

    @respx.mock
    async def test_delete_request(self) -> None:
        route = respx.delete(f"{BASE_URL}/api/v2/item/1").mock(return_value=httpx.Response(204))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.delete("/api/v2/item/1")
        assert result is None
        assert route.called

    @respx.mock
    async def test_put_request(self) -> None:
        route = respx.put(f"{BASE_URL}/api/v2/item/1").mock(return_value=httpx.Response(200, json={"updated": True}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.put("/api/v2/item/1", json_data={"name": "new"})
        assert result == {"updated": True}
        assert route.called

    @respx.mock
    async def test_patch_request(self) -> None:
        route = respx.patch(f"{BASE_URL}/api/v2/item/1").mock(return_value=httpx.Response(200, json={"patched": True}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.patch("/api/v2/item/1", json_data={"name": "patched"})
        assert result == {"patched": True}
        assert route.called

    @respx.mock
    async def test_get_with_params(self) -> None:
        route = respx.get(f"{BASE_URL}/api/v2/search").mock(return_value=httpx.Response(200, json={"results": []}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            result = await client.get("/api/v2/search", params={"q": "test"})
        assert result == {"results": []}
        assert route.called

    @respx.mock
    async def test_timeout_raises_api_error(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/slow").mock(side_effect=httpx.TimeoutException("timed out"))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            with pytest.raises(APIError, match="timed out"):
                await client.get("/api/v2/slow")

    @respx.mock
    async def test_connect_error_raises_api_error(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/down").mock(side_effect=httpx.ConnectError("Connection refused"))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            with pytest.raises(APIError, match="Connection failed"):
                await client.get("/api/v2/down")


# ---------------------------------------------------------------------------
# Synchronous wrapper
# ---------------------------------------------------------------------------


class TestSyncRequest:
    @respx.mock
    def test_request_sync(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/test").mock(return_value=httpx.Response(200, json={"sync": True}))
        client = NetskopeClient(BASE_URL, api_token="tok")
        result = client.request("GET", "/api/v2/test")
        assert result == {"sync": True}


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPaginate:
    @respx.mock
    async def test_paginate_single_page(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/items").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": 1}, {"id": 2}], "total": 2},
            )
        )
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            items = await client.paginate("/api/v2/items", page_size=100)
        assert items == [{"id": 1}, {"id": 2}]

    @respx.mock
    async def test_paginate_multiple_pages(self) -> None:
        call_count = 0

        def _side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            offset = int(request.url.params.get("offset", 0))
            if offset == 0:
                call_count += 1
                return httpx.Response(
                    200,
                    json={"data": [{"id": 1}, {"id": 2}], "total": 3},
                )
            else:
                call_count += 1
                return httpx.Response(
                    200,
                    json={"data": [{"id": 3}], "total": 3},
                )

        respx.get(f"{BASE_URL}/api/v2/items").mock(side_effect=_side_effect)
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            items = await client.paginate("/api/v2/items", page_size=2)
        assert len(items) == 3
        assert call_count == 2

    @respx.mock
    async def test_paginate_empty_response(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/items").mock(return_value=httpx.Response(200, json={"data": [], "total": 0}))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            items = await client.paginate("/api/v2/items")
        assert items == []

    @respx.mock
    async def test_paginate_none_response(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/items").mock(return_value=httpx.Response(204))
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            items = await client.paginate("/api/v2/items")
        assert items == []

    @respx.mock
    async def test_paginate_custom_keys(self) -> None:
        respx.get(f"{BASE_URL}/api/v2/items").mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"id": 1}], "count": 1},
            )
        )
        async with NetskopeClient(BASE_URL, api_token="tok") as client:
            items = await client.paginate(
                "/api/v2/items",
                data_key="results",
                total_key="count",
            )
        assert items == [{"id": 1}]


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_async_context_manager(self) -> None:
        async with NetskopeClient(BASE_URL) as client:
            assert client._client is not None
            assert not client._client.is_closed
        assert client._client is None

    async def test_close_idempotent(self) -> None:
        client = NetskopeClient(BASE_URL)
        await client.close()  # no-op, client was never opened
        assert client._client is None
