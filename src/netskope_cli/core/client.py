"""Async HTTP client for the Netskope API.

Provides ``NetskopeClient``, an httpx-based client with typed error handling,
connection pooling, pagination support, and a synchronous convenience wrapper
for use in CLI command handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from netskope_cli.core.exceptions import (
    APIError,
    AuthError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# Maps URL path substrings to contextual hints for 404 errors.
_404_SUGGESTIONS: list[tuple[str, str]] = [
    ("/steering/globalconfig", "The Steering Global Config API may not be available on this tenant or license."),
    ("/spm/", "SPM requires a SaaS Security Posture Management license."),
    ("/dspm/", "DSPM requires a Data Security Posture Management license."),
    ("/devices/", "The Devices API may not be available on this tenant or license."),
    ("/rbi/", "RBI requires a Remote Browser Isolation license."),
    ("/dem/", "DEM requires a Digital Experience Management license."),
]
_404_FALLBACK = "This API endpoint may not be available on your tenant or license plan."


class NetskopeClient:
    """HTTP client for communicating with the Netskope REST API.

    Parameters
    ----------
    base_url:
        Tenant URL, e.g. ``https://mytenant.goskope.com``.
    api_token:
        Netskope REST API v2 token.  Mutually exclusive with *ci_session*.
    ci_session:
        Browser session cookie value (``ci_session``).  Mutually exclusive
        with *api_token*.
    timeout:
        Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        ci_session: str | None = None,
        timeout: int = 180,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._ci_session = ci_session
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "netskope-cli",
        }
        if self._api_token:
            headers["Netskope-Api-Token"] = self._api_token
        return headers

    def _build_cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if self._ci_session:
            cookies["ci_session"] = self._ci_session
        return cookies

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared ``AsyncClient``, creating it on first use."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._build_headers(),
                cookies=self._build_cookies(),
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "NetskopeClient":
        await self._get_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response, *, request_path: str = "") -> None:
        """Translate HTTP status codes into typed exceptions."""
        status = response.status_code

        if 200 <= status < 300:
            return

        # Attempt to pull a human-readable message from the JSON body.
        try:
            body = response.json()
            # Check nested status.message first, then top-level keys.
            if isinstance(body, dict):
                status_obj = body.get("status")
                if isinstance(status_obj, dict) and status_obj.get("message"):
                    message = status_obj["message"]
                elif body.get("message"):
                    message = body["message"]
                elif body.get("error"):
                    message = body["error"]
                else:
                    message = response.text
            else:
                message = response.text or f"HTTP {status}"
        except Exception:
            body = {}
            message = response.text or f"HTTP {status}"

        details = {"status_code": status, "body": body}

        if status == 401:
            if not self._api_token and not self._ci_session:
                raise AuthError(
                    "No credentials were sent with this request.",
                    suggestion=(
                        "You need to set up authentication. Choose one:\n"
                        "  1. Set an API token:     netskope config set-token\n"
                        "  2. Login via browser:    netskope auth login\n"
                        '  3. Use an env variable:  export NETSKOPE_API_TOKEN="your-token"\n'
                        "\n"
                        "  Get a token from: Settings > Tools > REST API v2 in your Netskope admin console."
                    ),
                    details=details,
                )
            raise AuthError(
                f"Authentication failed (HTTP {status}): {message}",
                suggestion=(
                    "Your token may be invalid or expired. Try:\n"
                    "  • Check status:    netskope auth status\n"
                    "  • Replace token:   netskope config set-token\n"
                    "  • Test connection: netskope config test"
                ),
                details=details,
            )
        if status == 403:
            raise AuthorizationError(
                f"Forbidden (HTTP {status}): {message}",
                details=details,
            )
        if status == 404:
            # Find a contextual suggestion based on the request path.
            suggestion_404 = _404_FALLBACK
            for pattern, hint in _404_SUGGESTIONS:
                if pattern in request_path:
                    suggestion_404 = hint
                    break
            raise NotFoundError(
                f"Not found (HTTP {status}): {message}",
                suggestion=suggestion_404,
                details=details,
            )
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                f"Rate limit exceeded (HTTP {status}): {message}",
                retry_after=int(retry_after) if retry_after else None,
                details=details,
            )

        suggestion = None
        if status == 400 and "syntax error" in message.lower():
            suggestion = "Run 'netskope docs jql' for query syntax help."

        raise APIError(
            f"API error (HTTP {status}): {message}",
            status_code=status,
            suggestion=suggestion,
            details=details,
        )

    @staticmethod
    def _parse_json(response: httpx.Response) -> Any:
        """Return parsed JSON, falling back to ``None`` for empty bodies."""
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # ------------------------------------------------------------------
    # Core async HTTP verbs
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Send an HTTP request, handle errors, and return parsed data."""
        client = await self._get_client()
        url = path if path.startswith("http") else path

        logger.debug(
            "HTTP %s %s params=%s json_keys=%s",
            method.upper(),
            url,
            {k: v for k, v in (params or {}).items() if k not in ("token", "api_token", "password", "secret")},
            list((json_data or {}).keys()) if isinstance(json_data, dict) else type(json_data).__name__,
        )

        try:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_data,
            )
        except httpx.TimeoutException as exc:
            raise APIError(
                f"Request timed out after {self._timeout}s: {method.upper()} {url}",
                suggestion="Increase the timeout with --timeout or check network connectivity.",
                details={"method": method, "path": url},
            ) from exc
        except httpx.ConnectError as exc:
            raise APIError(
                f"Connection failed: {exc}",
                suggestion=f"Verify that {self.base_url} is reachable.",
                details={"method": method, "path": url},
            ) from exc

        logger.debug(
            "HTTP %s %s -> %s (%d bytes)",
            method.upper(),
            url,
            response.status_code,
            len(response.content),
        )

        self._raise_for_status(response, request_path=url)
        return self._parse_json(response)

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send an async GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Send an async POST request."""
        return await self._request("POST", path, params=params, json_data=json_data)

    async def put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Send an async PUT request."""
        return await self._request("PUT", path, params=params, json_data=json_data)

    async def patch(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Send an async PATCH request."""
        return await self._request("PATCH", path, params=params, json_data=json_data)

    async def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send an async DELETE request."""
        return await self._request("DELETE", path, params=params)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    async def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 100,
        data_key: str = "data",
        offset_key: str = "offset",
        limit_key: str = "limit",
        total_key: str = "total",
    ) -> list[Any]:
        """Fetch all pages of a paginated endpoint and return a flat list.

        The method keeps requesting the next page until either the total is
        reached or the server returns fewer items than *page_size*.

        Parameters
        ----------
        path:
            API path to query.
        params:
            Extra query parameters (merged with pagination params).
        page_size:
            Number of records per page.
        data_key:
            JSON key that holds the list of records.
        offset_key:
            Query-parameter name for the page offset.
        limit_key:
            Query-parameter name for the page size.
        total_key:
            JSON key that holds the total record count.
        """
        all_items: list[Any] = []
        offset = 0

        while True:
            page_params = {**(params or {}), offset_key: offset, limit_key: page_size}
            data = await self.get(path, params=page_params)

            if data is None:
                break

            items = data.get(data_key, []) if isinstance(data, dict) else []
            all_items.extend(items)

            total = data.get(total_key) if isinstance(data, dict) else None

            # Stop when we've collected everything or the page was short.
            if not items or len(items) < page_size:
                break
            if total is not None and len(all_items) >= total:
                break

            offset += len(items)

        return all_items

    # ------------------------------------------------------------------
    # Synchronous convenience wrapper
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Synchronous wrapper around :meth:`_request` for CLI handlers.

        Uses ``asyncio.run()`` to execute the async call in a fresh event
        loop, then tears down the client cleanly.
        """

        async def _run() -> Any:
            try:
                return await self._request(method, path, params=params, json_data=json_data)
            finally:
                await self.close()

        return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Shared client-builder for command modules
# ---------------------------------------------------------------------------

_NO_CREDS_SUGGESTION = (
    "You need to set up authentication. Choose one:\n"
    "  1. Set an API token:     netskope config set-token\n"
    "  2. Login via browser:    netskope auth login\n"
    '  3. Use an env variable:  export NETSKOPE_API_TOKEN="your-token"\n'
    "\n"
    "  Get a token from: Settings > Tools > REST API v2 in your Netskope admin console."
)

_NO_TENANT_SUGGESTION = (
    "You need to configure a tenant first. Choose one:\n"
    "  1. Set tenant:           netskope config set-tenant HOSTNAME\n"
    '  2. Use an env variable:  export NETSKOPE_TENANT="mytenant.goskope.com"'
)


def build_client(ctx: Any) -> "NetskopeClient":
    """Build a NetskopeClient from the Typer context with helpful error messages.

    This is the shared implementation for the ``_build_client()`` helpers in
    every command module.  It resolves the profile, tenant, and credentials
    using the standard configuration hierarchy and raises clear errors with
    actionable suggestions when something is missing.
    """
    from netskope_cli.core.config import (
        get_active_profile,
        get_api_token,
        get_session_cookie,
        get_tenant_url,
        load_config,
    )
    from netskope_cli.core.exceptions import ConfigError

    state = ctx.obj
    profile_name = state.profile if state else "default"

    cfg = load_config()
    active = get_active_profile(cfg, cli_profile=profile_name)

    try:
        base_url = get_tenant_url(profile=active, cfg=cfg)
    except ValueError:
        raise ConfigError(
            f"No tenant configured for profile '{active}'.",
            suggestion=_NO_TENANT_SUGGESTION,
        )

    api_token = get_api_token(profile=active, cfg=cfg)
    ci_session = get_session_cookie(profile=active, cfg=cfg)

    if not api_token and not ci_session:
        raise ConfigError(
            f"No credentials configured for profile '{active}'.",
            suggestion=_NO_CREDS_SUGGESTION,
        )

    return NetskopeClient(
        base_url=base_url,
        api_token=api_token,
        ci_session=ci_session,
    )
