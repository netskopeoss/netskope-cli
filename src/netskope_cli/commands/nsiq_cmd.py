"""Netskope Threat Intelligence (NSIQ) commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/nsiq`` endpoints,
covering URL threat lookups, URL recategorization requests, and false
positive reporting.  Use these commands to query the Netskope threat
intelligence database and contribute feedback to improve detection accuracy.
"""

from __future__ import annotations

import logging
from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
nsiq_app = typer.Typer(
    name="intel",
    help=(
        "Netskope Threat Intelligence — look up URL threat data, request "
        "recategorizations, and report false positives.\n\n"
        "Access this command group via: netskope intel <subcommand>"
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an OutputFormatter respecting the current state."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from state."""
    state = ctx.obj
    return state.output.value if state is not None else "table"


def _is_quiet(ctx: typer.Context) -> bool:
    """Return whether quiet mode is enabled."""
    state = ctx.obj
    return state.quiet if state is not None else False


def _no_color(ctx: typer.Context) -> bool:
    """Return the no-color flag from global state."""
    state = ctx.obj
    return state.no_color if state is not None else False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@nsiq_app.command("url-lookup")
def url_lookup(
    ctx: typer.Context,
    url_arg: Optional[str] = typer.Argument(
        None,
        metavar="URL",
        help=("The URL to look up (positional). " "Example: netskope intel url-lookup google.com"),
    ),
    url_opt: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help=(
            "The URL to look up in the Netskope threat intelligence database. "
            "Provide the full URL including scheme (e.g. https://example.com). "
            "The service returns threat categories, confidence scores, and any "
            "known associations with malware campaigns or phishing kits."
        ),
    ),
) -> None:
    """Look up threat intelligence data for a URL.

    Queries the Netskope NSIQ URL-lookup endpoint to retrieve threat
    categorization, risk scores, and intelligence metadata for the given
    URL.  The response includes the URL category (e.g. Malware, Phishing,
    Botnet C2), a confidence level, first-seen and last-seen timestamps,
    and any related indicators of compromise.

    Use this command during incident investigations to quickly determine
    whether a URL accessed by a user is associated with known threats, or
    in automation scripts that need to enrich URLs with threat context.

    EXAMPLES

        # Look up a URL (positional argument)
        netskope intel url-lookup google.com

        # Look up a suspicious URL (using --url flag)
        netskope intel url-lookup --url "https://phishing.example.com/login"

        # Look up and output as JSON for scripting
        netskope -o json intel url-lookup "https://example.com"

        # Look up on a specific tenant profile
        netskope --profile prod intel url-lookup "https://suspect.site"
    """
    url = url_opt or url_arg
    if not url:
        raise typer.BadParameter("Provide a URL as an argument or via --url / -u.")

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = {"query": {"urls": [url]}}

    if not _is_quiet(ctx):
        with spinner("Looking up threat data for URL...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/nsiq/urllookup", json_data=body)
    else:
        result = client.request("POST", "/api/v2/nsiq/urllookup", json_data=body)

    formatter.format_output(result, fmt=fmt, title="URL Threat Lookup")


@nsiq_app.command("url-recategorize")
def url_recategorize(
    ctx: typer.Context,
    url: str = typer.Option(
        ...,
        "--url",
        "-u",
        help=(
            "The URL that you believe is incorrectly categorized. "
            "Provide the full URL including the scheme. The recategorization "
            "request will be reviewed by the Netskope threat research team."
        ),
    ),
    current_category: Optional[str] = typer.Option(
        None,
        "--current-category",
        "-c",
        help=(
            "The current category assigned to the URL by Netskope. "
            "Including this helps the review team understand the discrepancy. "
            "You can find the current category using the url-lookup command."
        ),
    ),
    suggested_category: str = typer.Option(
        ...,
        "--suggested-category",
        "-s",
        help=(
            "The category you believe the URL should be assigned to. "
            "Common categories include 'Business', 'Technology', 'News', "
            "'Malware', 'Phishing', etc. The Netskope team will evaluate "
            "your suggestion and update the classification if appropriate."
        ),
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        "-r",
        help=(
            "A brief explanation of why the URL should be recategorized. "
            "Providing context helps the threat research team process the "
            "request faster and improves the accuracy of future classifications."
        ),
    ),
) -> None:
    """Request recategorization of a URL in the Netskope threat database.

    Submits a recategorization request to the Netskope NSIQ team when you
    believe a URL has been assigned an incorrect category.  This is useful
    when a legitimate business site is blocked as malicious, or when a
    newly-discovered threat site has not yet been categorized correctly.

    Recategorization requests are reviewed by the Netskope threat research
    team and typically processed within 24-48 hours.  You will not receive
    a direct notification when the change is applied; use the url-lookup
    command to check the updated category.

    EXAMPLES

        # Request recategorization with a suggested category
        netskope intel url-recategorize \\
            --url "https://legitimate-business.com" \\
            --suggested-category "Business" \\
            --reason "This is our corporate partner portal"

        # Include the current incorrect category
        netskope intel url-recategorize \\
            --url "https://safe-site.example.com" \\
            --current-category "Malware" \\
            --suggested-category "Technology" \\
            --reason "False positive - this is a developer documentation site"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    recat_request: dict[str, object] = {
        "url": url,
        "suggested_categories": [suggested_category],
    }

    body: dict[str, object] = {
        "email": "",
        "recat_requests": [recat_request],
    }
    if reason is not None:
        body["justification"] = reason

    if not _is_quiet(ctx):
        with spinner("Submitting URL recategorization request...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/nsiq/url/recategorizations", json_data=body)
    else:
        result = client.request("POST", "/api/v2/nsiq/url/recategorizations", json_data=body)

    echo_success("URL recategorization request submitted.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="Recategorization Request")


@nsiq_app.command("false-positive")
def false_positive(
    ctx: typer.Context,
    url: str = typer.Option(
        ...,
        "--url",
        "-u",
        help=(
            "The URL or indicator that was incorrectly flagged as a threat. "
            "Provide the full URL including scheme. This is the primary "
            "identifier used to locate the detection in the threat database."
        ),
    ),
    detection_type: Optional[str] = typer.Option(
        None,
        "--detection-type",
        "-t",
        help=(
            "The type of detection that triggered the false positive. "
            "Examples include 'malware', 'phishing', 'botnet', 'grayware'. "
            "Specifying the detection type helps the research team narrow "
            "down which signature or rule caused the incorrect classification."
        ),
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        "-r",
        help=(
            "A detailed explanation of why you believe this is a false positive. "
            "Include relevant context such as the business purpose of the site, "
            "how it was discovered, and any evidence that it is legitimate."
        ),
    ),
) -> None:
    """Report a false positive detection to the Netskope threat research team.

    Submits a false positive report when a URL or indicator has been
    incorrectly classified as malicious by the Netskope threat intelligence
    engine.  The report is sent to the Netskope NSIQ team for review and,
    if confirmed, the classification will be corrected in a subsequent
    threat database update.

    Use this command when users are being blocked from accessing legitimate
    sites, or when security alerts are being generated for benign activity.
    Timely false positive reporting improves detection accuracy for all
    Netskope customers.

    EXAMPLES

        # Report a false positive for a legitimate URL
        netskope intel false-positive \\
            --url "https://safe-tool.example.com" \\
            --detection-type malware \\
            --reason "Internal developer tool, not malicious"

        # Minimal report with just the URL
        netskope intel false-positive --url "https://partner-portal.example.com"

        # Output the response as JSON
        netskope -o json intel false-positive \\
            --url "https://example.com/app" \\
            --reason "Business SaaS application"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    data: dict[str, object] = {
        "url": url,
    }
    if detection_type is not None:
        data["detection_type"] = detection_type
    if reason is not None:
        data["reason"] = reason

    body = {"data": data}

    if not _is_quiet(ctx):
        with spinner("Submitting false positive report...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/nsiq/falsepositives", json_data=body)
    else:
        result = client.request("POST", "/api/v2/nsiq/falsepositives", json_data=body)

    echo_success("False positive report submitted.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="False Positive Report")
