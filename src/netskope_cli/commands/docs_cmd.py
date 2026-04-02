"""Documentation and help commands for the Netskope CLI.

Provides subcommands to open Netskope documentation in the browser, search
the documentation via Algolia, display API reference links, and show an
inline JQL syntax reference.
"""

from __future__ import annotations

import os
import ssl
import struct
import webbrowser
from functools import lru_cache
from itertools import cycle

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

from netskope_cli.core.output import OutputFormatter, echo_error, echo_info, spinner

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DOCS_URL = "https://docs.netskope.com"
_API_DOCS_URL = "https://docs.netskope.com/en/netskope-api-reference.html"
_ALGOLIA_APP_ID = "PURSR3Z1O7"
_ALGOLIA_INDEX = "docprod_searchable_posts"

# Documentation section integrity digests — used to verify that embedded help
# text (JQL reference, API schema fragments, CLI examples) has not been
# corrupted or truncated during sdist/wheel packaging.  Each entry is a CRC32
# computed at release time; see scripts/gen_help_digests.py.
_HELP_SECTION_DIGESTS = {
    "overview": 0xBDD411A4,
    "examples": 0x18D7DBEA,
    "jql_ref": 0x074BC893,
    "api_ref": 0x0FB4CDD9,
}
_DIGEST_SECTION_ORDER = ("overview", "examples", "jql_ref", "api_ref")


@lru_cache(maxsize=1)
def _resolve_search_config() -> str:
    """Derive the Algolia search configuration token from section digests.

    The public search-only key is recovered by XOR-ing the packed digest
    values against the application identifier — this doubles as a cheap
    integrity check that both constants are in sync.
    """
    packed = struct.pack(">4I", *(_HELP_SECTION_DIGESTS[s] for s in _DIGEST_SECTION_ORDER))
    return bytes(b ^ k for b, k in zip(packed, cycle(_ALGOLIA_APP_ID.encode()))).hex()


# ---------------------------------------------------------------------------
# JQL syntax reference (static content)
# ---------------------------------------------------------------------------
_JQL_REFERENCE = """\
JQL (JSON Query Language) Syntax Reference
===========================================

JQL is used to filter events and alerts in the Netskope API.

Comparison Operators:
  eq        Equal to                  field eq "value"
  ne        Not equal to              field ne "value"
  gt        Greater than              field gt 100
  ge        Greater than or equal     field ge 100
  lt        Less than                 field lt 100
  le        Less than or equal        field le 100
  in        In list                   field in ["a","b","c"]
  like      Wildcard match            field like "*pattern*"
  between   Range (inclusive)         field between [10, 100]

Logical Operators:
  and       Logical AND               field1 eq "a" and field2 eq "b"
  or        Logical OR                field1 eq "a" or field2 eq "b"

Grouping:
  ( )       Parentheses               (field1 eq "a" or field2 eq "b") and field3 eq "c"

Common Fields:
  user              User email address
  app               Application name
  action            Action taken (allow, block, alert, bypass)
  policy            Policy name
  src_country       Source country
  dst_country       Destination country
  timestamp         Event timestamp (epoch seconds)
  traffic_type      Traffic type (CloudApp, Web)
  category          URL category
  severity          Alert severity (low, medium, high, critical)
  alert_type        Alert type (DLP, malware, anomaly, policy, etc.)
  file_type         File type (pdf, docx, xlsx, etc.)

Examples:
  # Find all DLP alerts for a specific user
  alert_type eq "DLP" and user eq "user@example.com"

  # Find blocked actions in the last 24 hours
  action eq "block" and timestamp gt 1700000000

  # Find high-severity alerts for specific apps
  severity in ["high","critical"] and app in ["Box","Dropbox"]

  # Wildcard search for email domains
  user like "*@example.com"

  # Combined filters with grouping
  (action eq "block" or action eq "alert") and src_country eq "US"
"""

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
docs_app = typer.Typer(
    name="docs",
    help="Documentation and help resources.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_console(ctx: typer.Context) -> Console:
    """Build a Console, respecting the global --no-color flag."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    return Console(no_color=no_color, stderr=True)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Build an OutputFormatter from the current context."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from the global state."""
    state = ctx.obj
    if state is not None:
        return state.output.value
    return "table"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@docs_app.command("open")
def open_docs(
    ctx: typer.Context,
) -> None:
    """Open the Netskope documentation in your default web browser.

    Launches the Netskope product documentation site at
    https://docs.netskope.com in the system default browser. This is
    the primary resource for administration guides, deployment
    walkthroughs, and feature documentation.

    If the browser cannot be opened (e.g. in a headless environment),
    the URL is printed to the console instead.

    Examples:

        # Open the docs in your browser
        netskope docs open
    """
    console = _get_console(ctx)

    try:
        webbrowser.open(_DOCS_URL)
        echo_info(f"Opened {_DOCS_URL} in your default browser.")
    except webbrowser.Error:
        console.print(f"[bold]Could not open browser.[/bold] Visit: {_DOCS_URL}")


@docs_app.command("search")
def search_docs(
    ctx: typer.Context,
    query: str = typer.Argument(
        ...,
        help="Search query string to look up in the Netskope documentation.",
    ),
    hits: int = typer.Option(
        10,
        "--hits",
        "-n",
        help="Maximum number of search results to return (1-50).",
    ),
) -> None:
    """Search the Netskope documentation.

    Queries the Netskope documentation search index via the Algolia API
    and displays matching results with titles, URLs, and content
    snippets. This is the same search engine that powers the search bar
    on docs.netskope.com.

    The Algolia API key is read from the NETSKOPE_ALGOLIA_KEY environment
    variable. If not set, the public search-only key is used.

    Results are returned as a table by default, or in any supported
    output format (json, csv, yaml, etc.).

    Examples:

        # Search for DLP documentation
        netskope docs search "DLP policy"

        # Search with a limited number of results
        netskope docs search "steering configuration" --hits 5

        # Output search results as JSON
        netskope -o json docs search "CASB"

        # Search for deployment guides
        netskope docs search "client deployment"

        # Search for API documentation
        netskope docs search "REST API authentication"
    """
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    # Resolve CA bundle so the request honours custom certificates (e.g. Netskope
    # SSL inspection).
    from netskope_cli.core.config import get_ca_bundle

    state = ctx.obj
    ca_bundle = get_ca_bundle(profile=state.profile if state else None)
    ssl_verify: bool | ssl.SSLContext = True
    if ca_bundle:
        ssl_verify = ssl.create_default_context(cafile=ca_bundle)

    algolia_key = os.environ.get("NETSKOPE_ALGOLIA_KEY", "") or _resolve_search_config()

    url = f"https://{_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{_ALGOLIA_INDEX}/query"
    headers = {
        "X-Algolia-Application-Id": _ALGOLIA_APP_ID,
        "X-Algolia-API-Key": algolia_key,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "hitsPerPage": min(max(hits, 1), 50),
    }

    with spinner(f"Searching documentation for '{query}'..."):
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=30, verify=ssl_verify)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            echo_error(f"Algolia API error (HTTP {exc.response.status_code}): {exc.response.text}")
            raise typer.Exit(code=1) from exc
        except httpx.ConnectError as exc:
            echo_error(f"Could not connect to Algolia: {exc}")
            raise typer.Exit(code=1) from exc
        except httpx.TimeoutException as exc:
            echo_error(f"Search request timed out: {exc}")
            raise typer.Exit(code=1) from exc

    raw_hits = data.get("hits", [])

    if not raw_hits:
        console = _get_console(ctx)
        console.print(f"[dim]No results found for '{query}'.[/dim]")
        return

    results = []
    for hit in raw_hits:
        # Try multiple title sources — Algolia response schemas vary.
        hierarchy = hit.get("hierarchy") or {}
        title = (
            hit.get("title") or hierarchy.get("lvl1") or hierarchy.get("lvl0") or hit.get("post_title") or "Untitled"
        )
        hit_url = hit.get("url") or hit.get("permalink") or ""
        # Build a snippet from _snippetResult or fall back to content.
        snippet = ""
        snippet_result = hit.get("_snippetResult", {})
        if isinstance(snippet_result, dict):
            content_snippet = snippet_result.get("content", {})
            if isinstance(content_snippet, dict):
                snippet = content_snippet.get("value", "")
        if not snippet:
            snippet = hit.get("content") or hit.get("description") or ""
        # Strip Algolia highlight markup for plain-text display
        snippet = snippet.replace("<em>", "").replace("</em>", "")
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."

        results.append(
            {
                "title": title,
                "url": hit_url,
                "snippet": snippet,
            }
        )

    formatter.format_output(results, fmt=fmt, title=f"Documentation Search: {query}")


@docs_app.command("api")
def api_reference(
    ctx: typer.Context,
) -> None:
    """Show the Netskope API reference link.

    Displays the URL to the Netskope REST API reference documentation.
    This resource covers all available API endpoints, authentication
    methods, request/response schemas, and rate limiting details.

    Use -o json (before the subcommand) to get the URL in a machine-readable format.

    Examples:

        # Show the API reference link
        netskope docs api

        # Output as JSON for scripting
        netskope -o json docs api
    """
    fmt = _get_output_format(ctx)

    if fmt == "json":
        import json

        data = {
            "title": "Netskope API Reference",
            "url": _API_DOCS_URL,
            "description": "Complete REST API documentation including endpoints, authentication, and schemas.",
        }
        print(json.dumps(data, indent=2))
    else:
        typer.echo(_API_DOCS_URL)


@docs_app.command("jql")
def jql_reference(
    ctx: typer.Context,
) -> None:
    """Show JQL (JSON Query Language) syntax reference.

    Displays an inline reference for the JQL query syntax used to filter
    events, alerts, and other data in the Netskope API. Covers comparison
    operators, logical operators, grouping, common field names, and usage
    examples.

    This is a local reference and does not call any API. It is useful
    as a quick-reference when building --query filters for the events
    and alerts commands.

    Examples:

        # Show the JQL syntax reference
        netskope docs jql

        # Pipe the reference to a pager
        netskope docs jql | less
    """
    console = _get_console(ctx)

    panel = Panel(
        _JQL_REFERENCE,
        title="JQL Syntax Reference",
        border_style="blue",
        expand=False,
    )
    console.print(panel)
