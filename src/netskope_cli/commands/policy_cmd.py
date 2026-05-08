"""Policy management commands for the Netskope CLI.

Provides URL list CRUD operations and policy deployment.
"""

from __future__ import annotations

from typing import Optional

import typer

from netskope_cli.core.client import NetskopeClient, build_client
from netskope_cli.core.output import OutputFormatter, echo_success, echo_warning

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

policy_app = typer.Typer(
    name="policy",
    help=(
        "Manage security policies on the Netskope platform.\n\n"
        "This command group provides URL list CRUD operations and policy deployment. "
        "URL lists define sets of URLs or domains that can be referenced by security "
        "policies for allow/block decisions. After making changes to URL lists, use "
        "'policy deploy' to push all pending changes to the live tenant configuration."
    ),
    no_args_is_help=True,
)

url_list_app = typer.Typer(
    name="url-list",
    help=(
        "Create, list, update, and delete URL lists used in security policies.\n\n"
        "URL lists define collections of URLs or domain patterns that policies "
        "reference for allow, block, or alert actions. Each list has a name, "
        "a matching type (exact or regex), and a set of URL entries."
    ),
    no_args_is_help=True,
)

policy_app.add_typer(url_list_app, name="url-list")
policy_app.add_typer(url_list_app, name="url-lists", hidden=True)


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


# ---------------------------------------------------------------------------
# URL List commands
# ---------------------------------------------------------------------------


@url_list_app.command("create")
def url_list_create(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help=(
            "A descriptive name for the new URL list. This name is displayed in the "
            "Netskope admin console and referenced by policies. Must be unique within "
            "your tenant."
        ),
    ),
    urls: str = typer.Option(
        ...,
        "--urls",
        help=(
            "Comma-separated list of URLs or domains to include in the list. "
            "For exact matching, provide full domains like 'example.com,bad-site.org'. "
            "For regex matching, provide patterns like '.*\\.example\\.com,malware-.*\\.net'."
        ),
    ),
    list_type: str = typer.Option(
        "exact",
        "--type",
        help=(
            "URL matching type for this list. Valid values: 'exact' for literal domain "
            "matching, or 'regex' for regular expression pattern matching. Defaults to "
            "'exact'. Use 'regex' when you need wildcard or pattern-based matching."
        ),
    ),
) -> None:
    """Create a new URL list for use in security policies.

    Sends POST /api/v2/policy/urllist to create a named URL list. After creating
    the list, reference it in your security policies and run 'netskope policy deploy'
    to activate the changes.

    Examples:
        netskope policy url-list create "Blocked Sites" --urls "malware.com,phishing.org"
        netskope policy url-list create "Partner Domains" --urls "partner1.com,partner2.com" --type exact
        netskope policy url-list create "Shadow IT" --urls ".*\\.personal-cloud\\..*" --type regex
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    url_items = [u.strip() for u in urls.split(",") if u.strip()]

    body = {
        "name": name,
        "data": {
            "urls": url_items,
            "type": list_type,
        },
    }

    result = client.request("POST", "/api/v2/policy/urllist", json_data=body)

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"URL list '{name}' created.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title="Created URL List")


@url_list_app.command("list")
def url_list_list(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help=(
            "Maximum number of URL lists to return in a single response. Use this for "
            "pagination when you have many URL lists. Omit to return all lists. "
            "Combine with --offset for paginated retrieval."
        ),
    ),
    offset: Optional[int] = typer.Option(
        None,
        "--offset",
        help=(
            "Number of URL lists to skip before returning results. Use this together "
            "with --limit for pagination. For example, --offset 20 --limit 10 returns "
            "items 21-30. Defaults to 0 (start from the beginning)."
        ),
    ),
    fields: Optional[str] = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated list of field names to include in the response.",
    ),
    count: bool = typer.Option(False, "--count", help="Print only the total count."),
) -> None:
    """List all URL lists configured in the tenant.

    Fetches all URL lists from GET /api/v2/policy/urllist with optional pagination.
    Use this to audit existing URL lists, find list IDs for updates, or verify
    that a newly created list is present.

    Examples:
        netskope policy url-list list
        netskope policy url-list list --limit 10 --offset 0
        netskope -o json policy url-list list
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)
    state = ctx.obj

    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    result = client.request("GET", "/api/v2/policy/urllist", params=params or None)

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    formatter.format_output(
        result,
        fmt=fmt,
        title="URL Lists",
        default_fields=["id", "name", "modify_by", "modify_time", "pending"],
        fields=field_list,
        count_only=count,
        strip_internal=not (state.raw if state else False),
        add_iso_timestamps=not (state.epoch if state else False),
    )


@url_list_app.command("get")
def url_list_get(
    ctx: typer.Context,
    url_list_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the URL list to retrieve. Find IDs by running "
            "'netskope policy url-list list'. The ID is a tenant-unique integer "
            "assigned when the list was created."
        ),
    ),
) -> None:
    """Retrieve details of a specific URL list by its ID.

    Fetches a single URL list from GET /api/v2/policy/urllist/{id} including
    its name, type, and all URL entries. Use this to inspect the contents of a
    list before updating or to verify changes after an update.

    Examples:
        netskope policy url-list get 42
        netskope -o json policy url-list get 42
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    result = client.request("GET", f"/api/v2/policy/urllist/{url_list_id}")

    formatter.format_output(
        result,
        fmt=fmt,
        title=f"URL List {url_list_id}",
        default_fields=["id", "name", "type", "modify_by", "modify_time", "pending"],
    )


@url_list_app.command("update")
def url_list_update(
    ctx: typer.Context,
    url_list_id: int = typer.Argument(
        ...,
        help=("Numeric ID of the URL list to update. Find IDs by running " "'netskope policy url-list list'."),
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=("New name for the URL list. Omit to keep the current name. Must be unique " "within your tenant."),
    ),
    urls: Optional[str] = typer.Option(
        None,
        "--urls",
        help=(
            "Comma-separated URLs or domains that will REPLACE the existing entries. "
            "This is a full replacement, not an append. Include all desired URLs. "
            "For example: 'site1.com,site2.com,site3.com'."
        ),
    ),
    list_type: Optional[str] = typer.Option(
        None,
        "--type",
        help=(
            "New URL matching type. Valid values: 'exact' or 'regex'. Omit to keep the "
            "current type. Changing from exact to regex (or vice versa) affects how all "
            "entries in the list are interpreted."
        ),
    ),
) -> None:
    """Update an existing URL list by ID.

    Sends PUT /api/v2/policy/urllist/{id} with the provided changes. Note that
    --urls performs a full replacement of all entries. After updating, run
    'netskope policy deploy' to activate the changes.

    Examples:
        netskope policy url-list update 42 --name "Updated Block List"
        netskope policy url-list update 42 --urls "new-site.com,other-site.com"
        netskope policy url-list update 42 --name "Regex Patterns" --type regex --urls ".*\\.test\\..*"
    """
    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    if name is None and urls is None and list_type is None:
        echo_warning(
            "No update options provided. Use --name, --urls, or --type.",
            no_color=ctx.obj.no_color if ctx.obj is not None else False,
        )
        raise typer.Exit(code=1)

    # The API rejects PUT bodies that omit name, data.urls, or data.type
    # ("name required", "urls must be an array of URLs", "data.type must be one of
    # exact, regex"). Fetch the existing list and merge the user's overrides on top
    # so callers only need to specify what they want to change.
    current = client.request("GET", f"/api/v2/policy/urllist/{url_list_id}")
    current_data = current.get("data") or {} if isinstance(current, dict) else {}

    new_name = name if name is not None else (current.get("name") if isinstance(current, dict) else None)
    new_urls = [u.strip() for u in urls.split(",") if u.strip()] if urls is not None else current_data.get("urls", [])
    new_type = list_type if list_type is not None else current_data.get("type", "exact")

    body = {"name": new_name, "data": {"urls": new_urls, "type": new_type}}
    result = client.request(
        "PUT",
        f"/api/v2/policy/urllist/{url_list_id}",
        json_data=body,
    )

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"URL list {url_list_id} updated.", no_color=no_color)
    formatter.format_output(result, fmt=fmt, title=f"Updated URL List {url_list_id}")


@url_list_app.command("delete")
def url_list_delete(
    ctx: typer.Context,
    url_list_id: int = typer.Argument(
        ...,
        help=(
            "Numeric ID of the URL list to delete. Find IDs by running "
            "'netskope policy url-list list'. This action cannot be undone."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and proceed with deletion. "
            "Required for non-interactive use (scripts, CI/CD, AI agents). "
            "Defaults to False (prompt for confirmation)."
        ),
    ),
) -> None:
    """Delete a URL list by ID.

    Sends DELETE /api/v2/policy/urllist/{id}. This is a destructive operation
    that cannot be undone. Any policies referencing this list may be affected.
    After deletion, run 'netskope policy deploy' to activate the change.

    Examples:
        netskope policy url-list delete 42
        netskope policy url-list delete 42 --yes
    """
    if not yes:
        typer.confirm(
            f"Are you sure you want to delete URL list {url_list_id}?",
            abort=True,
        )

    client = _build_client(ctx)

    result = client.request("DELETE", f"/api/v2/policy/urllist/{url_list_id}")

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success(f"URL list {url_list_id} deleted.", no_color=no_color)

    if result is not None:
        formatter = _get_formatter(ctx)
        fmt = _get_output_format(ctx)
        formatter.format_output(result, fmt=fmt, title="Delete Result")


# ---------------------------------------------------------------------------
# Policy deploy command
# ---------------------------------------------------------------------------


@policy_app.command("deploy")
def policy_deploy(
    ctx: typer.Context,
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip the interactive confirmation prompt and deploy immediately. Required "
            "for non-interactive use (scripts, CI/CD, AI agents). Use with extreme caution "
            "as this pushes all pending changes to production. Defaults to False."
        ),
    ),
) -> None:
    """Deploy all pending policy changes to the live tenant.

    Sends POST /api/v2/policy/deploy to apply all staged policy modifications
    to the production configuration. This is a critical operation that affects
    your live security posture. All URL list changes, policy rule updates, and
    other pending modifications will become active immediately.

    Examples:
        netskope policy deploy
        netskope policy deploy --yes
        netskope -o json policy deploy --yes
    """
    if not yes:
        echo_warning(
            "This will deploy ALL pending policy changes to your tenant.",
            no_color=ctx.obj.no_color if ctx.obj is not None else False,
        )
        typer.confirm("Do you want to proceed?", abort=True)

    client = _build_client(ctx)
    formatter = _get_formatter(ctx)
    fmt = _get_output_format(ctx)

    result = client.request("POST", "/api/v2/policy/deploy")

    no_color = ctx.obj.no_color if ctx.obj is not None else False
    echo_success("Policy changes deployed successfully.", no_color=no_color)

    if result is not None:
        formatter.format_output(result, fmt=fmt, title="Deploy Result")
