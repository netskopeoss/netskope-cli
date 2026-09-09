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
import re
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.markup import escape as rich_escape

from netskope_cli.core.exceptions import APIError, NetskopeError, ValidationError
from netskope_cli.core.fieldpaths import find_unmatched, top_level_name
from netskope_cli.core.filtering import Expr, apply_filter
from netskope_cli.core.output import (
    CountResult,
    flatten_grouped_results,
    page_is_capped,
    print_count,
    spinner,
    unwrap_api_response,
)

#: Most rows a single datasearch request returns, whatever ``limit`` asks for.
DATASEARCH_PAGE_CAP = 10_000

#: Rows ``--exact`` will page through before giving up and reporting ``N+``.
DEFAULT_COUNT_CEILING = 200_000
COUNT_CEILING_ENV = "NETSKOPE_COUNT_CEILING"

#: Help for every ``--api-fields`` option (events, alerts, incidents, NPA publishers and policy).
API_FIELDS_HELP = (
    "Comma-separated top-level field names the API should return (a server-side projection that reduces "
    "payload size). Widened automatically with any field named by --fields, --where or --sort so those keep "
    "working. Output shows these columns in this order unless --fields picks others. Omit to return every "
    "field. To choose columns client-side (nested paths, globs) use the global --fields; see 'ntsk docs fields'."
)

#: Help for the local ``--count`` option on the datasearch list commands.
COUNT_HELP = (
    f"Print only the count of matching records. Fetches up to {DATASEARCH_PAGE_CAP:,} rows (the API page cap) "
    "and prints N+ when that cap is hit; add the global --exact to page for the true total."
)


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
            f"{COUNT_CEILING_ENV} must be a positive integer, got {rich_escape(repr(raw))}.",
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
    #: Names widening added for --fields/--where/--sort; the user never typed them.
    widened: tuple[str, ...] = ()

    @property
    def projected(self) -> bool:
        """True when a projection is sent, so the API may legitimately omit fields."""
        return self.request is not None


_TRANSITION_NOTE = (
    "--fields now selects columns client-side on every command, so the API returned every field here. "
    "Add --api-fields NAMES to trim the response server-side, which is what --fields used to do on this command."
)


def _err_console(state: Any) -> Console:
    console = getattr(state, "console", None)
    if isinstance(console, Console):
        return console
    return Console(stderr=True, no_color=bool(getattr(state, "no_color", False)))


def resolve_api_fields(ctx: Any, api_fields: str | None, params: dict[str, Any] | None = None) -> ApiFieldSelection:
    """Widen ``--api-fields`` with the names ``--fields``/``--where``/``--sort`` need.

    When ``--api-fields`` is absent nothing is sent and, for one release, a
    one-line note on stderr tells users who pass a plain top-level ``--fields``
    list (the old server-side spelling) how to get the payload trimming back.
    Scripts that pipe the output are its audience, so the note ignores the
    non-TTY auto-quiet and is suppressed only by an explicit ``--quiet``.
    With *params* the request projection is stored under ``fields`` there.
    """
    selection = _resolve_api_fields(ctx, api_fields)
    if params is not None and selection.request is not None:
        params["fields"] = selection.request
    return selection


def _resolve_api_fields(ctx: Any, api_fields: str | None) -> ApiFieldSelection:
    state = getattr(ctx, "obj", None)
    global_fields: list[str] | None = getattr(state, "fields", None) or None
    requested = split_names(api_fields)

    if not requested:
        quiet = bool(getattr(state, "quiet_explicit", False))
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
        if name is None:
            continue
        # ``<field>_iso`` companions are synthesised client-side from ``<field>``.
        if name.endswith("_iso"):
            name = name[:-4]
        if name and name not in union:
            union.append(name)

    display = None if global_fields else list(dict.fromkeys(requested))
    widened = tuple(name for name in union if name not in requested)
    return ApiFieldSelection(request=",".join(union), display=display, widened=widened)


# ---------------------------------------------------------------------------
# --count and the page cap
# ---------------------------------------------------------------------------


def is_datasearch_endpoint(endpoint: str) -> bool:
    """The ``/datasearch/`` endpoints page by ``offset`` and cap a request at :data:`DATASEARCH_PAGE_CAP`."""
    return "/datasearch/" in endpoint


#: Events endpoints that state a ``total``, so ``--count`` needs only ``--limit`` rows there.
STATES_TOTAL_ENDPOINTS = ("/api/v2/events/data/audit",)


def counts_full_page(endpoint: str) -> bool:
    """``--count`` fetches a full :data:`DATASEARCH_PAGE_CAP` page on events endpoints that return no total.

    Only the datasearch ones are known to page by ``offset``; ``events/data/*``
    (infrastructure, transaction) count a single page and cannot be paged with
    ``--exact``.  Audit states a total, so its rows would be fetched only to be
    discarded.
    """
    return endpoint.startswith("/api/v2/events/") and endpoint not in STATES_TOTAL_ENDPOINTS


def is_page_capped(data: Any, limit: int, *, where_active: bool = False) -> bool:
    """True when a response filled the ``limit``-row page and the count is therefore a lower bound.

    The rule is :func:`netskope_cli.core.output.page_is_capped`; this unwraps
    the envelope first.
    """
    records, meta = unwrap_api_response(data)
    if not isinstance(records, list):
        return False
    return page_is_capped(meta, len(records), limit, where_active=where_active)


def raise_on_error_envelope(page: Any) -> None:
    """Datasearch reports query errors as HTTP 200 with ``ok: 0``; never render or count that as data."""
    if isinstance(page, dict):
        ok = page.get("ok")
        if ok is not None and not ok:
            msg = page.get("message") or page.get("error") or "Unknown API error"
            raise NetskopeError(f"API returned an error: {rich_escape(str(msg))}", details=page)


def request_with_projection(client: Any, endpoint: str, params: dict[str, Any], selection: ApiFieldSelection) -> Any:
    """``client.request`` that explains an HTTP 400 caused by a name widening added to ``fields``."""
    try:
        return client.request("GET", endpoint, params=params)
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        if (status == 400 or "HTTP 400" in exc.message) and selection.widened:
            culprits = [n for n in selection.widened if re.search(rf"\b{re.escape(n)}\b", exc.message)]
            if culprits:
                exc.suggestion = (
                    f"{', '.join(culprits)} was added to --api-fields because --fields, --where or --sort reference "
                    "it, and the API does not accept it as a projection. Drop --api-fields, or remove the reference "
                    "and filter client-side."
                )
        raise


#: What a capped count should tell the user to do, by whether ``--exact`` can page the endpoint.
CAPPED_HINT_EXACT = "narrow the time range or use --exact"
CAPPED_HINT_NO_EXACT = "narrow the time range (--exact cannot page this endpoint)"


@dataclass(frozen=True)
class Page:
    """One fetched page and everything the formatter needs to know about how it was fetched."""

    data: Any
    selection: ApiFieldSelection
    count: bool
    #: The page size the API stopped at when the page filled it (a count is then a lower bound).
    capped_at: int | None
    #: Passed as ``format_output(capped_hint=)``; only meaningful when ``capped_at`` is set.
    capped_hint: str = CAPPED_HINT_EXACT

    def format_kwargs(self, ctx: Any) -> dict[str, Any]:
        """The ``format_output`` keywords this page determines (add ``fmt``, ``title``, ``default_fields``)."""
        state = getattr(ctx, "obj", None)
        return {
            "fields": self.selection.display,
            "count_only": self.count,
            "capped_at": self.capped_at,
            "capped_hint": self.capped_hint,
            "strip_internal": not bool(getattr(state, "raw", False)),
            "add_iso_timestamps": not bool(getattr(state, "epoch", False)),
        }


def fetch_page(
    ctx: Any,
    client: Any,
    endpoint: str,
    params: dict[str, Any],
    *,
    api_fields: str | None,
    limit: int,
    count: bool,
    spinner_text: str,
    api_fields_supported: bool = True,
) -> Page | None:
    """Run the request for a list/count command, or the whole ``--exact`` count.

    Reads ``--exact``, ``--where``, ``--quiet``, ``--no-color`` and the output
    format from ``ctx.obj`` and resolves ``--api-fields`` (widened for the
    client-side options) into ``params["fields"]``.  A ``--count`` on an
    events endpoint without a total asks for a full :data:`DATASEARCH_PAGE_CAP`
    page and a full page is a lower bound; elsewhere the request uses *limit*
    and the envelope total speaks for itself.  With ``--exact`` on a
    datasearch endpoint the count is paged and printed here and ``None`` is
    returned; that needs a ``starttime`` (the commands resolve ``--start`` to a
    fixed epoch once, which pins the window across pages), since paging the
    API's rolling default window would count a moving target.  An HTTP 200
    ``ok: 0`` body raises, and an HTTP 400 for a name widening added to the
    projection says which option did it.
    """
    state = getattr(ctx, "obj", None)
    exact = bool(getattr(state, "exact", False))
    where: Expr | None = getattr(state, "where_expr", None)
    quiet = bool(getattr(state, "quiet", False))
    no_color = bool(getattr(state, "no_color", False))
    fmt = getattr(getattr(state, "output", None), "value", None)
    console = Console(stderr=True, no_color=no_color)

    # ``events get`` has no --api-fields option, so it must not print the transition note.
    selection = resolve_api_fields(ctx, api_fields, params) if api_fields_supported else ApiFieldSelection(None, None)

    datasearch = is_datasearch_endpoint(endpoint)
    if count and exact:
        if not datasearch:
            if not quiet:
                console.print("[dim]--exact applies to the datasearch endpoints only; counting a single page.[/dim]")
        elif "groupbys" in params:
            if not quiet:
                console.print("[dim]--exact does not page group-by results; counting the groups on one page.[/dim]")
        else:
            if "starttime" not in params:
                raise ValidationError(
                    "--exact needs a time window: pass --start (for example --start 7d).",
                    suggestion="Every page is then counted against the same fixed window; without one the API "
                    "applies a rolling default and rows arriving mid-count would shift the pages.",
                )
            ceiling = count_ceiling()
            result = count_exact(
                client,
                endpoint,
                params,
                selection=selection,
                where=where,
                ceiling=ceiling,
                quiet=quiet,
                no_color=no_color,
            )
            print_exact_count(result, where=where is not None, ceiling=ceiling, quiet=quiet, no_color=no_color, fmt=fmt)
            return None

    paged = count and counts_full_page(endpoint)
    params["limit"] = DATASEARCH_PAGE_CAP if paged else limit
    with spinner(spinner_text, no_color=no_color, quiet=quiet):
        data = request_with_projection(client, endpoint, params, selection)
    raise_on_error_envelope(data)
    capped = paged and is_page_capped(data, DATASEARCH_PAGE_CAP, where_active=where is not None)
    hint = CAPPED_HINT_EXACT if datasearch else CAPPED_HINT_NO_EXACT
    return Page(data, selection, count, DATASEARCH_PAGE_CAP if capped else None, hint)


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
    selection: ApiFieldSelection | None = None,
    where: Expr | None = None,
    ceiling: int | None = None,
    page_size: int = DATASEARCH_PAGE_CAP,
    quiet: bool = False,
    no_color: bool = False,
) -> ExactCount:
    """Page through *endpoint* with ``offset`` and count the rows (matching *where* if given).

    Stops at the first short page (exact) or once *ceiling* rows have been
    fetched (``reached_ceiling``).  Only the running count is kept, so memory
    stays flat however many pages are read.  A page whose first ``_id`` is the
    previous page's means the endpoint ignored ``offset``; that raises rather
    than counting the first page twice or, worse, reporting it as exact.  A
    ``--api-fields`` projection is widened with ``_id`` so the check always
    has something to compare (the rows are counted, never rendered).  A total
    that is an exact multiple of *page_size* costs one extra, empty request
    and cannot be told from an endpoint that answers an empty page past its
    window.  *selection* lets an HTTP 400 for a widened ``--api-fields`` name
    be explained as :func:`request_with_projection` does.
    """
    ceiling = count_ceiling() if ceiling is None else ceiling
    base = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    projection = split_names(base.get("fields")) if isinstance(base.get("fields"), str) else []
    if projection and "_id" not in projection:
        base["fields"] = ",".join([*projection, "_id"])
    count = fetched = requests = 0
    offset = 0
    reached_ceiling = False
    previous_first_id: Any = None

    with spinner("Counting...", no_color=no_color, quiet=quiet) as progress:
        while True:
            # Never fetch past the ceiling: the last page is trimmed so the
            # reported "N+" is the ceiling itself, not a page-size overshoot.
            size = min(page_size, ceiling - fetched)
            if size <= 0:
                reached_ceiling = True
                break
            page_params = {**base, "limit": size, "offset": offset}
            if selection is not None:
                page = request_with_projection(client, endpoint, page_params, selection)
            else:
                page = client.request("GET", endpoint, params=page_params)
            requests += 1
            raise_on_error_envelope(page)
            records, _meta = unwrap_api_response(page)
            rows = records if isinstance(records, list) else []
            first_id = rows[0].get("_id") if rows and isinstance(rows[0], dict) else None
            if first_id is not None and requests > 1 and first_id == previous_first_id:
                raise NetskopeError(
                    f"{endpoint} returned the same first row (_id {rich_escape(str(first_id))}) at offset "
                    f"{offset:,} as at offset {offset - size:,}, so it is not honouring offset paging and "
                    "--exact cannot count it.",
                    suggestion="Drop --exact and narrow the time range until the plain --count is not capped.",
                )
            previous_first_id = first_id
            fetched += len(rows)
            if where is not None:
                # Same view of the rows as the formatter: group-by responses are
                # flattened first, and a filter path no row has is called out once.
                rows_for_filter = flatten_grouped_results(rows)
                if requests == 1 and rows_for_filter:
                    for path in dict.fromkeys(where.paths()):
                        if find_unmatched(rows_for_filter, [path]):
                            Console(stderr=True, no_color=no_color).print(
                                f"[yellow]--where:[/yellow] '{rich_escape(path)}' is not present in any record. "
                                "[dim]Nothing will match; see --list-fields.[/dim]"
                            )
                kept, _removed = apply_filter(rows_for_filter, where)
                count += len(kept)
            else:
                count += len(rows)
            if len(rows) < size:
                break
            offset += len(rows)
            if progress is not None and progress.task_ids:
                progress.update(progress.task_ids[0], description=f"Counting... {fetched:,} rows so far")

    return ExactCount(count=count, fetched=fetched, requests=requests, reached_ceiling=reached_ceiling)


def print_exact_count(
    result: ExactCount,
    *,
    where: bool,
    ceiling: int,
    quiet: bool,
    no_color: bool,
    fmt: str | None = None,
) -> None:
    """Print an :class:`ExactCount` the way ``--count`` does (:func:`print_count`): number on stdout, notes on stderr.

    The ceiling warning is printed even under ``--quiet`` (the count is a lower
    bound, which a pipeline consumer needs to know); the ``--where`` summary is
    informational and is suppressed.
    """
    console = Console(stderr=True, no_color=no_color)
    hint = None
    if result.reached_ceiling:
        hint = (
            f"Count reached the --exact ceiling of {ceiling:,} rows after {result.requests} requests; "
            f"narrow the time range or raise {COUNT_CEILING_ENV}."
        )
    print_count(CountResult(result.count, result.reached_ceiling, hint), fmt=fmt, err_console=console)
    if where and not quiet:
        console.print(f"[dim]{result.count:,} of {result.fetched:,} rows matched --where[/dim]")
