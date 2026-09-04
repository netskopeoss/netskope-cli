"""Server-side ``fields`` projections and the datasearch page cap.

Two API quirks need handling the generic formatter cannot do on its own:

* Some endpoints (events/alerts/incidents datasearch, NPA publishers and
  policy) accept a server-side ``fields`` projection of top-level names,
  exposed by the commands as ``--api-fields``.  The global ``--fields``,
  ``--where`` and ``--sort`` run client-side on whatever came back, so
  :func:`resolve_api_fields` widens the request projection to every
  top-level name those options reference.  Otherwise a filter on a field the
  server stripped could never match (``--where 'action eq "block"'`` used to
  report ``action`` absent from every record).
* The datasearch endpoints return at most :data:`DATASEARCH_PAGE_CAP` rows
  per request and no total, so a ``--count`` that fills the page is a lower
  bound.  :func:`is_page_capped` detects that and :func:`count_exact` pages
  with ``offset`` for the true total (bounded by :func:`count_ceiling`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from netskope_cli.core.exceptions import ValidationError
from netskope_cli.core.fieldpaths import top_level_name
from netskope_cli.core.filtering import Expr, apply_filter
from netskope_cli.core.output import spinner, unwrap_api_response

#: Most rows a single datasearch request returns, whatever ``limit`` asks for.
DATASEARCH_PAGE_CAP = 10_000

#: Rows ``--exact`` will page through before giving up and reporting ``N+``.
DEFAULT_COUNT_CEILING = 200_000
COUNT_CEILING_ENV = "NETSKOPE_COUNT_CEILING"


def count_ceiling() -> int:
    """Return the ``--exact`` row ceiling (``NETSKOPE_COUNT_CEILING`` or the default)."""
    raw = os.environ.get(COUNT_CEILING_ENV, "").strip()
    if not raw:
        return DEFAULT_COUNT_CEILING
    try:
        value = int(raw.replace(",", "").replace("_", ""))
    except ValueError:
        value = 0
    if value <= 0:
        raise ValidationError(
            f"{COUNT_CEILING_ENV} must be a positive integer, got {raw!r}.",
            suggestion=f"Unset it to use the default of {DEFAULT_COUNT_CEILING:,} rows.",
        )
    return value


def split_names(value: str | None) -> list[str]:
    """Split a comma-separated option value into stripped, non-empty names."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# --api-fields
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApiFieldSelection:
    """Result of :func:`resolve_api_fields`.

    ``request`` is the value for the API ``fields`` parameter (``None`` sends
    no projection).  ``display`` is what to pass as ``format_output(fields=)``:
    the user's ``--api-fields`` list when no global ``--fields`` was given, so
    the output keeps the requested order and drops the columns the widening
    added; ``None`` otherwise, letting the formatter apply the global
    ``--fields`` or the command's defaults.
    """

    request: str | None
    display: list[str] | None


_TRANSITION_NOTE = (
    "--fields now selects columns client-side on every command, so the API returned every field here. "
    "Add --api-fields NAMES to trim the response server-side, which is what --fields used to do on this command."
)


def _err_console(state: Any) -> Console:
    console = getattr(state, "console", None)
    if isinstance(console, Console):
        return console
    return Console(stderr=True, no_color=bool(getattr(state, "no_color", False)))


def resolve_api_fields(ctx: Any, api_fields: str | None) -> ApiFieldSelection:
    """Widen ``--api-fields`` with the names ``--fields``/``--where``/``--sort`` need.

    When ``--api-fields`` is absent nothing is sent and, for one release, a
    one-line note on stderr tells users who pass a plain top-level ``--fields``
    list (the old server-side spelling) how to get the payload trimming back.
    """
    state = getattr(ctx, "obj", None)
    global_fields: list[str] | None = getattr(state, "fields", None) or None
    requested = split_names(api_fields)

    if not requested:
        quiet = bool(getattr(state, "quiet", False))
        if global_fields and not quiet and all(top_level_name(f) == f for f in global_fields):
            _err_console(state).print(f"[dim]{_TRANSITION_NOTE}[/dim]", soft_wrap=True)
        return ApiFieldSelection(request=None, display=None)

    referenced: list[str] = list(global_fields or [])
    where_expr: Expr | None = getattr(state, "where_expr", None)
    if where_expr is not None:
        referenced.extend(where_expr.paths())
    for path, _descending in getattr(state, "sort_spec", None) or []:
        referenced.append(path)

    union = list(dict.fromkeys(requested))
    for spec in referenced:
        name = top_level_name(spec)
        if name and name not in union:
            union.append(name)

    display = None if global_fields else list(dict.fromkeys(requested))
    return ApiFieldSelection(request=",".join(union), display=display)


# ---------------------------------------------------------------------------
# --count and the page cap
# ---------------------------------------------------------------------------


def is_page_capped(data: Any, limit: int) -> bool:
    """True when a response filled the ``limit``-row page and carries no larger total.

    Datasearch responses have no total, or a ``status.count`` equal to the
    rows returned, so a full page means "at least this many".  A response
    whose envelope total exceeds the page is exact and not capped.
    """
    records, meta = unwrap_api_response(data)
    if not isinstance(records, list) or len(records) < limit:
        return False
    total = meta.get("total") or meta.get("totalResults") or meta.get("status.count") or meta.get("status.total")
    if total is None:
        return True
    try:
        return int(total) <= len(records)
    except (TypeError, ValueError):
        return True


@dataclass(frozen=True)
class ExactCount:
    count: int
    fetched: int
    requests: int
    reached_ceiling: bool


def count_exact(
    client: Any,
    endpoint: str,
    params: dict[str, Any],
    *,
    where: Expr | None = None,
    ceiling: int | None = None,
    page_size: int = DATASEARCH_PAGE_CAP,
    quiet: bool = False,
    no_color: bool = False,
) -> ExactCount:
    """Page through *endpoint* with ``offset`` and count the rows (matching *where* if given).

    Stops at the first short page (exact) or once *ceiling* rows have been
    fetched (``reached_ceiling``).  Only the running count is kept, so memory
    stays flat however many pages are read.
    """
    ceiling = count_ceiling() if ceiling is None else ceiling
    base = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count = fetched = requests = 0
    offset = 0
    reached_ceiling = False

    with spinner("Counting...", no_color=no_color, quiet=quiet) as progress:
        while True:
            page = client.request("GET", endpoint, params={**base, "limit": page_size, "offset": offset})
            requests += 1
            records, _meta = unwrap_api_response(page)
            rows = records if isinstance(records, list) else []
            fetched += len(rows)
            if where is not None:
                kept, _removed = apply_filter(rows, where)
                count += len(kept)
            else:
                count += len(rows)
            if len(rows) < page_size:
                break
            if fetched >= ceiling:
                reached_ceiling = True
                break
            offset += len(rows)
            if progress is not None and progress.task_ids:
                progress.update(progress.task_ids[0], description=f"Counting... {fetched:,} rows so far")

    return ExactCount(count=count, fetched=fetched, requests=requests, reached_ceiling=reached_ceiling)


def print_exact_count(result: ExactCount, *, where: bool, ceiling: int, quiet: bool, no_color: bool) -> None:
    """Print an :class:`ExactCount` the way ``--count`` does: the number on stdout, notes on stderr.

    The ceiling warning is printed even under ``--quiet`` (the count is a lower
    bound, which a pipeline consumer needs to know); the ``--where`` summary is
    informational and is suppressed.
    """
    print(f"{result.count}+" if result.reached_ceiling else result.count)
    console = Console(stderr=True, no_color=no_color)
    if where and not quiet:
        console.print(f"[dim]{result.count:,} of {result.fetched:,} rows matched --where[/dim]")
    if result.reached_ceiling:
        console.print(
            f"[yellow]Count reached the --exact ceiling of {ceiling:,} rows after {result.requests} requests; "
            f"narrow the time range or raise {COUNT_CEILING_ENV}.[/yellow]"
        )
