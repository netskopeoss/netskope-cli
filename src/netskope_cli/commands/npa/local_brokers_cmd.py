"""NPA local broker management commands.

Provides subcommands to list, create, update, delete local brokers,
manage broker configuration, and generate registration tokens.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _confirm_delete,
    _get_formatter,
    _get_output_format,
)
from netskope_cli.core.output import echo_error, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------
local_brokers_app = typer.Typer(
    name="local-brokers",
    help=(
        "Manage local brokers.\n\n"
        "Local brokers handle traffic distribution within a publisher deployment. "
        "Use these commands to provision, configure, and maintain local brokers."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@local_brokers_app.command("list")
def list_local_brokers(
    ctx: typer.Context,
) -> None:
    """List all local brokers.

    Queries GET /api/v2/infrastructure/lbrokers.

    Examples:
        netskope npa publishers local-brokers list
        netskope -o json npa publishers local-brokers list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching local brokers..."):
        data = client.request("GET", "/api/v2/infrastructure/lbrokers")

    formatter.format_output(
        data,
        fmt=fmt,
        title="Local Brokers",
        default_fields=["id", "name", "common_name", "registered"],
    )


@local_brokers_app.command("get")
def get_local_broker(
    ctx: typer.Context,
    broker_id: int = typer.Argument(..., help="Numeric local broker ID."),
) -> None:
    """Retrieve detailed information for a specific local broker.

    Queries GET /api/v2/infrastructure/lbrokers/{id}.

    Examples:
        netskope npa publishers local-brokers get 10
        netskope -o json npa publishers local-brokers get 10
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Fetching local broker {broker_id}..."):
        data = client.request("GET", f"/api/v2/infrastructure/lbrokers/{broker_id}")

    formatter.format_output(data, fmt=fmt, title=f"Local Broker {broker_id}")


@local_brokers_app.command("create")
def create_local_broker(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Display name for the new local broker. Must be unique.",
    ),
    city: Optional[str] = typer.Option(
        None,
        "--city",
        help="City where the broker is deployed.",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Region or state where the broker is deployed.",
    ),
    country: Optional[str] = typer.Option(
        None,
        "--country",
        help="Country where the broker is deployed.",
    ),
    country_code: Optional[str] = typer.Option(
        None,
        "--country-code",
        help="ISO country code (e.g. 'US', 'GB').",
    ),
    latitude: Optional[float] = typer.Option(
        None,
        "--latitude",
        help="Geographic latitude of the broker location.",
    ),
    longitude: Optional[float] = typer.Option(
        None,
        "--longitude",
        help="Geographic longitude of the broker location.",
    ),
    custom_public_ip: Optional[str] = typer.Option(
        None,
        "--custom-public-ip",
        help="Custom public IP address for the broker.",
    ),
    custom_private_ip: Optional[str] = typer.Option(
        None,
        "--custom-private-ip",
        help="Custom private IP address for the broker.",
    ),
    access_via_public_ip: Optional[str] = typer.Option(
        None,
        "--access-via-public-ip",
        help="Public IP access policy. Choices: NONE, OFF_PREM, ON_PREM, ON_OFF_PREM.",
    ),
) -> None:
    """Create a new local broker.

    Sends POST /api/v2/infrastructure/lbrokers.

    Examples:
        netskope npa publishers local-brokers create --name "DC-Broker-1"
        netskope npa publishers local-brokers create --name "NYC-Broker" --city "New York" --country-code US
    """
    if access_via_public_ip is not None:
        _validate_access_via_public_ip(access_via_public_ip)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {"name": name}
    if city is not None:
        payload["city"] = city
    if region is not None:
        payload["region"] = region
    if country is not None:
        payload["country"] = country
    if country_code is not None:
        payload["country_code"] = country_code
    if latitude is not None:
        payload["latitude"] = latitude
    if longitude is not None:
        payload["longitude"] = longitude
    if custom_public_ip is not None:
        payload["custom_public_ip"] = custom_public_ip
    if custom_private_ip is not None:
        payload["custom_private_ip"] = custom_private_ip
    if access_via_public_ip is not None:
        payload["access_via_public_ip"] = access_via_public_ip

    with spinner("Creating local broker..."):
        data = client.request("POST", "/api/v2/infrastructure/lbrokers", json_data=payload)

    echo_success(f"Local broker '{name}' created.")
    formatter.format_output(data, fmt=fmt, title="Created Local Broker")


@local_brokers_app.command("update")
def update_local_broker(
    ctx: typer.Context,
    broker_id: int = typer.Argument(..., help="Numeric ID of the local broker to update."),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="New display name for the broker.",
    ),
    city: Optional[str] = typer.Option(
        None,
        "--city",
        help="City where the broker is deployed.",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Region or state where the broker is deployed.",
    ),
    country: Optional[str] = typer.Option(
        None,
        "--country",
        help="Country where the broker is deployed.",
    ),
    country_code: Optional[str] = typer.Option(
        None,
        "--country-code",
        help="ISO country code (e.g. 'US', 'GB').",
    ),
    latitude: Optional[float] = typer.Option(
        None,
        "--latitude",
        help="Geographic latitude of the broker location.",
    ),
    longitude: Optional[float] = typer.Option(
        None,
        "--longitude",
        help="Geographic longitude of the broker location.",
    ),
    custom_public_ip: Optional[str] = typer.Option(
        None,
        "--custom-public-ip",
        help="Custom public IP address for the broker.",
    ),
    custom_private_ip: Optional[str] = typer.Option(
        None,
        "--custom-private-ip",
        help="Custom private IP address for the broker.",
    ),
    access_via_public_ip: Optional[str] = typer.Option(
        None,
        "--access-via-public-ip",
        help="Public IP access policy. Choices: NONE, OFF_PREM, ON_PREM, ON_OFF_PREM.",
    ),
) -> None:
    """Update an existing local broker.

    Sends PUT /api/v2/infrastructure/lbrokers/{id}.

    Examples:
        netskope npa publishers local-brokers update 10 --name "Renamed-Broker"
        netskope npa publishers local-brokers update 10 --city "Chicago" --region "IL"
    """
    if access_via_public_ip is not None:
        _validate_access_via_public_ip(access_via_public_ip)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {}
    if name is not None:
        payload["name"] = name
    if city is not None:
        payload["city"] = city
    if region is not None:
        payload["region"] = region
    if country is not None:
        payload["country"] = country
    if country_code is not None:
        payload["country_code"] = country_code
    if latitude is not None:
        payload["latitude"] = latitude
    if longitude is not None:
        payload["longitude"] = longitude
    if custom_public_ip is not None:
        payload["custom_public_ip"] = custom_public_ip
    if custom_private_ip is not None:
        payload["custom_private_ip"] = custom_private_ip
    if access_via_public_ip is not None:
        payload["access_via_public_ip"] = access_via_public_ip

    if not payload:
        echo_error("No update fields provided. Supply at least one option.")
        raise typer.Exit(code=1)

    with spinner(f"Updating local broker {broker_id}..."):
        data = client.request(
            "PUT",
            f"/api/v2/infrastructure/lbrokers/{broker_id}",
            json_data=payload,
        )

    echo_success(f"Local broker {broker_id} updated.")
    formatter.format_output(data, fmt=fmt, title=f"Updated Local Broker {broker_id}")


@local_brokers_app.command("delete")
def delete_local_broker(
    ctx: typer.Context,
    broker_id: int = typer.Argument(..., help="Numeric ID of the local broker to delete."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt. Required for non-interactive use.",
    ),
) -> None:
    """Delete a local broker.

    Sends DELETE /api/v2/infrastructure/lbrokers/{id}. This is a destructive
    operation. Use --yes to skip confirmation.

    Examples:
        netskope npa publishers local-brokers delete 10
        netskope npa publishers local-brokers delete 10 --yes
    """
    _confirm_delete("local broker", broker_id, yes, ctx)

    client = _build_client(ctx)

    with spinner(f"Deleting local broker {broker_id}..."):
        client.request("DELETE", f"/api/v2/infrastructure/lbrokers/{broker_id}")

    echo_success(f"Local broker {broker_id} deleted.")


@local_brokers_app.command("config-get")
def config_get(
    ctx: typer.Context,
) -> None:
    """Retrieve the global local broker configuration.

    Queries GET /api/v2/infrastructure/lbrokers/brokerconfig.

    Examples:
        netskope npa publishers local-brokers config-get
        netskope -o json npa publishers local-brokers config-get
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner("Fetching broker configuration..."):
        data = client.request("GET", "/api/v2/infrastructure/lbrokers/brokerconfig")

    formatter.format_output(data, fmt=fmt, title="Broker Configuration")


@local_brokers_app.command("config-update")
def config_update(
    ctx: typer.Context,
    hostname: str = typer.Option(
        ...,
        "--hostname",
        help="Hostname to set in the broker configuration.",
    ),
) -> None:
    """Update the global local broker configuration.

    Sends PUT /api/v2/infrastructure/lbrokers/brokerconfig.

    Examples:
        netskope npa publishers local-brokers config-update --hostname broker.example.com
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    payload: dict[str, object] = {"hostname": hostname}

    with spinner("Updating broker configuration..."):
        data = client.request("PUT", "/api/v2/infrastructure/lbrokers/brokerconfig", json_data=payload)

    echo_success("Broker configuration updated.")
    formatter.format_output(data, fmt=fmt, title="Updated Broker Configuration")


@local_brokers_app.command("registration-token")
def registration_token(
    ctx: typer.Context,
    broker_id: int = typer.Argument(..., help="Numeric local broker ID to generate a registration token for."),
) -> None:
    """Generate a registration token for a local broker.

    Sends POST /api/v2/infrastructure/lbrokers/{id}/registrationtoken.

    Examples:
        netskope npa publishers local-brokers registration-token 10
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    with spinner(f"Generating registration token for local broker {broker_id}..."):
        data = client.request("POST", f"/api/v2/infrastructure/lbrokers/{broker_id}/registrationtoken")

    echo_success(f"Registration token generated for local broker {broker_id}.")
    formatter.format_output(data, fmt=fmt, title=f"Registration Token (Local Broker {broker_id})")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_ACCESS_VIA_PUBLIC_IP = {"NONE", "OFF_PREM", "ON_PREM", "ON_OFF_PREM"}


def _validate_access_via_public_ip(value: str) -> None:
    """Raise BadParameter if the access-via-public-ip value is invalid."""
    if value not in _VALID_ACCESS_VIA_PUBLIC_IP:
        raise typer.BadParameter(
            f"Invalid access-via-public-ip '{value}'. "
            f"Must be one of: {', '.join(sorted(_VALID_ACCESS_VIA_PUBLIC_IP))}"
        )
