"""NPA publisher upgrade profile management commands.

Provides subcommands to list, create, update, delete upgrade profiles,
and assign profiles to publishers in bulk.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
    _load_json_file,
    _parse_comma_sep_ints,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
upgrade_profiles_app = typer.Typer(
    name="upgrade-profiles",
    help=(
        "Manage publisher upgrade profiles.\n\n"
        "Upgrade profiles define software update schedules and policies for "
        "publishers, including release type, frequency, and timezone."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@upgrade_profiles_app.command("list")
def list_upgrade_profiles(
    ctx: typer.Context,
) -> None:
    """List all publisher upgrade profiles.

    Queries GET /api/v2/infrastructure/publisherupgradeprofiles.

    Examples:
        netskope npa publishers upgrade-profiles list
        netskope -o json npa publishers upgrade-profiles list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching upgrade profiles..."):
        data = client.request("GET", "/api/v2/infrastructure/publisherupgradeprofiles")

    formatter.format_output(
        data,
        fmt=fmt,
        title="Publisher Upgrade Profiles",
        default_fields=["id", "name", "enabled", "frequency", "timezone", "release_type"],
    )


@upgrade_profiles_app.command("get")
def get_upgrade_profile(
    ctx: typer.Context,
    profile_id: int = typer.Argument(..., help="Numeric upgrade profile ID."),
) -> None:
    """Retrieve detailed information for a specific upgrade profile.

    Queries GET /api/v2/infrastructure/publisherupgradeprofiles/{id}.

    Examples:
        netskope npa publishers upgrade-profiles get 5
        netskope -o json npa publishers upgrade-profiles get 5
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching upgrade profile {profile_id}..."):
        data = client.request("GET", f"/api/v2/infrastructure/publisherupgradeprofiles/{profile_id}")

    formatter.format_output(data, fmt=fmt, title=f"Upgrade Profile {profile_id}")


@upgrade_profiles_app.command("create")
def create_upgrade_profile(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Display name for the upgrade profile.",
    ),
    enabled: bool = typer.Option(
        True,
        "--enabled/--disabled",
        help="Whether the profile is enabled. Defaults to enabled.",
    ),
    docker_tag: str = typer.Option(
        ...,
        "--docker-tag",
        help="Docker image tag for the publisher version to upgrade to.",
    ),
    frequency: str = typer.Option(
        ...,
        "--frequency",
        help="Cron expression defining the upgrade schedule (e.g. '0 2 * * 0').",
    ),
    timezone: str = typer.Option(
        ...,
        "--timezone",
        help="Timezone for the cron schedule (e.g. 'America/Los_Angeles').",
    ),
    release_type: str = typer.Option(
        ...,
        "--release-type",
        help="Release channel. Choices: Beta, Latest, Latest-1, Latest-2.",
    ),
    json_file: Optional[str] = typer.Option(
        None,
        "--json-file",
        help="Path to a JSON file containing the full profile payload. Overrides other options.",
    ),
) -> None:
    """Create a new publisher upgrade profile.

    Sends POST /api/v2/infrastructure/publisherupgradeprofiles.

    Examples:
        netskope npa publishers upgrade-profiles create \\
            --name "Weekly Beta" --docker-tag "v100" --frequency "0 2 * * 0" \\
            --timezone "America/Los_Angeles" --release-type Beta
        netskope npa publishers upgrade-profiles create --json-file profile.json
    """
    _validate_release_type(release_type)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if json_file:
        payload = _load_json_file(json_file)
    else:
        payload = {
            "name": name,
            "enabled": enabled,
            "docker_tag": docker_tag,
            "frequency": frequency,
            "timezone": timezone,
            "release_type": release_type,
        }

    with spinner("Creating upgrade profile..."):
        data = client.request("POST", "/api/v2/infrastructure/publisherupgradeprofiles", json_data=payload)

    echo_success(f"Upgrade profile '{name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created Upgrade Profile")


@upgrade_profiles_app.command("update")
def update_upgrade_profile(
    ctx: typer.Context,
    profile_id: int = typer.Argument(..., help="Numeric ID of the upgrade profile to update."),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="New display name for the profile.",
    ),
    enabled: Optional[bool] = typer.Option(
        None,
        "--enabled/--disabled",
        help="Enable or disable the profile.",
    ),
    docker_tag: Optional[str] = typer.Option(
        None,
        "--docker-tag",
        help="Docker image tag for the publisher version.",
    ),
    frequency: Optional[str] = typer.Option(
        None,
        "--frequency",
        help="Cron expression defining the upgrade schedule.",
    ),
    timezone: Optional[str] = typer.Option(
        None,
        "--timezone",
        help="Timezone for the cron schedule.",
    ),
    release_type: Optional[str] = typer.Option(
        None,
        "--release-type",
        help="Release channel. Choices: Beta, Latest, Latest-1, Latest-2.",
    ),
    json_file: Optional[str] = typer.Option(
        None,
        "--json-file",
        help="Path to a JSON file containing the full profile payload. Overrides other options.",
    ),
) -> None:
    """Update an existing publisher upgrade profile.

    Sends PUT /api/v2/infrastructure/publisherupgradeprofiles/{id}.

    Examples:
        netskope npa publishers upgrade-profiles update 5 --name "New Name"
        netskope npa publishers upgrade-profiles update 5 --json-file profile.json
    """
    if release_type is not None:
        _validate_release_type(release_type)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if json_file:
        payload = _load_json_file(json_file)
    else:
        payload: dict[str, object] = {}
        if name is not None:
            payload["name"] = name
        if enabled is not None:
            payload["enabled"] = enabled
        if docker_tag is not None:
            payload["docker_tag"] = docker_tag
        if frequency is not None:
            payload["frequency"] = frequency
        if timezone is not None:
            payload["timezone"] = timezone
        if release_type is not None:
            payload["release_type"] = release_type

        if not payload:
            echo_error("No update fields provided. Supply at least one option or --json-file.")
            raise typer.Exit(code=1)

    with spinner(f"Updating upgrade profile {profile_id}..."):
        data = client.request(
            "PUT",
            f"/api/v2/infrastructure/publisherupgradeprofiles/{profile_id}",
            json_data=payload,
        )

    echo_success(f"Upgrade profile {profile_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated Upgrade Profile {profile_id}")


@upgrade_profiles_app.command("delete")
def delete_upgrade_profile(
    ctx: typer.Context,
    profile_id: int = typer.Argument(..., help="Numeric ID of the upgrade profile to delete."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt. Required for non-interactive use.",
    ),
) -> None:
    """Delete a publisher upgrade profile.

    Sends DELETE /api/v2/infrastructure/publisherupgradeprofiles/{id}.

    Examples:
        netskope npa publishers upgrade-profiles delete 5
        netskope npa publishers upgrade-profiles delete 5 --yes
    """
    _confirm_delete("upgrade profile", profile_id, yes, ctx)

    client = _build_client(ctx)

    with spinner(f"Deleting upgrade profile {profile_id}..."):
        client.request("DELETE", f"/api/v2/infrastructure/publisherupgradeprofiles/{profile_id}")

    echo_success(f"Upgrade profile {profile_id} deleted.")


@upgrade_profiles_app.command("assign")
def assign_upgrade_profile(
    ctx: typer.Context,
    profile_id: int = typer.Option(
        ...,
        "--profile-id",
        help="Numeric ID of the upgrade profile to assign.",
    ),
    publisher_ids: str = typer.Option(
        ...,
        "--publisher-ids",
        help="Comma-separated list of publisher IDs to assign the profile to.",
    ),
) -> None:
    """Assign an upgrade profile to one or more publishers in bulk.

    Sends PUT /api/v2/infrastructure/publisherupgradeprofiles/bulk.

    Examples:
        netskope npa publishers upgrade-profiles assign --profile-id 5 --publisher-ids 1,2,3
    """
    ids = _parse_comma_sep_ints(publisher_ids)
    if not ids:
        echo_error("No publisher IDs provided.")
        raise typer.Exit(code=1)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {
        "publishers": {
            "apply": {"publisher_upgrade_profiles_id": str(profile_id)},
            "id": [str(pid) for pid in ids],
        }
    }

    with spinner("Assigning upgrade profile to publishers..."):
        data = client.request("PUT", "/api/v2/infrastructure/publisherupgradeprofiles/bulk", json_data=payload)

    echo_success(f"Upgrade profile {profile_id} assigned to publishers {ids}.")
    formatter.format_output(data, fmt=fmt, title="Upgrade Profile Assignment")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_RELEASE_TYPES = {"Beta", "Latest", "Latest-1", "Latest-2"}


def _validate_release_type(value: str) -> None:
    """Raise BadParameter if the release type is not one of the allowed values."""
    if value not in _VALID_RELEASE_TYPES:
        raise typer.BadParameter(
            f"Invalid release type '{value}'. Must be one of: {', '.join(sorted(_VALID_RELEASE_TYPES))}"
        )
