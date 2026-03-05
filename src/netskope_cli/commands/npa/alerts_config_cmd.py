"""Publisher alert configuration management commands."""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _get_formatter,
    _get_output_format,
    _load_json_file,
    _parse_comma_sep,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
alerts_config_app = typer.Typer(
    name="alerts-config", help="Manage publisher alert configuration.", no_args_is_help=True
)

# ---------------------------------------------------------------------------
# Valid event types for --event-types validation
# ---------------------------------------------------------------------------
_VALID_EVENT_TYPES = frozenset(
    {
        "UPGRADE_WILL_START",
        "UPGRADE_STARTED",
        "UPGRADE_SUCCEEDED",
        "UPGRADE_FAILED",
        "CONNECTION_FAILED",
    }
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@alerts_config_app.command("get")
def get_alerts_config(
    ctx: typer.Context,
) -> None:
    """Retrieve the current publisher alert configuration.

    Queries GET /api/v2/infrastructure/publishers/alertsconfiguration.

    Examples:
        netskope npa alerts-config get
        netskope -o json npa alerts-config get
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching publisher alert configuration..."):
        data = client.request("GET", "/api/v2/infrastructure/publishers/alertsconfiguration")

    formatter.format_output(data, fmt=fmt, title="Publisher Alert Configuration")


@alerts_config_app.command("update")
def update_alerts_config(
    ctx: typer.Context,
    admin_users: Optional[str] = typer.Option(
        None,
        "--admin-users",
        help="Comma-separated list of admin email addresses to receive alerts.",
    ),
    event_types: Optional[str] = typer.Option(
        None,
        "--event-types",
        help="Comma-separated list of event types to alert on. Valid values: "
        "UPGRADE_WILL_START, UPGRADE_STARTED, UPGRADE_SUCCEEDED, UPGRADE_FAILED, CONNECTION_FAILED.",
    ),
    json_file: Optional[str] = typer.Option(
        None,
        "--json-file",
        help="Path to a JSON file containing the full alert configuration payload. Overrides other options.",
    ),
) -> None:
    """Update the publisher alert configuration.

    Sends PUT /api/v2/infrastructure/publishers/alertsconfiguration. Provide
    either --json-file for a full payload or use --admin-users and --event-types.

    Examples:
        netskope npa alerts-config update --admin-users "admin@example.com,ops@example.com" \\
            --event-types "UPGRADE_FAILED,CONNECTION_FAILED"
        netskope npa alerts-config update --json-file alerts.json
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if json_file:
        payload = _load_json_file(json_file)
    else:
        if not admin_users and not event_types:
            echo_error("Provide --admin-users and/or --event-types, or use --json-file.")
            raise typer.Exit(code=1)

        payload: dict[str, object] = {}
        if admin_users:
            payload["adminUsers"] = _parse_comma_sep(admin_users)
        if event_types:
            parsed = _parse_comma_sep(event_types)
            invalid = [et for et in parsed if et not in _VALID_EVENT_TYPES]
            if invalid:
                echo_error(
                    f"Invalid event type(s): {', '.join(invalid)}. "
                    f"Valid values: {', '.join(sorted(_VALID_EVENT_TYPES))}."
                )
                raise typer.Exit(code=1)
            payload["eventTypes"] = parsed

    with spinner("Updating publisher alert configuration..."):
        data = client.request("PUT", "/api/v2/infrastructure/publishers/alertsconfiguration", json_data=payload)

    echo_success("Publisher alert configuration updated.")
    formatter.format_output(data, fmt=fmt, title="Updated Publisher Alert Configuration")
