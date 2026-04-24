"""Incident commands for the Netskope CLI.

Provides subcommands for querying user confidence index, updating incidents,
retrieving DLP forensics, and searching incident events.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_error, echo_success, spinner
from netskope_cli.utils.helpers import validate_time_range

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
incidents_app = typer.Typer(
    name="incidents",
    help=(
        "View and manage security incidents on the Netskope platform.\n\n"
        "This command group lets you query User Confidence Index (UCI) scores, "
        "update incident fields (status, assignee, severity), retrieve DLP forensics "
        "data, and search incident events with JQL queries. Use these commands for "
        "incident response workflows and SOC automation."
    ),
    no_args_is_help=True,
)

_notes_app = typer.Typer(
    name="notes",
    help=(
        "List, add, and delete notes on DLP incidents.\n\n"
        "Notes are free-text annotations attached to a DLP incident — useful "
        "for recording investigation findings, handoff context, or remediation "
        "steps. Each incident can hold at most 25 notes, and each note must be "
        "under 512 characters.\n\n"
        "See also: 'netskope incidents forensics' for the DLP evidence payload "
        "that accompanies an incident."
    ),
    no_args_is_help=True,
)
incidents_app.add_typer(_notes_app, name="notes")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    """Return an OutputFormatter configured from global state."""
    state = ctx.obj
    no_color = state.no_color if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from global state."""
    state = ctx.obj
    return state.output.value if state is not None else "table"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@incidents_app.command("list")
def incidents_list(
    ctx: typer.Context,
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help=(
            "JQL query string for filtering incident events. Supports field comparisons "
            "and logical operators. Omit to return all recent incidents."
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated list of field names to include in the response.",
    ),
    start: str = typer.Option(
        "24h",
        "--start",
        "-s",
        help="Start of the time range. Accepts relative offsets like '24h', '7d'. Defaults to '24h'.",
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help="End of the time range. Defaults to now.",
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help="Maximum number of incidents to return. Defaults to 100.",
    ),
    count: bool = typer.Option(
        False,
        "--count",
        help="Print only the total count of matching incidents.",
    ),
) -> None:
    """List recent incidents (alias for 'incidents search' with optional query).

    Queries GET /api/v2/events/datasearch/incident. Unlike 'search', the
    --query flag is optional here — omit it to return all recent incidents.

    Examples:
        netskope incidents list
        netskope incidents list --query 'severity eq "critical"' --start 7d
        netskope incidents list --count
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    start_ts, end_ts = validate_time_range(start, end)

    params: dict[str, object] = {
        "starttime": start_ts,
        "endtime": end_ts,
        "limit": limit,
    }
    if query:
        params["query"] = query
    if fields:
        params["fields"] = fields

    field_list = [f.strip() for f in fields.split(",")] if fields else None

    with spinner("Fetching incidents...", no_color=state.no_color):
        data = client.request(
            "GET",
            "/api/v2/events/datasearch/incident",
            params=params,
        )

    strip_internal = not (state.raw if state else False)
    add_iso = not (state.epoch if state else False)

    formatter.format_output(
        data,
        fmt=fmt,
        fields=field_list,
        title="Incidents",
        default_fields=["_id", "incident_id", "user", "severity", "status", "timestamp"],
        count_only=count,
        strip_internal=strip_internal,
        add_iso_timestamps=add_iso,
    )


@incidents_app.command("uci")
def uci(
    ctx: typer.Context,
    user: str = typer.Argument(
        ...,
        help=(
            "Username or email address of the user to look up. This must match the "
            "identity as it appears in Netskope (typically the user's email address). "
            "For example: 'alice@example.com'."
        ),
    ),
    from_time: str = typer.Option(
        "7d",
        "--from-time",
        help=(
            "Start of the time range for the UCI calculation. Accepts a relative offset "
            "such as '7d' (last 7 days), '24h' (last 24 hours), or a Unix epoch timestamp "
            "in seconds. Defaults to '7d'. Longer ranges provide a more complete risk picture."
        ),
    ),
) -> None:
    """Retrieve the User Confidence Index (UCI) score for a specific user.

    The UCI is a risk score calculated from user behaviour analytics. It queries
    POST /api/v2/ubadatasvc/user/uci to assess how risky a user's recent activity
    has been. Use this to prioritize incident investigations or to feed into
    automated risk-based access policies.

    Examples:
        netskope incidents uci alice@example.com
        netskope incidents uci bob@example.com --from-time 30d
        netskope -o json incidents uci alice@example.com --from-time 24h
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    # Convert the from_time to milliseconds.
    from_time_seconds, _ = validate_time_range(from_time)
    from_time_ms = from_time_seconds * 1000

    payload = {
        "user": user,
        "fromTime": from_time_ms,
    }

    with spinner("Fetching User Confidence Index...", no_color=state.no_color):
        data = client.request(
            "POST",
            "/api/v2/ubadatasvc/user/uci",
            json_data=payload,
        )

    formatter.format_output(data, fmt=fmt, title=f"UCI — {user}")


@incidents_app.command("update")
def update(
    ctx: typer.Context,
    incident_id: str = typer.Argument(
        ...,
        help=(
            "The unique identifier of the incident to update. You can find incident IDs "
            "by running 'netskope incidents search' or 'netskope events incident'."
        ),
    ),
    field: str = typer.Option(
        ...,
        "--field",
        help=(
            "The incident field to update. Valid values are: 'status', 'assignee', or "
            "'severity'. Only one field can be updated per call. Use separate invocations "
            "to update multiple fields."
        ),
    ),
    old_value: str = typer.Option(
        ...,
        "--old-value",
        help=(
            "The current value of the field being updated. This is required by the API as "
            "a concurrency guard to prevent conflicting updates. Must match the field's "
            "current value exactly."
        ),
    ),
    new_value: str = typer.Option(
        ...,
        "--new-value",
        help=(
            "The new value to set for the field. For 'status', use values like 'open', "
            "'in_progress', or 'closed'. For 'severity', use 'low', 'medium', 'high', "
            "or 'critical'. For 'assignee', use the analyst's email address."
        ),
    ),
    user: str = typer.Option(
        ...,
        "--user",
        help=(
            "Email address of the analyst making the change. This is recorded in the "
            "audit trail for accountability. Must be a valid user in your Netskope tenant."
        ),
    ),
) -> None:
    """Update a field on an existing incident (status, assignee, or severity).

    Calls PATCH /api/v2/incidents/update with the provided field change. The API
    requires the old value as a concurrency guard. Use this for SOC workflow
    automation such as assigning incidents to analysts or escalating severity.

    Examples:
        netskope incidents update INC-123 --field status \\
            --old-value open --new-value in_progress --user analyst@example.com
        netskope incidents update INC-456 --field severity \\
            --old-value medium --new-value critical --user admin@example.com
        netskope incidents update INC-789 --field assignee \\
            --old-value "" --new-value responder@example.com --user admin@example.com
    """
    state = ctx.obj
    allowed_fields = ("status", "assignee", "severity")
    if field not in allowed_fields:
        echo_error(
            f"Invalid field '{field}'. Must be one of: {', '.join(allowed_fields)}",
            no_color=state.no_color,
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload = {
        "payload": [
            {
                "object_id": incident_id,
                "field": field,
                "old_value": old_value,
                "new_value": new_value,
                "user": user,
            }
        ]
    }

    with spinner("Updating incident...", no_color=state.no_color):
        data = client.request(
            "PATCH",
            "/api/v2/incidents/update",
            json_data=payload,
        )

    formatter.format_output(data, fmt=fmt, title=f"Incident {incident_id} Updated")


@incidents_app.command("forensics")
def forensics(
    ctx: typer.Context,
    dlp_incident_id: str = typer.Argument(
        ...,
        help=(
            "The DLP-specific incident ID to retrieve forensics for. Important: this is "
            "the dlp_incident_id field, NOT the regular incident_id. You can find DLP "
            "incident IDs in the incident event data or the Netskope admin console."
        ),
    ),
) -> None:
    """Retrieve DLP forensics data for a specific DLP incident.

    Calls GET /api/v2/incidents/dlpincidents/{id}/forensics to download the
    forensic evidence associated with a DLP violation. This includes details
    about the matched DLP rules, the sensitive content that triggered the alert,
    and file metadata. Use this for incident investigation and compliance reporting.

    Examples:
        netskope incidents forensics DLP-12345
        netskope -o json incidents forensics DLP-12345
        netskope -o json incidents forensics DLP-67890 | jq '.data'
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    path = f"/api/v2/incidents/dlpincidents/{urllib.parse.quote(dlp_incident_id, safe='')}/forensics"

    with spinner("Fetching DLP forensics...", no_color=state.no_color):
        data = client.request("GET", path)

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"DLP Forensics — Incident {dlp_incident_id}",
    )


@incidents_app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help=(
            "JQL (JSON Query Language) query string for filtering incident events. Supports "
            "field comparisons and logical operators. For example: 'severity eq \"critical\"' "
            'or \'status eq "open" AND user eq "alice@example.com"\'. This option is required.'
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help=(
            "Comma-separated list of field names to include in the response. Reduces payload "
            "size and focuses on relevant data. For example: 'incident_id,user,severity,timestamp'. "
            "Omit to return all available fields."
        ),
    ),
    start: str = typer.Option(
        "24h",
        "--start",
        "-s",
        help=(
            "Start of the time range for the search. Accepts a relative offset such as '24h' "
            "(last 24 hours), '7d' (last 7 days), or a Unix epoch timestamp in seconds. "
            "Defaults to '24h'."
        ),
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        "-e",
        help=(
            "End of the time range for the search. Accepts a relative offset or Unix epoch "
            "timestamp. Defaults to the current time ('now') when omitted. Must be later "
            "than --start."
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help=(
            "Maximum number of incident events to return. Defaults to 100. Use smaller values "
            "for quick lookups and larger values for bulk analysis. The API may enforce an "
            "upper bound."
        ),
    ),
) -> None:
    """Search incident events using JQL queries and time ranges.

    Calls GET /api/v2/events/datasearch/incident with the provided JQL query,
    time range, and field selections. Use this for detailed incident investigation
    and to build custom incident reports. Defaults to the last 24 hours.

    Examples:
        netskope incidents search --query 'severity eq "critical"' --start 7d
        netskope incidents search --query 'status eq "open"' --fields incident_id,user,severity --limit 50
        netskope -o json incidents search --query 'user eq "alice@example.com"' --start 30d
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    start_ts, end_ts = validate_time_range(start, end)

    params: dict[str, object] = {
        "query": query,
        "starttime": start_ts,
        "endtime": end_ts,
        "limit": limit,
    }

    if fields:
        params["fields"] = fields

    field_list = [f.strip() for f in fields.split(",")] if fields else None

    with spinner("Searching incident events...", no_color=state.no_color):
        data = client.request(
            "GET",
            "/api/v2/events/datasearch/incident",
            params=params,
        )

    formatter.format_output(
        data,
        fmt=fmt,
        fields=field_list,
        title="Incident Event Search Results",
    )


@incidents_app.command("anomalies")
def anomalies(
    ctx: typer.Context,
    users: str = typer.Option(
        ...,
        "--users",
        "-u",
        help=(
            "Comma-separated list of user email addresses to investigate for anomalies. "
            "For example: 'alice@example.com,bob@example.com'. At least one email is required."
        ),
    ),
    timeframe: int = typer.Option(
        30,
        "--timeframe",
        "-t",
        min=1,
        max=90,
        help=(
            "Number of days to look back for anomalies. Must be between 1 and 90. "
            "Defaults to 30 days. Longer timeframes capture more anomalies but may "
            "take longer to return."
        ),
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        min=1,
        max=10000,
        help=("Maximum number of anomaly results to return. Must be between 1 and 10000. " "Defaults to 100."),
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
        help="Pagination offset. Use with --limit to paginate through large result sets.",
    ),
    sortby: str = typer.Option(
        "time",
        "--sortby",
        help=("Field to sort results by. Defaults to 'time'. Other useful values include " "'severity' or 'user'."),
    ),
    sortorder: str = typer.Option(
        "desc",
        "--sortorder",
        help="Sort direction: 'asc' for ascending or 'desc' for descending. Defaults to 'desc'.",
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help=(
            "Comma-separated severity filter to narrow results. Valid severity levels are: "
            "'Critical', 'High', 'Medium', 'Low', 'Informational'. "
            "For example: 'High,Critical' to see only high and critical anomalies."
        ),
    ),
) -> None:
    """Retrieve UBA (User Behavior Analytics) anomalies for specific users.

    Calls POST /api/v2/incidents/users/getanomalies to fetch ML-detected
    suspicious user behavior. UBA anomalies are generated when Netskope's
    machine-learning models identify activity that deviates significantly from
    a user's normal behavioral baseline.

    Common anomaly types include:

    \b
    - Bulk failed logins indicating brute-force or credential-stuffing attacks
    - Unusual access patterns such as accessing sensitive resources at odd hours
    - Compromised credentials detected through impossible-travel or anomalous IP usage
    - Data exfiltration signals from abnormal upload/download volumes

    Severity levels (from most to least severe):

    \b
    - Critical  — Immediate action required; strong indicators of compromise
    - High      — Likely malicious; should be investigated promptly
    - Medium    — Suspicious activity that warrants review
    - Low       — Minor deviations; may be benign
    - Informational — Context events for awareness only

    Examples:
        netskope incidents anomalies --users alice@example.com
        netskope incidents anomalies -u alice@example.com,bob@example.com -t 7
        netskope incidents anomalies -u alice@example.com --severity High,Critical
        netskope incidents anomalies -u alice@example.com --limit 500 --offset 100
        netskope -o json incidents anomalies -u alice@example.com --sortby severity --sortorder asc
    """
    state = ctx.obj

    if sortorder not in ("asc", "desc"):
        echo_error(
            f"Invalid sortorder '{sortorder}'. Must be 'asc' or 'desc'.",
            no_color=state.no_color,
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    user_list = [u.strip() for u in users.split(",") if u.strip()]
    if not user_list:
        echo_error(
            "At least one user email is required for --users.",
            no_color=state.no_color,
        )
        raise typer.Exit(code=1)

    payload: dict[str, object] = {
        "users": user_list,
        "timeframe": timeframe,
        "limit": limit,
        "offset": offset,
        "sortby": sortby,
        "sortorder": sortorder,
    }

    if severity:
        severity_list = [s.strip() for s in severity.split(",") if s.strip()]
        payload["severity_filter"] = severity_list

    with spinner("Fetching UBA anomalies...", no_color=state.no_color):
        data = client.request(
            "POST",
            "/api/v2/incidents/users/getanomalies",
            json_data=payload,
        )

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"UBA Anomalies — {', '.join(user_list)}",
    )


# ---------------------------------------------------------------------------
# Notes subcommands
# ---------------------------------------------------------------------------

# The API rejects content at 512 characters or more — enforce strict-less-than
# on the client side so we fail fast with a clear message instead of round-
# tripping a 400.
_NOTE_CONTENT_LIMIT = 512

_DLP_INCIDENT_ID_HELP = (
    "DLP incident identifier. Important: this is the dlp_incident_id field, "
    "NOT the regular incident_id. Find DLP incident IDs in the "
    "'dlp_incident_id' column of 'netskope incidents list' output, or in the "
    "Netskope admin console."
)


@_notes_app.command("list")
def notes_list(
    ctx: typer.Context,
    dlp_incident_id: str = typer.Argument(..., help=_DLP_INCIDENT_ID_HELP),
) -> None:
    """List notes attached to a DLP incident.

    Calls GET /api/v2/incidents/dlpincidents/{id}/notes. Each note records
    the author, timestamp, and text content. Returns an empty list if the
    incident has no notes yet.

    Examples:
        netskope incidents notes list 1343008090332508247
        netskope -o json incidents notes list 1343008090332508247 | jq '.[].content'
        netskope incidents notes list 1343008090332508247 -f note_id,user
        netskope --profile staging incidents notes list 1343008090332508247
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    path = f"/api/v2/incidents/dlpincidents/{urllib.parse.quote(dlp_incident_id, safe='')}/notes"

    with spinner("Fetching notes...", no_color=state.no_color):
        data = client.request("GET", path)

    add_iso = not (state.epoch if state else False)

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"Notes — DLP Incident {dlp_incident_id}",
        default_fields=["note_id", "user", "timestamp", "content"],
        add_iso_timestamps=add_iso,
    )


@_notes_app.command("add")
def notes_add(
    ctx: typer.Context,
    dlp_incident_id: str = typer.Argument(..., help=_DLP_INCIDENT_ID_HELP),
    content: str = typer.Option(
        ...,
        "--content",
        "-c",
        help=(
            "Text body of the note. Must be under 512 characters. Intended for "
            "short investigation findings, handoff context, or remediation steps."
        ),
    ),
) -> None:
    """Add a new note to a DLP incident.

    Calls POST /api/v2/incidents/dlpincidents/{id}/notes with the provided
    content. Each incident can hold at most 25 notes; the API returns 409 when
    that limit is reached. Content must be under 512 characters.

    Examples:
        netskope incidents notes add 1343008090332508247 -c "Escalated to tier 2"
        netskope incidents notes add 1343008090332508247 --content "False positive — closing"
        netskope -o json incidents notes add 1343008090332508247 -c "Handoff to IR" | jq '.note_id'
        netskope --profile staging incidents notes add 1343008090332508247 -c "Reviewed"
    """
    state = ctx.obj

    if len(content) >= _NOTE_CONTENT_LIMIT:
        echo_error(
            f"Note content is {len(content)} characters; it must be under " f"{_NOTE_CONTENT_LIMIT}.",
            no_color=state.no_color,
        )
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    path = f"/api/v2/incidents/dlpincidents/{urllib.parse.quote(dlp_incident_id, safe='')}/notes"

    with spinner("Adding note...", no_color=state.no_color):
        data = client.request("POST", path, json_data={"content": content})

    # Envelope is {"data": {..single note..}, "status": "success"}. The shared
    # unwrap helper only handles list-typed data, so pull out the note dict
    # here for clean table/json rendering.
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]

    add_iso = not (state.epoch if state else False)

    formatter.format_output(
        data,
        fmt=fmt,
        title=f"Note Added — DLP Incident {dlp_incident_id}",
        add_iso_timestamps=add_iso,
    )


@_notes_app.command("delete")
def notes_delete(
    ctx: typer.Context,
    dlp_incident_id: str = typer.Argument(..., help=_DLP_INCIDENT_ID_HELP),
    note_id: str = typer.Argument(
        ...,
        help=(
            "Unique identifier of the note to delete. This operation is "
            "irreversible — the note cannot be recovered. Find note IDs via "
            "'netskope incidents notes list <dlp-incident-id>'."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt. Useful for scripted workflows.",
    ),
) -> None:
    """Delete a note from a DLP incident.

    Calls DELETE /api/v2/incidents/dlpincidents/{id}/notes/{note_id}. This is
    a destructive operation — the note cannot be recovered. Prompts for
    confirmation unless --yes is passed.

    Examples:
        netskope incidents notes delete 1343008090332508247 604ce028-b104-4fe6-8d4e-6ed3c04c5378
        netskope incidents notes delete 1343008090332508247 604ce028-b104-4fe6-8d4e-6ed3c04c5378 --yes
        netskope --profile staging incidents notes delete 1343008090332508247 604ce028-... -y
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if not yes:
        typer.confirm(
            f"Delete note {note_id} from DLP incident {dlp_incident_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    path = (
        f"/api/v2/incidents/dlpincidents/"
        f"{urllib.parse.quote(dlp_incident_id, safe='')}/notes/"
        f"{urllib.parse.quote(note_id, safe='')}"
    )

    with spinner(f"Deleting note {note_id}...", no_color=no_color):
        client.request("DELETE", path)

    echo_success(
        f"Note {note_id} deleted from DLP incident {dlp_incident_id}.",
        no_color=no_color,
    )
