"""Tenant status / dashboard command for the Netskope CLI.

Shows a quick overview of tenant health: alert counts, publisher status,
private app count, user count, and recent event activity — all in one shot.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import spinner
from netskope_cli.utils.helpers import validate_time_range

status_app = typer.Typer(name="status", invoke_without_command=True)

_EVENT_LIMIT = 10000  # high enough for accurate daily counts


def _build_client(ctx: typer.Context) -> tuple[NetskopeClient, str]:
    """Return (client, base_url)."""
    client = build_client(ctx)
    return client, client.base_url


# ------------------------------------------------------------------
# Async data fetching — all API calls run concurrently
# ------------------------------------------------------------------


async def _fetch_event_count(
    base_url: str, headers: dict, path: str, params: dict, errors: list[str] | None = None, cookies: dict | None = None
) -> int | None:
    """Fetch event count from a datasearch endpoint."""
    import httpx

    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, cookies=cookies, timeout=60) as c:
            resp = await c.get(path, params=params)
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"{path}: HTTP {resp.status_code}")
                return None
            data = resp.json()
            if isinstance(data, dict):
                status = data.get("status")
                if isinstance(status, dict):
                    count = status.get("count")
                    if count is not None:
                        return int(count)
                result = data.get("result")
                if isinstance(result, list):
                    return len(result)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{path}: {exc}")
    return None


async def _fetch_resource_total(
    base_url: str, headers: dict, path: str, params: dict, errors: list[str] | None = None, cookies: dict | None = None
) -> int | None:
    """Fetch total from a resource endpoint that returns a 'total' field."""
    import httpx

    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, cookies=cookies, timeout=60) as c:
            resp = await c.get(path, params=params)
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"{path}: HTTP {resp.status_code}")
                return None
            data = resp.json()
            if isinstance(data, dict):
                total = data.get("total")
                if total is not None:
                    return int(total)
                # SCIM-style
                total_results = data.get("totalResults")
                if total_results is not None:
                    return int(total_results)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{path}: {exc}")
    return None


async def _fetch_publishers(
    base_url: str, headers: dict, errors: list[str] | None = None, cookies: dict | None = None
) -> dict[str, Any]:
    """Fetch publisher list with status breakdown."""
    import httpx

    result: dict[str, Any] = {"total": None, "connected": None, "not_connected": None}
    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, cookies=cookies, timeout=60) as c:
            resp = await c.get("/api/v2/infrastructure/publishers", params={"limit": 500, "offset": 0})
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"/api/v2/infrastructure/publishers: HTTP {resp.status_code}")
                return result
            data = resp.json()
            total = data.get("total", 0)
            result["total"] = int(total)
            pubs = data.get("data", {}).get("publishers", [])
            connected = sum(1 for p in pubs if p.get("status") == "connected")
            result["connected"] = connected
            result["not_connected"] = len(pubs) - connected
    except Exception as exc:
        if errors is not None:
            errors.append(f"/api/v2/infrastructure/publishers: {exc}")
    return result


async def _fetch_list_count(
    base_url: str,
    headers: dict,
    path: str,
    params: dict,
    errors: list[str] | None = None,
    cookies: dict | None = None,
    count_key: str | None = None,
) -> int | None:
    """Fetch a count from an endpoint that returns a list or total field.

    Tries, in order: ``count_key`` in the response dict, ``total``, ``totalResults``,
    ``len(data)``, ``len(result)``, ``len(Resources)``.
    """
    import httpx

    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, cookies=cookies, timeout=60) as c:
            resp = await c.get(path, params=params)
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"{path}: HTTP {resp.status_code}")
                return None
            data = resp.json()
            if isinstance(data, dict):
                if count_key and count_key in data:
                    return int(data[count_key])
                for key in ("total", "totalResults", "count"):
                    if key in data:
                        return int(data[key])
                for key in ("data", "result", "Resources", "roles", "tunnels"):
                    if key in data and isinstance(data[key], list):
                        return len(data[key])
            if isinstance(data, list):
                return len(data)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{path}: {exc}")
    return None


async def _fetch_ips_enabled(
    base_url: str, headers: dict, errors: list[str] | None = None, cookies: dict | None = None
) -> bool | None:
    """Check whether IPS is enabled on the tenant."""
    import httpx

    try:
        async with httpx.AsyncClient(base_url=base_url, headers=headers, cookies=cookies, timeout=60) as c:
            resp = await c.get("/api/v2/ips/status")
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"/api/v2/ips/status: HTTP {resp.status_code}")
                return None
            data = resp.json()
            if isinstance(data, dict):
                ips_data = data.get("data", {})
                if isinstance(ips_data, dict):
                    return bool(ips_data.get("web", False) or ips_data.get("nonweb", False))
                return bool(data.get("enabled", False))
    except Exception as exc:
        if errors is not None:
            errors.append(f"/api/v2/ips/status: {exc}")
    return None


async def _gather_status(
    base_url: str,
    headers: dict,
    time_params: dict,
    cookies: dict | None = None,
    extended: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Run all API calls concurrently and return (metrics, errors)."""
    event_types = ["alert", "application", "network", "page", "incident"]
    event_params = {**time_params, "limit": _EVENT_LIMIT}
    errors: list[str] = []

    tasks = []
    # Event counts
    for etype in event_types:
        tasks.append(
            _fetch_event_count(
                base_url, headers, f"/api/v2/events/datasearch/{etype}", event_params, errors, cookies=cookies
            )
        )
    # Publishers (full detail)
    tasks.append(_fetch_publishers(base_url, headers, errors, cookies=cookies))
    # Private apps total
    tasks.append(
        _fetch_resource_total(
            base_url, headers, "/api/v2/steering/apps/private", {"limit": 1, "offset": 0}, errors, cookies=cookies
        )
    )
    # Users total
    tasks.append(_fetch_resource_total(base_url, headers, "/api/v2/scim/Users", {"count": 1}, errors, cookies=cookies))

    # Extended metrics
    ext_keys: list[str] = []
    if extended:
        ext_endpoints: list[tuple[str, str, dict, str | None]] = [
            ("groups_scim", "/api/v2/scim/Groups", {"count": 1}, None),
            ("url_lists", "/api/v2/policy/urllist", {}, None),
            ("npa_policy_rules", "/api/v2/policy/npa/rules", {"limit": 1, "offset": 0}, None),
            ("ipsec_tunnels", "/api/v2/steering/ipsec/tunnels", {"limit": 1, "offset": 0}, None),
            ("rbac_roles", "/api/v2/rbac/roles", {}, None),
        ]
        for key, path, params, count_key in ext_endpoints:
            ext_keys.append(key)
            tasks.append(
                _fetch_list_count(base_url, headers, path, params, errors, cookies=cookies, count_key=count_key)
            )
        ext_keys.append("ips_enabled")
        tasks.append(_fetch_ips_enabled(base_url, headers, errors, cookies=cookies))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    metrics: dict[str, Any] = {}
    for i, etype in enumerate(event_types):
        val = results[i]
        metrics[f"{etype}_events_24h"] = val if isinstance(val, int) else None

    base_idx = len(event_types)
    pub_result = results[base_idx]
    metrics["publishers"] = pub_result if isinstance(pub_result, dict) else {"total": None}

    priv_apps = results[base_idx + 1]
    metrics["private_apps"] = priv_apps if isinstance(priv_apps, int) else None

    users = results[base_idx + 2]
    metrics["users"] = users if isinstance(users, int) else None

    # Extended metrics
    if extended:
        ext_start = base_idx + 3
        for i, key in enumerate(ext_keys):
            val = results[ext_start + i]
            if isinstance(val, BaseException):
                metrics[key] = None
            else:
                metrics[key] = val

    return metrics, errors


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------


def _fmt(value: int | None) -> str:
    """Format an integer with commas, or 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value:,}"


def _color_status(connected: int | None, total: int | None) -> Text:
    """Return a colored summary like '7 connected / 0 down'."""
    if total is None:
        return Text("N/A", style="dim")
    parts = Text()
    parts.append(f"{total:,}", style="bold")
    parts.append(" total")
    if connected is not None:
        parts.append("  (")
        parts.append(f"{connected}", style="bold green")
        parts.append(" connected")
        not_conn = (total or 0) - (connected or 0)
        if not_conn > 0:
            parts.append(", ")
            parts.append(f"{not_conn}", style="bold red")
            parts.append(" down")
        parts.append(")")
    return parts


def _render_table(base_url: str, metrics: dict[str, Any], period: str, no_color: bool, extended: bool = False) -> None:
    """Render the status dashboard as a Rich table."""
    console = Console(no_color=no_color, stderr=True)

    # Infrastructure section
    infra_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
    infra_table.add_column("Resource", style="bold", min_width=16)
    infra_table.add_column("Status")

    pub = metrics.get("publishers", {})
    infra_table.add_row("Publishers", _color_status(pub.get("connected"), pub.get("total")))
    infra_table.add_row("Private Apps", Text(_fmt(metrics.get("private_apps"))))
    infra_table.add_row("Users (SCIM)", Text(_fmt(metrics.get("users"))))

    # Events section
    events_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
    events_table.add_column("Event Type", style="bold", min_width=16)
    events_table.add_column("Count")

    event_labels = [
        ("alert_events_24h", "Alerts"),
        ("incident_events_24h", "Incidents"),
        ("application_events_24h", "Application"),
        ("network_events_24h", "Network"),
        ("page_events_24h", "Page"),
    ]
    for key, label in event_labels:
        val = metrics.get(key)
        count_text = _fmt(val)
        style = ""
        if val is not None and val > 0 and key in ("alert_events_24h", "incident_events_24h"):
            style = "yellow"
        events_table.add_row(label, Text(count_text, style=style))

    # Assemble into panels
    tenant_text = Text()
    tenant_text.append("Tenant: ", style="bold")
    tenant_text.append(base_url, style="cyan underline")

    output = Table.grid(padding=(1, 0))
    output.add_row(tenant_text)
    output.add_row(Text("Infrastructure", style="bold magenta"))
    output.add_row(infra_table)
    output.add_row(Text(f"\nEvents (last {period})", style="bold magenta"))
    output.add_row(events_table)

    # Extended configuration section
    if extended:
        config_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False, show_edge=False)
        config_table.add_column("Resource", style="bold", min_width=20)
        config_table.add_column("Count")

        config_labels = [
            ("groups_scim", "SCIM Groups"),
            ("url_lists", "URL Lists"),
            ("npa_policy_rules", "NPA Policy Rules"),
            ("ipsec_tunnels", "IPsec Tunnels"),
            ("rbac_roles", "RBAC Roles"),
        ]
        for key, label in config_labels:
            config_table.add_row(label, Text(_fmt(metrics.get(key))))

        ips_val = metrics.get("ips_enabled")
        if ips_val is not None:
            ips_text = Text("Enabled" if ips_val else "Disabled", style="green" if ips_val else "dim")
        else:
            ips_text = Text("N/A", style="dim")
        config_table.add_row("IPS", ips_text)

        output.add_row(Text("\nConfiguration", style="bold magenta"))
        output.add_row(config_table)

    panel = Panel(output, title="[bold]Tenant Status[/bold]", border_style="blue", expand=False, padding=(1, 2))
    console.print(panel)


def _render_json(base_url: str, metrics: dict[str, Any], period: str, extended: bool = False) -> None:
    """Render the status as JSON."""
    pub = metrics.get("publishers", {})
    output: dict[str, Any] = {
        "tenant": base_url,
        "period": period,
        "infrastructure": {
            "publishers": {
                "total": pub.get("total"),
                "connected": pub.get("connected"),
                "not_connected": pub.get("not_connected"),
            },
            "private_apps": metrics.get("private_apps"),
            "users_scim": metrics.get("users"),
        },
        "events": {
            "alerts": metrics.get("alert_events_24h"),
            "incidents": metrics.get("incident_events_24h"),
            "application": metrics.get("application_events_24h"),
            "network": metrics.get("network_events_24h"),
            "page": metrics.get("page_events_24h"),
        },
    }
    if extended:
        output["configuration"] = {
            "groups_scim": metrics.get("groups_scim"),
            "url_lists": metrics.get("url_lists"),
            "npa_policy_rules": metrics.get("npa_policy_rules"),
            "ipsec_tunnels": metrics.get("ipsec_tunnels"),
            "rbac_roles": metrics.get("rbac_roles"),
            "ips_enabled": metrics.get("ips_enabled"),
        }
    print(json.dumps(output, indent=2))


# ------------------------------------------------------------------
# Command
# ------------------------------------------------------------------


@status_app.callback(invoke_without_command=True)
def status(
    ctx: typer.Context,
    period: str = typer.Option(
        "24h",
        "--period",
        "--since",
        "-p",
        help="Time period for event counts. Supports relative offsets (e.g. 1h, 24h, 7d) or epoch timestamps.",
    ),
    extended: bool = typer.Option(
        False,
        "--extended",
        "-x",
        help="Fetch additional resource counts: SCIM groups, URL lists, NPA rules, IPsec tunnels, RBAC roles, IPS.",
    ),
) -> None:
    """Show a quick tenant health overview.

    Displays infrastructure health (publishers, private apps, users) and
    event activity (alerts, incidents, application, network, page events)
    in a single dashboard view. Useful as a first command to check tenant
    status.

    Use --extended / -x to include additional resource counts (SCIM groups,
    URL lists, NPA policy rules, IPsec tunnels, RBAC roles, IPS status).

    Examples:
        netskope status
        netskope status --since 7d
        netskope status --period 7d
        netskope status -o json
        netskope status -p 1h
        netskope status --extended
        netskope status -x -o json
    """
    state = ctx.obj
    no_color = state.no_color if state else False
    fmt = state.output.value if state else "table"

    client, base_url = _build_client(ctx)
    headers = client._build_headers()
    cookies = client._build_cookies()

    start_ts, end_ts = validate_time_range(period)
    time_params = {"starttime": start_ts, "endtime": end_ts}

    with spinner("Fetching tenant status...", no_color=no_color):
        metrics, errors = asyncio.run(
            _gather_status(base_url, headers, time_params, cookies=cookies, extended=extended)
        )

    if errors:
        verbose = getattr(state, "verbose", False) if state else False
        err_console = Console(stderr=True)
        if verbose:
            for err in errors:
                err_console.print(f"[dim red]  ✗ {err}[/dim red]")
        else:
            all_na = (
                all(v is None for k, v in metrics.items() if k != "publishers")
                and metrics.get("publishers", {}).get("total") is None
            )
            if all_na:
                err_console.print(
                    f"[yellow]All API calls failed. Verify the tenant URL ({base_url}) and credentials.[/yellow]"
                )
                err_console.print("[dim]Use --verbose for details.[/dim]")

    if fmt == "json":
        _render_json(base_url, metrics, period, extended=extended)
    else:
        _render_table(base_url, metrics, period, no_color, extended=extended)
