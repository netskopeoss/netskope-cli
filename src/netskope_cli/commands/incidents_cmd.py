"""Incident commands for the Netskope CLI.

Provides subcommands for querying user confidence index, updating incidents,
retrieving DLP forensics, and searching incident events.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.datasearch import (
    DATASEARCH_PAGE_CAP,
    count_ceiling,
    count_exact,
    is_page_capped,
    print_exact_count,
    raise_on_error_envelope,
    resolve_api_fields,
)
from netskope_cli.core.exceptions import APIError, ValidationError
from netskope_cli.core.output import (
    OutputFormatter,
    echo_error,
    echo_success,
    echo_warning,
    spinner,
)
from netskope_cli.core.output import (
    build_formatter as _core_build_formatter,
)
from netskope_cli.utils.helpers import validate_time_range

# Fields the update API accepts, and the values each one recognises.
#
# The tenant validates `severity` (an unknown value fails the write), but it does
# NOT validate `status` — an arbitrary string is written straight through, so a
# typo or the wrong capitalisation silently corrupts the incident's workflow
# state. Both are checked here; --force bypasses the check.
_UPDATABLE_FIELDS = ("status", "assignee", "severity")
_STATUS_VALUES = ("new", "in_progress", "resolved", "closed")
_SEVERITY_VALUES = ("Low", "Medium", "High", "Critical")
_KNOWN_VALUES = {"status": _STATUS_VALUES, "severity": _SEVERITY_VALUES}

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
    """Build the shared OutputFormatter for this context (delegates to core.output.build_formatter)."""
    return _core_build_formatter(ctx)


def _get_output_format(ctx: typer.Context) -> str:
    """Return the output format string from global state."""
    state = ctx.obj
    return state.output.value if state is not None else "table"


_INCIDENT_EVENTS_ENDPOINT = "/api/v2/events/datasearch/incident"

_HELP_API_FIELDS = (
    "Comma-separated top-level field names the API should return, e.g. 'incident_id,user,severity,timestamp'. "
    "Sent to the API as a server-side projection to reduce payload size; automatically widened with any field "
    "named by --fields, --where or --sort so those keep working. Output shows these columns in this order "
    "unless --fields picks others. Omit to return every field. To choose columns client-side (nested paths, "
    "globs) use the global --fields; see 'ntsk docs fields'."
)


def _query_incident_events(
    ctx: typer.Context,
    params: dict[str, object],
    *,
    api_fields: Optional[str],
    limit: int,
    count: bool,
    title: str,
    default_fields: Optional[list[str]] = None,
    spinner_text: str,
) -> None:
    """Run a datasearch/incident query and render it (shared by 'list' and 'search').

    ``--count`` fetches a full API page (10,000 rows) instead of ``--limit``
    and reports ``N+`` when the page filled up; ``--exact`` pages for the
    true total.  ``--api-fields`` is widened so client-side ``--fields``,
    ``--where`` and ``--sort`` still see the fields they reference.
    """
    state = ctx.obj
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    quiet = bool(getattr(state, "quiet", False))
    no_color = bool(getattr(state, "no_color", False))

    selection = resolve_api_fields(ctx, api_fields)
    if selection.request is not None:
        params["fields"] = selection.request

    if count and getattr(state, "exact", False):
        where_expr = getattr(state, "where_expr", None)
        ceiling = count_ceiling()
        result = count_exact(
            client,
            _INCIDENT_EVENTS_ENDPOINT,
            params,
            where=where_expr,
            ceiling=ceiling,
            quiet=quiet,
            no_color=no_color,
        )
        print_exact_count(result, where=where_expr is not None, ceiling=ceiling, quiet=quiet, no_color=no_color)
        return

    params["limit"] = DATASEARCH_PAGE_CAP if count else limit

    with spinner(spinner_text, no_color=no_color, quiet=quiet):
        data = client.request("GET", _INCIDENT_EVENTS_ENDPOINT, params=params)
    raise_on_error_envelope(data)

    capped_at = DATASEARCH_PAGE_CAP if count and is_page_capped(data, DATASEARCH_PAGE_CAP) else None

    formatter.format_output(
        data,
        fmt=fmt,
        fields=selection.display,
        projected=selection.projected,
        title=title,
        default_fields=default_fields,
        count_only=count,
        capped_at=capped_at,
        strip_internal=not bool(getattr(state, "raw", False)),
        add_iso_timestamps=not bool(getattr(state, "epoch", False)),
    )


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
    api_fields: Optional[str] = typer.Option(None, "--api-fields", help=_HELP_API_FIELDS),
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
        help=(
            "Print only the count of matching incidents. Fetches up to 10,000 rows (the API page cap) and "
            "prints N+ when that cap is hit; add the global --exact to page for the true total."
        ),
    ),
) -> None:
    """List recent incidents (alias for 'incidents search' with optional query).

    Queries GET /api/v2/events/datasearch/incident. Unlike 'search', the
    --query flag is optional here — omit it to return all recent incidents.

    Examples:
        netskope incidents list
        netskope incidents list --query 'severity eq "critical"' --start 7d
        netskope incidents list --fields incident_id,severity,user -o csv
        netskope incidents list --api-fields incident_id,severity --where 'status eq "open"'
        netskope incidents list --count
    """
    state = ctx.obj
    count = count or bool(getattr(state, "count", False))

    start_ts, end_ts = validate_time_range(start, end)

    params: dict[str, object] = {"starttime": start_ts, "endtime": end_ts}
    if query:
        params["query"] = query

    _query_incident_events(
        ctx,
        params,
        api_fields=api_fields,
        limit=limit,
        count=count,
        title="Incidents",
        default_fields=["_id", "incident_id", "user", "severity", "status", "timestamp"],
        spinner_text="Fetching incidents...",
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
    incident_id: Optional[str] = typer.Argument(
        None,
        help=(
            "The numeric ID of the incident to update. This is the 'incident_id' (also "
            "reported as 'dlp_incident_id') field returned by 'netskope incidents search'. "
            "Omit only when using --object-id instead."
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
    new_value: str = typer.Option(
        ...,
        "--new-value",
        help=(
            "The new value to set. For 'status': new, in_progress, resolved, closed "
            "(lowercase). For 'severity': Low, Medium, High, Critical (capitalised). "
            "For 'assignee': the analyst's email address."
        ),
    ),
    user: str = typer.Option(
        ...,
        "--user",
        help=(
            "Identifier of the analyst making the change, recorded in the audit trail. "
            "The API does not validate this against your tenant's users, so any string "
            "is accepted — an email address is the useful convention."
        ),
    ),
    old_value: Optional[str] = typer.Option(
        None,
        "--old-value",
        help=(
            "The field's current value. Required with --object-id, where the API uses it "
            "to select which incidents to change. Ignored when updating by incident ID."
        ),
    ),
    object_id: Optional[str] = typer.Option(
        None,
        "--object-id",
        help=(
            "Update every incident attached to this object instead of a single incident. "
            "An object ID looks like 'hash_user@example.com_<md5>_<sha1>' and is usually "
            "shared by many incidents. Requires --old-value."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Send --new-value even if it is not a recognised value for the field.",
    ),
) -> None:
    """Update a field on an existing incident (status, assignee, or severity).

    Calls PATCH /api/v2/incidents/update. By default this targets one incident by
    its numeric ID. Pass --object-id to instead update every incident attached to a
    given object, which is a bulk operation — see the warning it prints.

    A success here means the API accepted the request, not that an incident
    changed: an ID matching no incident is also reported as success. Re-query to
    confirm, e.g. 'netskope incidents search --query "incident_id eq <id>"'.

    Examples:
        netskope incidents update 1807262583165050077 --field status \\
            --new-value in_progress --user analyst@example.com
        netskope incidents update 1807262583165050077 --field severity \\
            --new-value Critical --user admin@example.com
        netskope incidents update 1807262583165050077 --field assignee \\
            --new-value responder@example.com --user admin@example.com
    """
    state = ctx.obj

    if field not in _UPDATABLE_FIELDS:
        raise ValidationError(
            f"Invalid field '{field}'.",
            suggestion=f"--field must be one of: {', '.join(_UPDATABLE_FIELDS)}",
        )

    if incident_id and object_id:
        raise ValidationError(
            "Pass either an incident ID or --object-id, not both.",
            suggestion=(
                "The API cannot mix the two in one call. Drop --object-id to update the "
                "single incident, or drop the ID argument to update by object."
            ),
        )
    if not incident_id and not object_id:
        raise ValidationError(
            "No incident to update.",
            suggestion=(
                "Give the numeric incident ID as an argument, or use --object-id.\n"
                "Find IDs with: netskope incidents search --fields incident_id,status,severity"
            ),
        )

    known = _KNOWN_VALUES.get(field)
    if known and new_value not in known and not force:
        raise ValidationError(
            f"'{new_value}' is not a recognised value for '{field}'.",
            suggestion=(
                f"Valid values are: {', '.join(known)} (case-sensitive).\n"
                "The tenant does not reject an unrecognised status, it stores it verbatim, "
                "so a typo here silently corrupts the incident. Pass --force if you really "
                "mean it."
            ),
        )

    entry: dict[str, object] = {
        "field": field,
        "new_value": new_value,
        "user": user,
    }

    if object_id:
        if old_value is None:
            raise ValidationError(
                "--object-id requires --old-value.",
                suggestion=(
                    "The API selects incidents by the pair (object_id, current value), so "
                    "--old-value must match the field's current value exactly."
                ),
            )
        entry["object_id"] = object_id
        entry["old_value"] = old_value
        target = f"object {object_id}"
        echo_warning(
            "--object-id updates every incident attached to this object, which is often "
            "dozens. The API reports the number of payload entries sent, not the number of "
            "incidents changed, so the result count will read '1' either way.",
            no_color=state.no_color,
        )
    else:
        # incident_id must reach the API as a JSON integer: the tenant rejects a quoted
        # ID with "incident_id attribute needs to be integer".
        assert incident_id is not None  # narrowed by the checks above
        if not incident_id.isdigit():
            raise ValidationError(
                f"'{incident_id}' is not a valid incident ID.",
                suggestion=(
                    "Incident IDs are numeric, e.g. 1807262583165050077. If you meant to "
                    "update by object, pass it as --object-id together with --old-value."
                ),
            )
        entry["incident_id"] = int(incident_id)
        target = f"incident {incident_id}"
        if old_value is not None:
            echo_warning(
                "--old-value is ignored when updating by incident ID; the API applies no "
                "concurrency check on this path.",
                no_color=state.no_color,
            )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Updating incident...", no_color=state.no_color):
        try:
            data = client.request(
                "PATCH",
                "/api/v2/incidents/update",
                json_data={"payload": [entry]},
            )
        except APIError as exc:
            # A 500 here means the tenant matched no incident, not a transient fault.
            # Its own wording ("please try later") sends people into pointless retries.
            if exc.status_code == 500 and "update incidents" in str(exc).lower():
                raise APIError(
                    f"The tenant found no incident matching {target}.",
                    status_code=500,
                    suggestion=(
                        "The API reports this as a 500 asking you to retry, but retrying "
                        "will not help. Confirm the incident exists:\n"
                        "  netskope incidents search --query 'incident_id eq <id>' "
                        "--fields incident_id,status,severity"
                        + (
                            "\nWith --object-id, --old-value must also match the field's " "current value exactly."
                            if object_id
                            else ""
                        )
                    ),
                    details=exc.details,
                ) from exc
            raise

    _check_update_response(data, target=target, no_color=state.no_color)

    formatter.format_output(data, fmt=fmt, title="Incident update")


def _check_update_response(data: object, *, target: str, no_color: bool) -> None:
    """Fail loudly on the update API's several flavours of quiet non-success.

    The endpoint answers HTTP 200 for input it rejected ({"ok": 0, ...}) and for
    payload entries it discarded without applying ({"ok": 1, "result": "0"}), so
    the status code alone says nothing about whether anything changed.

    Note the ceiling on what success means here: `result` counts the payload
    entries the API accepted, not the incidents it changed. An ID that matches no
    incident at all still comes back as {"ok": 1, "result": "1"}, so this reports
    acceptance and leaves confirmation to a follow-up query.
    """
    if not isinstance(data, dict):
        return

    result = data.get("result")

    if not data.get("ok"):
        raise APIError(
            str(result) if result else "The incident update was rejected.",
            suggestion=(
                "The tenant accepted the request but applied nothing. Check that --field "
                "and --new-value are valid, and that the incident exists."
            ),
        )

    if str(result) == "0":
        raise APIError(
            f"Nothing was updated for {target}.",
            suggestion=(
                "The API discarded the update without applying it. Confirm the incident "
                "still exists:\n"
                "  netskope incidents search --query 'incident_id eq <id>' --fields incident_id,status"
            ),
        )

    echo_success(f"Update accepted for {target}.", no_color=no_color)


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
    api_fields: Optional[str] = typer.Option(None, "--api-fields", help=_HELP_API_FIELDS),
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
        netskope incidents search --query 'status eq "open"' --api-fields incident_id,user,severity
        netskope -o json incidents search --query 'user eq "alice@example.com"' --start 30d
    """
    state = ctx.obj
    start_ts, end_ts = validate_time_range(start, end)

    params: dict[str, object] = {"query": query, "starttime": start_ts, "endtime": end_ts}

    _query_incident_events(
        ctx,
        params,
        api_fields=api_fields,
        limit=limit,
        count=bool(getattr(state, "count", False)),
        title="Incident Event Search Results",
        spinner_text="Searching incident events...",
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
