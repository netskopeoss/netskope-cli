"""Background version-check against PyPI with local caching.

Checks once per day whether a newer release of the ``netskope`` package is
available on PyPI. The network fetch runs in a background daemon thread so it
**never** adds latency to CLI startup. Results are cached in
``~/.cache/netskope/version_check.json``; the update notice is shown from the
cache on the *next* invocation.

Set ``NETSKOPE_NO_UPDATE_CHECK=1`` to disable entirely.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from rich.console import Console

from netskope_cli.core.config import cache_dir

_PYPI_URL = "https://pypi.org/pypi/netskope/json"
_CHECK_INTERVAL = 86_400  # 24 hours
_FETCH_TIMEOUT = 3.0  # seconds


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of ints for comparison."""
    return tuple(int(x) for x in v.strip().split("."))


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _cache_path() -> Path:
    return cache_dir() / "version_check.json"


def _read_cache() -> dict | None:
    """Return the cached check result, or *None* if missing / corrupt."""
    try:
        data = json.loads(_cache_path().read_text())
        if isinstance(data, dict) and "last_check" in data and "latest_version" in data:
            return data
    except Exception:
        pass
    return None


def _write_cache(latest_version: str) -> None:
    """Persist the check result to disk."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps({
            "last_check": time.time(),
            "latest_version": latest_version,
        }))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background PyPI fetch
# ---------------------------------------------------------------------------

def _fetch_latest_version() -> None:
    """Fetch the latest version from PyPI and write to cache. Never raises."""
    try:
        import httpx

        resp = httpx.get(_PYPI_URL, timeout=_FETCH_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        latest = resp.json()["info"]["version"]
        _write_cache(latest)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Install-method detection
# ---------------------------------------------------------------------------

def _detect_install_method() -> str:
    """Return the appropriate upgrade command for the user's install method."""
    # 1. Check the INSTALLER metadata file (most reliable).
    try:
        from importlib.metadata import distribution

        dist = distribution("netskope")
        installer = (dist.read_text("INSTALLER") or "").strip().lower()
        if installer == "uv":
            return "uv tool upgrade netskope"
    except Exception:
        pass

    # 2. Fall back to sys.executable path heuristics.
    exe = sys.executable or ""

    if "pipx" in exe:
        return "pipx upgrade netskope"

    if "/homebrew/" in exe or "/Cellar/" in exe:
        return "brew upgrade netskope"

    if "/uv/" in exe or ".local/share/uv" in exe:
        return "uv tool upgrade netskope"

    return "pip install --upgrade netskope"


def _stderr_is_tty() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def maybe_show_update_notice(console: Console, current_version: str, quiet: bool = False) -> None:
    """Show a one-liner upgrade notice if an update is available.

    - **Never blocks** — stale/missing cache triggers a background fetch;
      the notice appears on the *next* invocation.
    - Writes to *stderr* via the supplied Rich *console*.
    - Suppressed when ``NETSKOPE_NO_UPDATE_CHECK`` is set, ``quiet`` is
      ``True``, or stderr is not a TTY.
    """
    # --- Early exits ---
    if os.environ.get("NETSKOPE_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        return

    if quiet:
        return

    if not _stderr_is_tty():
        return

    # --- Read cache ---
    cache = _read_cache()

    if cache is None or (time.time() - cache["last_check"]) >= _CHECK_INTERVAL:
        # Stale or missing — refresh in background, show nothing this time.
        thread = threading.Thread(target=_fetch_latest_version, daemon=True)
        thread.start()
        return

    # --- Compare versions ---
    try:
        latest = cache["latest_version"]
        if _parse_version(latest) <= _parse_version(current_version):
            return
    except Exception:
        return

    # --- Show one-liner ---
    upgrade_cmd = _detect_install_method()
    console.print(
        f"[dim]Update available:[/dim] "
        f"[dim]{current_version}[/dim] → [bold green]{latest}[/bold green]"
        f" — Run: [cyan]{upgrade_cmd}[/cyan]"
    )
