"""Advanced Threat Protection commands for the Netskope CLI.

Provides subcommands that map to the Netskope ``/api/v2/atp`` endpoints,
covering file scanning, URL scanning, scan reports, and threat analysis
submission reports.  Use these commands to submit suspicious files or URLs
for malware analysis and retrieve the resulting verdicts.
"""

from __future__ import annotations

import base64
import logging
import urllib.parse
from pathlib import Path

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.exceptions import NetskopeError
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
atp_app = typer.Typer(
    name="atp",
    help=("Advanced Threat Protection — submit files and URLs for malware " "scanning and retrieve analysis reports."),
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


@atp_app.command("scan-file")
def scan_file(
    ctx: typer.Context,
    file: Path = typer.Option(
        ...,
        "--file",
        "-f",
        exists=True,
        readable=True,
        resolve_path=True,
        help=(
            "Path to the file to submit for malware analysis. "
            "The file is read and base64-encoded before being sent to the "
            "Netskope ATP scanning service. Maximum size depends on your tenant license."
        ),
    ),
    scan_type: str = typer.Option(
        "sandbox",
        "--type",
        "-t",
        help=(
            "Type of scan to perform on the submitted file. "
            "Use 'sandbox' for full behavioural detonation analysis which "
            "takes longer but provides deeper inspection, or 'realtime' for "
            "a quick signature-based scan that returns results immediately."
        ),
    ),
) -> None:
    """Submit a local file for malware scanning via Advanced Threat Protection.

    Reads the specified file, encodes it, and sends it to the Netskope ATP
    file-scan endpoint.  The API returns a job ID that you can use with the
    ``report`` command to check the scan verdict once analysis completes.

    Use this command when you need to verify whether a suspicious file
    contains malware before allowing it into your environment.

    EXAMPLES

        # Submit a file for sandbox analysis (default)
        netskope atp scan-file --file /tmp/suspicious.exe

        # Submit a file for real-time signature scan
        netskope atp scan-file --file ./payload.bin --type realtime

        # Submit and get JSON output
        netskope -o json atp scan-file --file report.pdf
    """
    if scan_type not in ("sandbox", "realtime"):
        raise NetskopeError(
            f"Invalid scan type '{scan_type}'.",
            suggestion="Use 'sandbox' or 'realtime'.",
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    file_bytes = file.read_bytes()
    encoded = base64.b64encode(file_bytes).decode("ascii")

    body = {
        "data": {
            "filename": file.name,
            "content": encoded,
            "type": scan_type,
        }
    }

    if not _is_quiet(ctx):
        with spinner(f"Submitting '{file.name}' for {scan_type} scan...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/atp/scans/filescan", json_data=body)
    else:
        result = client.request("POST", "/api/v2/atp/scans/filescan", json_data=body)

    echo_success(f"File '{file.name}' submitted for {scan_type} scan.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="File Scan Submission")


@atp_app.command("scan-url")
def scan_url(
    ctx: typer.Context,
    url: str = typer.Argument(
        ...,
        help=(
            "The URL to submit for threat scanning. Provide the full URL "
            "including the scheme (e.g. https://example.com/path). The ATP "
            "service will visit and analyse the URL for malicious content."
        ),
    ),
) -> None:
    """Submit a URL for malware and threat scanning.

    Sends the provided URL to the Netskope ATP URL-scan endpoint for
    analysis.  The service checks the URL against threat intelligence feeds,
    performs content inspection, and returns a job ID for retrieving the
    full scan report.

    Use this when you need to verify whether a URL is safe before allowing
    users to access it, or when investigating a potential phishing link
    reported by end users.

    EXAMPLES

        # Scan a suspicious URL
        netskope atp scan-url "https://suspicious-site.example.com/login"

        # Scan a URL and output as JSON
        netskope -o json atp scan-url "https://example.com/download.exe"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    body = {
        "data": {
            "url": url,
        }
    }

    if not _is_quiet(ctx):
        with spinner("Submitting URL for scan...", no_color=_no_color(ctx)):
            result = client.request("POST", "/api/v2/atp/scans/urlscan", json_data=body)
    else:
        result = client.request("POST", "/api/v2/atp/scans/urlscan", json_data=body)

    echo_success("URL submitted for scan.", no_color=_no_color(ctx))
    formatter.format_output(result, fmt=fmt, title="URL Scan Submission")


@atp_app.command("report")
def report(
    ctx: typer.Context,
    job_id: str = typer.Argument(
        ...,
        help=(
            "The job ID returned by a previous scan-file or scan-url command. "
            "This identifier is used to look up the analysis results once the "
            "ATP scanning engine has finished processing the submission."
        ),
    ),
) -> None:
    """Retrieve a scan report for a previously submitted file or URL.

    Queries the Netskope ATP reports endpoint using the job ID that was
    returned when you submitted a file or URL for scanning.  The report
    includes the scan verdict (clean, malicious, suspicious), threat names,
    severity scores, and detailed analysis metadata.

    If the scan is still in progress the API may return a pending status.
    Poll again after a short interval until the verdict is available.

    EXAMPLES

        # Get the report for a completed scan
        netskope atp report abc123-def456-7890

        # Get the report in JSON format for scripting
        netskope -o json atp report abc123-def456-7890

        # Combine with scan-file in a workflow
        netskope atp scan-file --file malware.exe
        # ... note the job_id from the output ...
        netskope atp report <job_id>
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if not _is_quiet(ctx):
        with spinner(f"Fetching report for job '{job_id}'...", no_color=_no_color(ctx)):
            result = client.request("GET", f"/api/v2/atp/scans/reports/{urllib.parse.quote(job_id, safe='')}")
    else:
        result = client.request("GET", f"/api/v2/atp/scans/reports/{urllib.parse.quote(job_id, safe='')}")

    formatter.format_output(result, fmt=fmt, title=f"ATP Scan Report — {job_id}")


@atp_app.command("submission")
def submission(
    ctx: typer.Context,
    submission_id: str = typer.Argument(
        ...,
        help=(
            "The submission ID for the threat analysis request. "
            "This is the unique identifier assigned by the Threat Protection "
            "as a Service (TPaaS) engine when a file was submitted for deep "
            "behavioural analysis."
        ),
    ),
) -> None:
    """Retrieve threat analysis reports for a TPaaS submission.

    Queries the Netskope Threat Protection as a Service (TPaaS) endpoint
    to fetch detailed behavioural analysis reports for a given submission.
    TPaaS reports include sandbox execution traces, network indicators of
    compromise (IOCs), dropped files, registry modifications, and an
    overall threat score.

    Use this command when you need the full detonation report for a file
    that was submitted through the ATP pipeline or through an inline
    policy action.

    EXAMPLES

        # Get the full TPaaS analysis report
        netskope atp submission sub-abc123-456

        # Output as JSON for integration with a SIEM
        netskope -o json atp submission sub-abc123-456

        # Output as YAML
        netskope -o yaml atp submission sub-abc123-456
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if not _is_quiet(ctx):
        with spinner(
            f"Fetching TPaaS reports for submission '{submission_id}'...",
            no_color=_no_color(ctx),
        ):
            result = client.request(
                "GET",
                f"/api/v2/atp/tpaas/submission/{urllib.parse.quote(submission_id, safe='')}/reports",
            )
    else:
        result = client.request(
            "GET",
            f"/api/v2/atp/tpaas/submission/{urllib.parse.quote(submission_id, safe='')}/reports",
        )

    formatter.format_output(result, fmt=fmt, title=f"TPaaS Submission Report — {submission_id}")
