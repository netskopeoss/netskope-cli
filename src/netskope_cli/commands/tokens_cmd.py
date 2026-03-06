"""API Token management commands for the Netskope CLI.

Provides subcommands for creating, listing, inspecting, updating, and
revoking API tokens used to authenticate against the Netskope REST API.
Use these commands to rotate credentials, audit active tokens, and
manage token scopes without logging into the Netskope console.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, spinner

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------

tokens_app = typer.Typer(
    name="tokens",
    help="API Token Management — create, inspect, update, and revoke tokens.",
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


def _build_client(ctx: typer.Context) -> NetskopeClient:
    return build_client(ctx)


def _build_formatter(ctx: typer.Context) -> OutputFormatter:
    """Create an OutputFormatter respecting global flags."""
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


@tokens_app.command("list")
def tokens_list(ctx: typer.Context) -> None:
    """List all API tokens configured in your Netskope tenant.

    Queries GET /api/v2/auth/tokens and returns every token record
    including its name, creation date, last-used timestamp, and the
    set of endpoint scopes it is authorised for.  Token values
    themselves are never returned by the API for security reasons.
    Use this command to audit which tokens exist and whether any are
    unused or over-provisioned.

    Examples:
        # List all tokens as a table
        netskope tokens list

        # Output as JSON for scripting
        netskope -o json tokens list

        # List tokens from a specific profile
        netskope --profile prod tokens list
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner("Fetching API tokens...", no_color=no_color):
        data = client.request("GET", "/api/v2/auth/tokens")

    formatter.format_output(data, fmt=_get_output_format(ctx), title="API Tokens")


@tokens_app.command("create")
def tokens_create(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        help=(
            "A descriptive name for the new API token.  Choose something that "
            "identifies its purpose, such as 'ci-pipeline-read' or "
            "'siem-integration'.  The name must be unique within the tenant."
        ),
    ),
    endpoints: str = typer.Option(
        ...,
        "--endpoints",
        help=(
            "Comma-separated list of API endpoint scopes the token is allowed "
            "to access.  Each scope corresponds to a Netskope REST endpoint "
            "group (e.g. '/api/v2/events,/api/v2/alerts').  Granting only the "
            "required scopes follows the principle of least privilege."
        ),
    ),
) -> None:
    """Create a new API token with specific endpoint scopes.

    Sends POST /api/v2/auth/tokens to generate a new token.  The API
    will return the token value exactly once in the response — store it
    securely, because it cannot be retrieved again.  Assign the minimum
    set of endpoint scopes the consumer needs.

    Examples:
        # Create a token for a SIEM integration
        netskope tokens create --name "splunk-ingest" --endpoints "/api/v2/events,/api/v2/alerts"

        # Create a token scoped to policy read-only
        netskope tokens create --name "policy-auditor" --endpoints "/api/v2/policy"

        # Create a token and capture the value from JSON output
        netskope -o json tokens create --name "ci-token" --endpoints "/api/v2/events"
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    endpoint_list = [e.strip() for e in endpoints.split(",") if e.strip()]

    body: dict[str, object] = {
        "name": name,
        "endpoints": endpoint_list,
    }

    with spinner("Creating API token...", no_color=no_color):
        data = client.request("POST", "/api/v2/auth/tokens", json_data=body)

    echo_success(f"Token '{name}' created.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title="Created Token")


@tokens_app.command("get")
def tokens_get(
    ctx: typer.Context,
    token_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the token to retrieve.  Run "
            "'netskope tokens list' to find token IDs.  The token value "
            "itself is not included in the response for security reasons."
        ),
    ),
) -> None:
    """Get metadata for a specific API token.

    Queries GET /api/v2/auth/tokens/{id} and returns the token's name,
    creation date, last-used timestamp, and authorised endpoint scopes.
    The actual token secret is never returned.  Use this command to
    verify a token's configuration before updating or revoking it.

    Examples:
        # Inspect token with ID 7
        netskope tokens get 7

        # Output as YAML for readability
        netskope -o yaml tokens get 7
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    with spinner(f"Fetching token {token_id}...", no_color=no_color):
        data = client.request("GET", f"/api/v2/auth/tokens/{token_id}")

    formatter.format_output(data, fmt=_get_output_format(ctx), title=f"API Token {token_id}")


@tokens_app.command("update")
def tokens_update(
    ctx: typer.Context,
    token_id: int = typer.Argument(
        ...,
        help=("Unique numeric identifier of the token to update.  Run " "'netskope tokens list' to find token IDs."),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=(
            "New name for the token.  If not provided, the existing name is "
            "kept.  Renaming a token does not invalidate it or change its "
            "secret value."
        ),
    ),
    endpoints: Optional[str] = typer.Option(
        None,
        "--endpoints",
        help=(
            "Comma-separated list of API endpoint scopes to replace the "
            "current scopes with.  This is a full replacement, not an "
            "additive update — include all desired scopes in the list."
        ),
    ),
) -> None:
    """Update the name or endpoint scopes of an existing API token.

    Sends PUT /api/v2/auth/tokens/{id} to modify a token's metadata.
    You can change the name, the endpoint scopes, or both.  The token
    secret itself is not changed by this operation.  If you need to
    rotate the secret, revoke the old token and create a new one.

    Examples:
        # Rename a token
        netskope tokens update 7 --name "renamed-token"

        # Update the endpoint scopes
        netskope tokens update 7 --endpoints "/api/v2/events,/api/v2/alerts"

        # Update both name and scopes
        netskope tokens update 7 --name "new-name" --endpoints "/api/v2/events"
    """
    client = _build_client(ctx)
    formatter = _build_formatter(ctx)
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    body: dict[str, object] = {}
    if name is not None:
        body["name"] = name
    if endpoints is not None:
        body["endpoints"] = [e.strip() for e in endpoints.split(",") if e.strip()]

    if not body:
        typer.echo("Nothing to update. Provide --name and/or --endpoints.", err=True)
        raise typer.Exit(code=1)

    with spinner(f"Updating token {token_id}...", no_color=no_color):
        data = client.request("PUT", f"/api/v2/auth/tokens/{token_id}", json_data=body)

    echo_success(f"Token {token_id} updated.", no_color=no_color)
    if data:
        formatter.format_output(data, fmt=_get_output_format(ctx), title=f"Updated Token {token_id}")


@tokens_app.command("revoke")
def tokens_revoke(
    ctx: typer.Context,
    token_id: int = typer.Argument(
        ...,
        help=(
            "Unique numeric identifier of the token to revoke.  Run "
            "'netskope tokens list' to find token IDs.  Revocation is "
            "permanent and cannot be undone."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and immediately revoke "
            "the token.  Useful for scripted or CI/CD workflows where no "
            "terminal is available for user input."
        ),
    ),
) -> None:
    """Revoke (delete) an API token permanently.

    Sends DELETE /api/v2/auth/tokens/{id} to revoke the token.  Any
    integrations or scripts using this token will immediately lose
    access.  This action cannot be undone — you will need to create a
    new token if access is required again.  Always verify that no
    active integrations depend on the token before revoking.

    Examples:
        # Revoke token 7 (will prompt for confirmation)
        netskope tokens revoke 7

        # Revoke without confirmation for CI pipelines
        netskope tokens revoke 7 --yes

        # Revoke from a specific profile
        netskope --profile prod tokens revoke 12 -y
    """
    no_color = ctx.obj.no_color if ctx.obj is not None else False

    if not yes:
        typer.confirm(
            f"Are you sure you want to revoke token {token_id}? This cannot be undone.",
            abort=True,
        )

    client = _build_client(ctx)

    with spinner(f"Revoking token {token_id}...", no_color=no_color):
        client.request("DELETE", f"/api/v2/auth/tokens/{token_id}")

    echo_success(f"Token {token_id} revoked.", no_color=no_color)


# Hidden alias so "tokens delete <id>" also works.
tokens_app.command("delete", hidden=True)(tokens_revoke)
