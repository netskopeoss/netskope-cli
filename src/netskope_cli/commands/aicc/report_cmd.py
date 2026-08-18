"""AICC AI Risk Report data command (``ntsk aicc report``).

Aggregates every data set needed for an AIRR-style AI Risk Report (executive
summary, application/MCP/identity inventories, alert posture, key findings)
into a single JSON document or Markdown report. This is the one-command data
source for report-generation tooling: run it once and render however you like.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import typer

from netskope_cli.commands.aicc._common import (
    AICC_BASE,
    HELP_END,
    HELP_START,
    aicc_get,
    build_aicc_client,
    extract_items,
    get_no_color,
    unwrap_data,
)
from netskope_cli.core.output import echo_success


class _ReportFormat(str, Enum):
    json = "json"
    markdown = "markdown"


def _fetch_pages(ctx: typer.Context, client: Any, path: str, params: dict[str, Any], max_rows: int) -> list[Any]:
    """Fetch up to *max_rows* rows from a paginated endpoint (page size 100)."""
    rows: list[Any] = []
    offset = 0
    while len(rows) < max_rows:
        page_size = min(100, max_rows - len(rows))
        page = {**params, "offset": offset, "limit": page_size}
        response = aicc_get(ctx, path, page, spinner_text=f"Fetching {path.rsplit('/', 1)[-1]}...", client=client)
        items, meta = extract_items(unwrap_data(response))
        rows.extend(items)
        total = meta.get("total")
        if not items or len(items) < page_size:
            break
        if total is not None and len(rows) >= total:
            break
        offset += len(items)
    return rows


def _fmt_bytes(value: Any) -> str:
    if not isinstance(value, (int, float)) or value < 0:
        return "-"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "-"


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    """Render rows as a Markdown table given (header, key) column specs."""
    if not rows:
        return ["_No data in this window._", ""]
    lines = ["| " + " | ".join(h for h, _ in columns) + " |"]
    lines.append("|" + "|".join(" --- " for _ in columns) + "|")
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key)
            if key.endswith("_bytes") or key == "bytes":
                cells.append(_fmt_bytes(value))
            elif value is None:
                cells.append("-")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _render_markdown(report: dict[str, Any]) -> str:
    meta = report["report"]
    summary = report["executive_summary"]
    lines: list[str] = []
    lines.append("# Netskope AI Risk Report")
    lines.append("")
    lines.append(f"- **Tenant:** {meta['tenant']}")
    lines.append(f"- **Reporting period:** {meta['time_range']['start_time']} — {meta['time_range']['end_time']}")
    lines.append(f"- **Generated:** {meta['generated_at']}")
    if meta.get("data_available_since"):
        lines.append(f"- **Data coverage since:** {meta['data_available_since']}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    entities = summary.get("entity_counts", {})
    lines.append(f"- **AI applications discovered:** {entities.get('applications', '-')}")
    lines.append(f"- **Unsanctioned applications:** {summary.get('unsanctioned_applications', '-')}")
    lines.append(f"- **MCP servers discovered:** {entities.get('mcp_servers', '-')}")
    lines.append(f"- **AI agents discovered:** {entities.get('agents', '-')}")
    lines.append(f"- **Models observed:** {entities.get('models', '-')}")
    lines.append(f"- **Known users of AI:** {entities.get('users', '-')}")
    lines.append(f"- **Unknown / unmanaged identities:** {entities.get('unknown', '-')}")
    traffic = summary.get("total_traffic", {})
    if traffic:
        trend = traffic.get("trend")
        trend_str = f" ({trend:+.1f}% vs prior window)" if isinstance(trend, (int, float)) else ""
        lines.append(f"- **Total AI traffic:** {_fmt_bytes(traffic.get('value'))}{trend_str}")
    alerts = summary.get("alerts", {})
    if alerts:
        lines.append(f"- **AI-related alerts:** {alerts.get('value', '-')}")
    lines.append("")

    lines.append("## AI Applications (top by traffic)")
    lines.append("")
    lines.extend(
        _md_table(
            report["applications"],
            [
                ("Application", "name"),
                ("Category", "category"),
                ("Status", "status"),
                ("CCI", "cci_score"),
                ("CCL", "ccl"),
                ("Identities", "identities"),
                ("Uploaded", "uploaded_bytes"),
                ("Downloaded", "downloaded_bytes"),
                ("Sessions", "sessions"),
                ("First Seen", "first_seen"),
            ],
        )
    )

    lines.append("## MCP Servers (top by sessions)")
    lines.append("")
    lines.extend(
        _md_table(
            report["mcp_servers"],
            [
                ("MCP Server", "name"),
                ("Category", "category"),
                ("CCI", "cci_score"),
                ("CCL", "ccl"),
                ("Users", "users"),
                ("Events", "events"),
                ("Sessions", "sessions"),
                ("First Seen", "first_seen"),
            ],
        )
    )

    lines.append("## Identities — Users (top by traffic)")
    lines.append("")
    lines.extend(
        _md_table(
            report["users"],
            [
                ("User", "user_id"),
                ("OU", "ou"),
                ("Apps", "apps"),
                ("MCP Servers", "mcp_servers"),
                ("Uploaded", "uploaded_bytes"),
                ("Downloaded", "downloaded_bytes"),
                ("Sessions", "sessions"),
                ("First Seen", "first_seen"),
            ],
        )
    )

    lines.append("## Identities — Unknown / Unmanaged")
    lines.append("")
    lines.extend(
        _md_table(
            report["unknown_identities"],
            [
                ("Source", "user_id"),
                ("Hostname", "last_hostname"),
                ("Apps", "apps"),
                ("MCP Servers", "mcp_servers"),
                ("Uploaded", "uploaded_bytes"),
                ("Downloaded", "downloaded_bytes"),
                ("First Seen", "first_seen"),
                ("Last Seen", "last_seen"),
            ],
        )
    )

    lines.append("## Alert Posture")
    lines.append("")
    lines.extend(
        _md_table(
            report["alerts"].get("matrix", []),
            [("Asset", "asset"), ("Detection", "detection"), ("Alerts", "count")],
        )
    )
    lines.extend(
        _md_table(
            report["alerts"].get("policies", []),
            [("Policy", "policy"), ("Severity", "severity"), ("Alerts", "count")],
        )
    )

    findings = report.get("key_findings", {})
    if findings:
        lines.append("## Key Findings")
        lines.append("")
        for label, item in findings.items():
            if item:
                lines.append(f"- **{label.replace('_', ' ').title()}:** {item}")
        lines.append("")

    lines.append("---")
    lines.append("_Data source: Netskope AI Command Center (`ntsk aicc`)._")
    lines.append("")
    return "\n".join(lines)


def _top_finding(rows: list[dict[str, Any]], key: str, name_key: str = "name") -> Optional[str]:
    best = None
    best_value: float = -1
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and value > best_value:
            best, best_value = row, value
    if best is None:
        return None
    display = best.get(name_key) or best.get("user_id") or "?"
    if key.endswith("bytes"):
        return f"{display} ({_fmt_bytes(best_value)})"
    return f"{display} ({best_value:,} {key.replace('_', ' ')})"


def report(
    ctx: typer.Context,
    start: Optional[str] = typer.Option(
        None, "--start", "-s", "--since", help=HELP_START + " For reports, 30d is a common choice."
    ),
    end: Optional[str] = typer.Option(None, "--end", "-e", help=HELP_END),
    top: int = typer.Option(
        10, "--top", help="Number of rows to include per inventory section (apps, MCP servers, users, unknown)."
    ),
    fmt: _ReportFormat = typer.Option(
        _ReportFormat.json,
        "--format",
        help=(
            "Output format: 'json' (structured data bundle for downstream rendering) or "
            "'markdown' (human-readable report)."
        ),
    ),
    output_file: Optional[str] = typer.Option(None, "--out", help="Write the report to this file instead of stdout."),
) -> None:
    """Build a complete AI Risk Report data bundle in one command.

    Aggregates ~10 AICC endpoints into one document: executive summary
    (entity counts, traffic KPIs, unsanctioned app count), top AI
    applications, MCP servers, user and unknown identities, alert posture
    (matrix + policies), and computed key findings (top app/server/user by
    usage and the riskiest assets).

    The JSON output is designed for report-generation tooling: every section
    is a plain list of records with stable field names, ready to render into
    HTML/PDF. The default window is the last 7 days; use --start 30d (or an
    explicit --start/--end pair) for a monthly report.

    Examples:
        ntsk aicc report --start 30d -o json > airr-data.json
        ntsk aicc report --start 2026-06-01 --end 2026-06-30 --format markdown --out airr.md
        ntsk aicc report --top 25 --format markdown
    """
    from netskope_cli.commands.aicc._common import resolve_time_range

    start_iso, end_iso = resolve_time_range(ctx, start, end)
    window = {"start_time": start_iso, "end_time": end_iso}
    client = build_aicc_client(ctx)

    def get(path: str, params: dict[str, Any], label: str) -> Any:
        return unwrap_data(aicc_get(ctx, path, params, spinner_text=f"Fetching {label}...", client=client))

    coverage = get(f"{AICC_BASE}/data-coverage", {}, "data coverage")
    entity_counts = get(f"{AICC_BASE}/analytics/entity-counts", dict(window), "entity counts")
    traffic = get(f"{AICC_BASE}/analytics/sums", {**window, "type": "traffic", "timezone": "UTC"}, "traffic KPI")
    alerts_kpi = get(f"{AICC_BASE}/analytics/counts", {**window, "type": "alerts", "timezone": "UTC"}, "alerts KPI")
    status_breakdown = get(
        f"{AICC_BASE}/analytics/ai-applications", {**window, "dimension": "status"}, "app status breakdown"
    )

    apps = _fetch_pages(
        ctx,
        client,
        f"{AICC_BASE}/inventory/ai-applications",
        {**window, "sort": json.dumps({"field": "bytes", "order": "desc"})},
        top,
    )
    mcp_servers = _fetch_pages(
        ctx,
        client,
        f"{AICC_BASE}/inventory/mcp-servers",
        {**window, "sort": json.dumps({"field": "sessions", "order": "desc"})},
        top,
    )
    users = _fetch_pages(
        ctx,
        client,
        f"{AICC_BASE}/inventory/identities",
        {**window, "type": "user", "sort": json.dumps({"field": "bytes", "order": "desc"})},
        top,
    )
    unknown = _fetch_pages(
        ctx,
        client,
        f"{AICC_BASE}/inventory/identities",
        {**window, "type": "unknown", "sort": json.dumps({"field": "bytes", "order": "desc"})},
        top,
    )

    matrix = get(f"{AICC_BASE}/analytics/alerts/matrix", dict(window), "alerts matrix")
    policies = get(f"{AICC_BASE}/analytics/alerts/policies", dict(window), "alert policies")

    unsanctioned = None
    if isinstance(status_breakdown, dict):
        for segment in status_breakdown.get("segments") or []:
            if str(segment.get("label", "")).lower() == "unsanctioned":
                unsanctioned = segment.get("value")

    def _kpi(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {k: payload.get(k) for k in ("value", "previous_value", "trend")}

    def _lowest_ccl(rows: list[dict[str, Any]]) -> Optional[str]:
        order = {"Poor": 0, "Low": 1, "Medium": 2, "High": 3, "Excellent": 4}
        scored = [r for r in rows if r.get("ccl") in order]
        if not scored:
            return None
        worst = min(scored, key=lambda r: order[str(r["ccl"])])
        return f"{worst.get('name')} (CCL {worst.get('ccl')}, CCI {worst.get('cci_score')})"

    report_doc: dict[str, Any] = {
        "report": {
            "tenant": client.base_url.removeprefix("https://"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_range": window,
            "data_available_since": coverage.get("data_available_since") if isinstance(coverage, dict) else None,
            "top_n": top,
        },
        "executive_summary": {
            "entity_counts": (
                {k: v for k, v in (entity_counts or {}).items() if k != "time_range"}
                if isinstance(entity_counts, dict)
                else {}
            ),
            "unsanctioned_applications": unsanctioned,
            "total_traffic": _kpi(traffic),
            "alerts": _kpi(alerts_kpi),
        },
        "applications": apps,
        "mcp_servers": mcp_servers,
        "users": users,
        "unknown_identities": unknown,
        "alerts": {
            "matrix": (matrix or {}).get("items", []) if isinstance(matrix, dict) else [],
            "policies": (policies or {}).get("items", []) if isinstance(policies, dict) else [],
            "total_alerts": (policies or {}).get("total_alerts") if isinstance(policies, dict) else None,
        },
        "key_findings": {
            "top_app_by_traffic": _top_finding(apps, "downloaded_bytes"),
            "top_app_by_sessions": _top_finding(apps, "sessions"),
            "top_mcp_server_by_sessions": _top_finding(mcp_servers, "sessions"),
            "top_user_by_traffic": _top_finding(users, "downloaded_bytes", name_key="user_id"),
            "riskiest_app": _lowest_ccl(apps),
            "riskiest_mcp_server": _lowest_ccl(mcp_servers),
        },
    }

    if fmt is _ReportFormat.markdown:
        rendered = _render_markdown(report_doc)
    else:
        rendered = json.dumps(report_doc, indent=2, default=str)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(rendered if rendered.endswith("\n") else rendered + "\n")
        echo_success(f"Report written to {output_file}", no_color=get_no_color(ctx))
    else:
        typer.echo(rendered)
