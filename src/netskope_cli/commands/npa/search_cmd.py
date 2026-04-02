"""NPA name validation and resource search commands.

These functions are intended to be registered directly on npa_app in __init__.py
rather than having their own Typer sub-app.
"""

from __future__ import annotations

import urllib.parse
from typing import Annotated

import typer

from netskope_cli.commands.npa._helpers import (
    _build_client,
    _get_formatter,
    _get_output_format,
)
from netskope_cli.core.output import spinner

# ---------------------------------------------------------------------------
# Valid choices
# ---------------------------------------------------------------------------
_VALID_RESOURCE_TYPES = [
    "publisher",
    "private_app",
    "policy",
    "policy_group",
    "upgrade_profile",
    "local_broker",
]

_VALID_SEARCH_TYPES = [
    "publishers",
    "private_apps",
]


# ---------------------------------------------------------------------------
# Commands (registered on npa_app from __init__.py)
# ---------------------------------------------------------------------------


def validate_name(
    ctx: typer.Context,
    resource_type: Annotated[
        str,
        typer.Option(
            "--resource-type",
            help="Type of NPA resource to validate the name for. "
            "Choices: publisher, private_app, policy, policy_group, upgrade_profile, local_broker.",
        ),
    ],
    name: Annotated[
        str,
        typer.Option(
            "--name",
            help="The name to validate for the given resource type.",
        ),
    ],
) -> None:
    """Validate a resource name for uniqueness and correctness.

    Queries GET /api/v2/infrastructure/npa/namevalidation with the given
    resource type and name.

    Examples:
        netskope npa validate-name --resource-type publisher --name "My Publisher"
        netskope npa validate-name --resource-type private_app --name "SSH Server"
    """
    if resource_type not in _VALID_RESOURCE_TYPES:
        raise typer.BadParameter(
            f"Invalid resource type '{resource_type}'. " f"Valid choices: {', '.join(_VALID_RESOURCE_TYPES)}."
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {
        "resourceType": resource_type,
        "name": name,
    }

    with spinner(f"Validating name '{name}' for {resource_type}..."):
        data = client.request("GET", "/api/v2/infrastructure/npa/namevalidation", params=params)

    formatter.format_output(data, fmt=fmt, title="Name Validation Result")


def search_resources(
    ctx: typer.Context,
    resource_type: Annotated[
        str,
        typer.Argument(help="Type of NPA resource to search. Choices: publishers, private_apps."),
    ],
    query: Annotated[
        str,
        typer.Option(
            "--query",
            "-q",
            help="Search query string to match against resource names and attributes.",
        ),
    ],
) -> None:
    """Search NPA resources by query string.

    Queries GET /api/v2/infrastructure/npa/search/{resource_type} with the
    provided query parameter.

    Examples:
        netskope npa search publishers --query "prod"
        netskope npa search private_apps --query "ssh"
    """
    if resource_type not in _VALID_SEARCH_TYPES:
        raise typer.BadParameter(
            f"Invalid resource type '{resource_type}'. " f"Valid choices: {', '.join(_VALID_SEARCH_TYPES)}."
        )

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    params: dict[str, object] = {"query": query}

    with spinner(f"Searching {resource_type} for '{query}'..."):
        path = f"/api/v2/infrastructure/npa/search/{urllib.parse.quote(resource_type, safe='')}"
        data = client.request("GET", path, params=params)

    formatter.format_output(data, fmt=fmt, title=f"NPA Search Results — {resource_type}")
