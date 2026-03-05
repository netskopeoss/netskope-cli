"""Browser-based authentication for Netskope CLI.

Opens the user's Netskope tenant login page using Playwright, waits for
successful authentication, and captures the ci_session cookie for API use.
"""

from __future__ import annotations

import sys
import time
from urllib.parse import unquote

from netskope_cli.core.config import (
    get_active_profile,
    get_tenant_url,
    load_config,
    save_session_cookie,
)
from netskope_cli.core.exceptions import AuthError, ConfigError


def _is_session_authenticated(tenant_url: str, ci_session: str) -> bool:
    """Check if a ci_session cookie represents an authenticated session.

    Makes a lightweight API call to the tenant and checks for a non-login
    response (e.g. 200 on an API endpoint vs. a redirect to a login page).
    """
    import httpx

    try:
        resp = httpx.get(
            f"{tenant_url.rstrip('/')}/api/v2/rbac/roles/me",
            cookies={"ci_session": ci_session},
            headers={"Accept": "application/json", "User-Agent": "netskope-cli"},
            timeout=10,
            follow_redirects=False,
        )
        # Authenticated sessions return 200; unauthenticated ones return
        # 401, 403, or a 3xx redirect to the login page.
        return resp.status_code == 200
    except Exception:
        return False


def browser_login(
    tenant_url: str | None = None,
    profile: str | None = None,
    headless: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """Open a browser to the Netskope tenant login page and capture ci_session.

    Parameters
    ----------
    tenant_url:
        Full tenant URL (e.g. https://sedemo.goskope.com). If *None*, resolved
        from the active profile configuration.
    profile:
        Config profile name. Defaults to the active profile.
    headless:
        Run the browser in headless mode (useful for testing, but most SSO
        providers require a visible browser).
    timeout_seconds:
        Maximum time (in seconds) to wait for the user to complete login.

    Returns
    -------
    str
        The captured ``ci_session`` cookie value.

    Raises
    ------
    AuthError
        If login times out or the cookie cannot be captured.
    ConfigError
        If no tenant is configured.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthError(
            "Playwright is not installed.",
            suggestion="Run: pip install playwright && playwright install chromium",
        ) from exc

    cfg = load_config()
    profile_name = profile or get_active_profile(cfg)

    if tenant_url is None:
        tenant_url = get_tenant_url(profile_name, cfg)
        if not tenant_url:
            raise ConfigError(
                "No tenant configured.",
                suggestion="Run: netskope config set-tenant <hostname>",
            )

    # Ensure https://
    if not tenant_url.startswith("http"):
        tenant_url = f"https://{tenant_url}"

    login_url = tenant_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print(f"Opening browser for login at: {login_url}", file=sys.stderr)
        print("Please complete the login in the browser window...", file=sys.stderr)

        # Navigate to the tenant — this will redirect to the login/SSO page
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

        # Poll for a ci_session cookie that is actually authenticated.
        # The server may set ci_session before auth completes (e.g. as a
        # pre-auth session tracker), so we validate each candidate by
        # making a lightweight API call.
        ci_session = None
        last_checked_value = None
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            for cookie in context.cookies():
                if cookie["name"] == "ci_session" and cookie["value"]:
                    value = unquote(cookie["value"])
                    # Only validate if the value changed since last check
                    if value != last_checked_value:
                        last_checked_value = value
                        if _is_session_authenticated(login_url, value):
                            ci_session = value
                            break
            if ci_session:
                break

            page.wait_for_timeout(1000)  # Check every second

        browser.close()

    if not ci_session:
        raise AuthError(
            f"Login timed out after {timeout_seconds} seconds.",
            suggestion="Try again with --timeout for more time, or use API token auth instead.",
        )

    # Persist the session cookie
    save_session_cookie(ci_session, profile_name, cfg)
    print("Login successful! Session cookie saved.", file=sys.stderr)

    return ci_session


def browser_login_with_credentials(
    tenant_url: str,
    username: str,
    password: str,
    profile: str | None = None,
    headless: bool = True,
    timeout_seconds: int = 60,
) -> str:
    """Automated login using username/password (for testing/CI).

    Attempts to fill in login forms automatically. This works for tenants
    using direct Netskope login (not SSO). For SSO tenants, use
    :func:`browser_login` which opens an interactive browser.

    Parameters
    ----------
    tenant_url:
        Full tenant URL.
    username:
        Login username/email.
    password:
        Login password.
    profile:
        Config profile name.
    headless:
        Run browser headless (default True for automated login).
    timeout_seconds:
        Max seconds to wait for login to complete.

    Returns
    -------
    str
        The captured ``ci_session`` cookie value.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthError(
            "Playwright is not installed.",
            suggestion="Run: pip install playwright && playwright install chromium",
        ) from exc

    if not tenant_url.startswith("http"):
        tenant_url = f"https://{tenant_url}"

    login_url = tenant_url.rstrip("/")

    cfg = load_config()
    profile_name = profile or get_active_profile(cfg)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        page.goto(login_url, wait_until="networkidle", timeout=30000)

        # Try multiple common login form selectors
        _try_fill_credentials(page, username, password)

        # Wait for navigation after login
        ci_session = _wait_for_session(context, page, timeout_seconds, tenant_url=login_url)

        browser.close()

    if not ci_session:
        raise AuthError(
            "Automated login failed — could not capture session cookie.",
            suggestion="Try interactive login with: netskope auth login",
        )

    save_session_cookie(ci_session, profile_name, cfg)
    return ci_session


def _try_fill_credentials(page, username: str, password: str) -> None:
    """Try to find and fill login form fields using common selectors."""
    # Common username field selectors
    username_selectors = [
        'input[name="email"]',
        'input[name="username"]',
        'input[name="login"]',
        'input[type="email"]',
        'input[id="email"]',
        'input[id="username"]',
        'input[id="login"]',
        "#login-email",
        "#login-username",
        'input[placeholder*="email" i]',
        'input[placeholder*="user" i]',
    ]

    # Common password field selectors
    password_selectors = [
        'input[name="password"]',
        'input[type="password"]',
        'input[id="password"]',
        "#login-password",
    ]

    # Common submit button selectors
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        "#login-submit",
        'button:has-text("Sign In")',
        'button:has-text("Log In")',
        'button:has-text("Login")',
        'button:has-text("Submit")',
        'button:has-text("Next")',
    ]

    # Fill username
    for selector in username_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.fill(username)
                break
        except Exception:
            continue

    # Some login flows have a "Next" button after username
    page.wait_for_timeout(1000)
    for selector in submit_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(2000)
                break
        except Exception:
            continue

    # Fill password (may appear after username submit)
    page.wait_for_timeout(1000)
    for selector in password_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.fill(password)
                break
        except Exception:
            continue

    # Submit the login form
    page.wait_for_timeout(500)
    for selector in submit_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                break
        except Exception:
            continue


def _wait_for_session(context, page, timeout_seconds: int, tenant_url: str | None = None) -> str | None:
    """Poll for ci_session cookie after login form submission."""
    deadline = time.time() + timeout_seconds
    last_checked_value: str | None = None

    while time.time() < deadline:
        cookies = context.cookies()
        for cookie in cookies:
            if cookie["name"] == "ci_session" and cookie["value"]:
                value = unquote(cookie["value"])
                # Validate the session is actually authenticated, matching
                # the logic in browser_login() to avoid saving pre-auth cookies.
                if value != last_checked_value:
                    last_checked_value = value
                    if tenant_url and _is_session_authenticated(tenant_url, value):
                        return value
                    elif not tenant_url:
                        return value

        page.wait_for_timeout(1000)

    return None
