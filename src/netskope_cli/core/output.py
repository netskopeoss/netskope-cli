"""Output formatting module for the Netskope CLI.

Supports multiple output formats (json, table, csv, yaml, jsonl, human) with
automatic TTY detection, field selection, color control, and Rich-based
display utilities.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator, Sequence

import yaml
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from netskope_cli.core.fieldpaths import (
    FieldInfo,
    discover_schema,
    expand_field_specs,
    find_unmatched,
    is_glob,
    project_records,
    schema_rows,
    suggest_fields,
)
from netskope_cli.core.filtering import Expr, apply_filter, parse_filter, parse_sort_spec, sort_records

# ---------------------------------------------------------------------------
# API response envelope unwrapping
# ---------------------------------------------------------------------------

# Keys commonly found in Netskope API envelopes that contain the actual data.
_ENVELOPE_LIST_KEYS = ("result", "data", "Resources")

# Nested dict keys under "data" that may hold the real list of records.
_DATA_NESTED_KEYS = (
    "publishers",
    "private_apps",
    "tags",
    "apps",
    "users",
    "devices",
    "policies",
    "rules",
    "groups",
    "events",
    "alerts",
    "roles",
    "tunnels",
    "pops",
    "upgrade_profiles",
    "lbrokers",
    "releases",
    "policygroups",
    "private_apps_tags",
    "items",
    "violations",
)

# Metadata keys that may appear at the envelope level.
_METADATA_KEYS = (
    "total",
    "totalResults",
    "startIndex",
    "itemsPerPage",
    "status",
    "status_code",
    "execution",
    "count",
    "ok",
    "message",
    "wait_time",
)

# Exact column names considered "important" for wide-table auto-selection.
# Checked first (exact match, case-insensitive), then we fall back to substring
# matching for broader coverage.
_PRIORITY_EXACT_NAMES = (
    "name",
    "id",
    "_id",
    "status",
    "user",
    "userName",
    "app",
    "alert_name",
    "alert_type",
    "severity",
    "timestamp",
    "action",
    "type",
    "display_name",
    "displayName",
    "email",
    "active",
    "tenant",
    "description",
    "count",
    "publisher_name",
    "publisher_id",
    "site",
    "version",
)

_PRIORITY_SUBSTRINGS = (
    "name",
    "id",
    "user",
    "timestamp",
    "status",
    "type",
    "app",
    "action",
    "severity",
    "email",
    "description",
)

_WIDE_TABLE_MAX_COLUMNS = 10


def unwrap_api_response(
    data: Any,
) -> tuple[Any, dict[str, Any]]:
    """Extract actual records from a Netskope API envelope.

    Returns a ``(records, metadata)`` tuple.  *records* is the unwrapped
    payload (a list of dicts in the common case) and *metadata* is a dict
    of envelope-level information such as ``total``, ``status``, etc.

    The function tries common envelope shapes:
    1. ``{"result": [...]}``
    2. ``{"data": [...]}``
    3. ``{"Resources": [...]}``  (SCIM)
    4. ``{"data": {"publishers": [...], ...}}``  (nested dict with known key)
    5. Falls back to returning *data* as-is.
    """
    if not isinstance(data, dict):
        return data, {}

    # Collect metadata from the envelope.
    metadata: dict[str, Any] = {}
    for key in _METADATA_KEYS:
        if key in data:
            val = data[key]
            # "status" at the envelope level may itself be a dict.
            if isinstance(val, dict):
                for sub_k, sub_v in val.items():
                    metadata[f"status.{sub_k}"] = sub_v
            else:
                metadata[key] = val

    # 1-3: Top-level list keys.
    for key in _ENVELOPE_LIST_KEYS:
        if key in data and isinstance(data[key], list):
            return data[key], metadata

    # 4: "data" is a dict with a nested list under a known key.
    if "data" in data and isinstance(data["data"], dict):
        nested = data["data"]
        for nk in _DATA_NESTED_KEYS:
            if nk in nested and isinstance(nested[nk], list):
                return nested[nk], metadata

    # 5: Check for top-level keys that match known data keys (e.g. "roles").
    for nk in _DATA_NESTED_KEYS:
        if nk in data and isinstance(data[nk], list):
            return data[nk], metadata

    # 6: Nothing matched – return as-is.
    return data, metadata


#: Envelope keys that state how many rows exist in total.  ``status.count`` on the
#: datasearch endpoints is the number of rows returned, so it is not one of them.
TOTAL_KEYS = ("total", "totalResults", "status.total")

#: Formats a program parses: a count prints as a bare integer there (``N+`` would not parse).
MACHINE_FORMATS = ("json", "jsonl", "csv", "yaml")


def stdout_is_tty() -> bool:
    """True when stdout is a terminal (a person is reading; a pipe gets machine-friendly output)."""
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def envelope_total(metadata: dict[str, Any]) -> int | None:
    """The total an unwrapped envelope states, preferring a real total over ``status.count``.

    A stated ``0`` is an answer, not a missing value, so keys are tested with
    ``is not None`` rather than truthiness.
    """
    for key in (*TOTAL_KEYS, "status.count"):
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def page_is_capped(metadata: dict[str, Any], rows: int, limit: int, *, where_active: bool = False) -> bool:
    """True when a page of *rows* filled *limit* and nothing proves the count exact.

    Datasearch responses carry no total, or a ``status.count`` that is the
    rows returned, so a full page means "at least this many".  A response
    that states a real total (:data:`TOTAL_KEYS`) is exact whatever the total
    is.  With a client-side ``--where`` a full page is always a lower bound:
    the rows beyond it were never filtered.  ``--count``, ``ntsk status`` and
    ``alerts summary`` all use this one rule.
    """
    if rows < limit:
        return False
    if where_active:
        return True
    return not any(metadata.get(key) is not None for key in TOTAL_KEYS)


def page_count(metadata: dict[str, Any], rows: int, *, capped: bool, where_active: bool = False) -> int:
    """The count a page supports: a stated total, else the rows (or the better lower bound).

    With ``--where`` the envelope numbers describe unfiltered rows, so the
    filtered *rows* are the answer.  A capped page has no real total
    (:func:`page_is_capped` ruled one out) but a ``status.count`` above the
    rows returned is the better lower bound.
    """
    if where_active:
        return rows
    stated = envelope_total(metadata)
    if stated is None:
        return rows
    return max(stated, rows) if capped else stated


@dataclass(frozen=True)
class CountResult:
    """What ``--count`` prints: the number, whether it is a lower bound, and what to do about that."""

    count: int
    capped: bool
    hint: str | None = None


def print_count(result: CountResult, *, fmt: str | None, err_console: Console) -> None:
    """Print a :class:`CountResult` the one way every count path uses.

    The number goes to stdout.  A lower bound gets a ``+`` marker only when a
    person is reading (table/human output on a terminal); machine formats and
    pipes get the bare integer so ``$(ntsk ... --count)`` keeps parsing, and
    the *hint* goes to stderr as the record that it is a lower bound.
    """
    marker = result.capped and fmt not in MACHINE_FORMATS and stdout_is_tty()
    print(f"{result.count}+" if marker else result.count)
    if result.capped and result.hint:
        err_console.print(f"[yellow]{result.hint}[/yellow]")


def flatten_grouped_results(data: list) -> list:
    """Flatten group-by API responses.

    Detects responses shaped like ``[{"_id": {"field": "val"}, "count": N}, ...]``
    or ``[{"_id": {"field": "val"}}, ...]`` (no count from API) and flattens them
    to ``[{"field": "val", "count": N}, ...]``.
    """
    if not data or not isinstance(data, list):
        return data
    if all(isinstance(row, dict) and "_id" in row and isinstance(row["_id"], dict) for row in data):
        flattened = []
        for row in data:
            new_row = dict(row["_id"])
            for k, v in row.items():
                if k != "_id":
                    new_row[k] = v
            flattened.append(new_row)
        return flattened
    return data


# ---------------------------------------------------------------------------
# Colour / Console helpers
# ---------------------------------------------------------------------------

_NO_COLOR = os.environ.get("NO_COLOR") is not None


def _should_disable_color(no_color_flag: bool = False) -> bool:
    """Return True when colour output must be suppressed."""
    return _NO_COLOR or no_color_flag


def _make_console(*, no_color: bool = False, stderr: bool = False) -> Console:
    """Build a Rich Console respecting NO_COLOR semantics."""
    return Console(
        no_color=_should_disable_color(no_color),
        stderr=stderr,
    )


# Module-level consoles (lazily re-created only when the no_color flag
# differs from the env-var default).
_console = _make_console()
_err_console = _make_console(stderr=True)


# ---------------------------------------------------------------------------
# OutputFormatter
# ---------------------------------------------------------------------------


class OutputFormatter:
    """Renders arbitrary data in the requested output format.

    Parameters
    ----------
    no_color:
        Explicitly disable colour (mirrors ``--no-color`` CLI flag).
    max_col_width:
        Maximum column-value width before truncation in *table* mode.
    """

    FORMATS = ("json", "table", "csv", "yaml", "jsonl", "human")

    def __init__(
        self,
        *,
        no_color: bool = False,
        max_col_width: int = 80,
        count_only: bool = False,
        wide: bool = False,
        fields: Sequence[str] | None = None,
        where: Expr | str | None = None,
        sort: Sequence[tuple[str, bool]] | str | None = None,
        list_fields: bool = False,
        quiet: bool = False,
    ) -> None:
        """Create a formatter.

        The keyword arguments mirror the global CLI options: ``fields`` is the
        global ``--fields`` list, ``where`` a parsed (or raw) ``--where``
        expression, ``sort`` a parsed (or raw) ``--sort`` specification and
        ``list_fields`` the ``--list-fields`` switch.  Strings are parsed here
        so tests and ad-hoc callers can pass them directly.
        """
        self.no_color = no_color
        self.console = _make_console(no_color=no_color)
        self.err_console = _make_console(no_color=no_color, stderr=True)
        self.max_col_width = 0 if wide else max_col_width
        self._default_count_only = count_only
        self._wide = wide
        self._quiet = quiet
        self._global_fields: list[str] | None = [f.strip() for f in fields if f.strip()] if fields else None
        self._where: Expr | None = parse_filter(where) if isinstance(where, str) else where
        self._sort: list[tuple[str, bool]] | None = (
            parse_sort_spec(sort) if isinstance(sort, str) else (list(sort) if sort else None)
        )
        self._list_fields = list_fields
        self._fields_applied = False
        self._schema_cache: list[FieldInfo] | None = None

    # ----- public API -------------------------------------------------------

    def format_output(
        self,
        data: Any,
        *,
        fmt: str | None = None,
        fields: Sequence[str] | None = None,
        default_fields: Sequence[str] | None = None,
        title: str | None = None,
        unwrap: bool = True,
        verbose: bool = False,
        show_all_columns: bool = False,
        empty_hint: str | None = None,
        count_only: bool = False,
        strip_internal: bool = True,
        add_iso_timestamps: bool = True,
        capped_at: int | None = None,
        capped_hint: str | None = None,
    ) -> None:
        """Format and print *data* to stdout.

        Parameters
        ----------
        data:
            A ``dict``, a ``list[dict]``, or any JSON-serialisable value.
        fmt:
            One of ``FORMATS``.  When *None* the format is auto-detected:
            ``"human"`` for interactive TTYs, ``"json"`` otherwise.
        fields:
            A projection the command already sent to the API (``--api-fields``),
            shown in this order.  The user's client-side list is the
            constructor's ``fields`` (the global ``--fields``).  Either way a
            name no returned record has is a warning with close matches and a
            blank/null column, never a failure: which keys a page carries
            depends on the rows that landed in it.
        default_fields:
            Default columns to show for table/human when *fields* is None.
            Ignored for json/csv/yaml/jsonl.
        title:
            Optional heading shown in *human* and *table* modes.
        unwrap:
            When *True* (default), automatically extract the payload from
            common Netskope API response envelopes before rendering.
        verbose:
            When *True*, print API metadata for table/human formats.
        show_all_columns:
            When *True*, disable auto-column-selection for wide tables.
        empty_hint:
            When the result is empty, show this hint to the user.
        count_only:
            When *True*, print only the record count and return.
        strip_internal:
            When *True* (default), strip ``_``-prefixed internal fields
            from each record (preserving ``_id``).
        add_iso_timestamps:
            When *True* (default), add ``{key}_iso`` companion fields for
            epoch timestamps in JSON/JSONL/CSV/YAML output.
        capped_at:
            The page size the API stopped at when *data* filled it (see
            ``core.datasearch.is_page_capped``).  Counts are then lower
            bounds: the result banner says so, ``--count`` prints ``N+`` in
            table/human output (the bare integer in ``MACHINE_FORMATS``) and
            a notice on stderr gives *capped_hint*.
        capped_hint:
            What the capped-count notice tells the user to do; defaults to
            narrowing the time range.  ``core.datasearch.fetch_page`` adds
            ``--exact`` when the endpoint can be paged.
        """
        if fmt is None:
            fmt = self._auto_detect_format()

        fmt = fmt.lower()
        if fmt not in self.FORMATS:
            raise ValueError(f"Unsupported format {fmt!r}. Choose from {self.FORMATS}")

        # Check env var or --wide flag for wide mode
        if self._wide or os.environ.get("NETSKOPE_WIDE", "") == "1":
            show_all_columns = True
            self.max_col_width = 0

        self._show_all_columns = show_all_columns
        self._fields_applied = False
        self._schema_cache = None

        # Auto-unwrap API response envelopes so that table/csv/etc. operate
        # on the actual records instead of the envelope keys.
        metadata: dict[str, Any] = {}
        if unwrap:
            data, metadata = unwrap_api_response(data)

        # Flatten group-by responses before any client-side processing so
        # --where / --sort / --fields see the aggregation columns.
        is_grouped = False
        if isinstance(data, list):
            old_data = data
            data = self._flatten_grouped_results(data)
            if data is not old_data:
                is_grouped = True

        # Client-side --where filter.  Runs before counting so that --count,
        # the "N results" line and --list-fields all reflect the filtered set.
        removed = 0
        if self._where is not None:
            self._warn_where_paths(data)
            data, removed = apply_filter(data, self._where)

        if unwrap and metadata and verbose and fmt in ("table", "human"):
            # Only print metadata when verbose is True and format is
            # interactive, so it never pollutes machine-consumable output.
            parts: list[str] = []
            for mk, mv in metadata.items():
                parts.append(f"{mk}={mv}")
            self.err_console.print(f"[dim]API metadata: {', '.join(parts)}[/dim]")

        count_only = count_only or self._default_count_only

        # Show record count for table/human/csv formats when there are results.
        if fmt in ("table", "human", "csv") and isinstance(data, list) and len(data) > 0:
            if removed > 0:
                if not self._quiet:
                    self.err_console.print(f"[dim]{len(data)} of {len(data) + removed} results matched --where[/dim]")
            elif capped_at is not None:
                # --count prints its own capped notice below, so no banner then.
                if not count_only and not self._quiet:
                    self.err_console.print(f"[dim]{len(data):,}+ results (capped)[/dim]")
            elif unwrap:
                total_int = envelope_total(metadata) if metadata else None
                if total_int is not None:
                    if total_int != len(data):
                        self.err_console.print(f"[dim]Showing {len(data)} of {total_int} results[/dim]")
                    else:
                        self.err_console.print(f"[dim]{total_int} results[/dim]")
                else:
                    self.err_console.print(f"[dim]{len(data)} results returned[/dim]")

        # Show time range for table/human formats with list data.
        if unwrap and fmt in ("table", "human") and isinstance(data, list) and all(isinstance(r, dict) for r in data):
            self._print_time_range(data)

        # --count mode: print the count and return immediately.
        if count_only:
            rows = len(data) if isinstance(data, list) else (1 if data else 0)
            capped = capped_at is not None
            n = page_count(metadata, rows, capped=capped, where_active=self._where is not None)
            hint = None
            if capped_at is not None:
                hint = (
                    f"Count capped at the API maximum of {capped_at:,} rows; {capped_hint or 'narrow the time range'}."
                )
            print_count(CountResult(n, capped, hint), fmt=fmt, err_console=self.err_console)
            return

        # If the unwrapped data is empty, inform the user (except
        # for JSON, which should faithfully output the raw value).
        is_empty = (isinstance(data, list) and len(data) == 0) or data is None or data == {}
        if is_empty and removed > 0:
            self.err_console.print(
                f"[yellow]--where matched 0 of {removed} records.[/yellow] "
                "[dim]Check field names with --list-fields; string compares are case-insensitive, "
                'use like "*x*" for partial matches.[/dim]'
            )
        if fmt != "json" and is_empty:
            if removed == 0:
                msg = "[dim]No matching records found.[/dim]"
                if empty_hint:
                    msg += f"\n[dim]{empty_hint}[/dim]"
                self.err_console.print(msg)
            if self._list_fields:
                self.err_console.print(
                    "[dim]No records returned, so there are no fields to list. "
                    "Widen the query (--limit, --start) or drop --where.[/dim]"
                )
            return

        # Strip internal _-prefixed fields (except _id) from records.
        if strip_internal and isinstance(data, list):
            data = self._strip_internal_fields(data)

        # --list-fields: describe the schema instead of rendering records.
        if self._list_fields:
            self._render_field_list(data, fmt=fmt, default_fields=default_fields, title=title)
            return

        # Add ISO timestamp companion fields for machine-readable formats.
        if add_iso_timestamps and fmt in ("json", "jsonl", "csv", "yaml"):
            data = self._add_iso_timestamps(data)

        # Client-side --sort (on unprojected rows so hidden fields can be sort keys).
        if self._sort:
            data = self._apply_sort(data)

        # A server-side projection shaped the request, not the aggregation:
        # grouped rows keep their group keys and ``count`` column.
        if is_grouped and fields is not None:
            fields = None
        # The companions synthesised above belong to the fields the projection
        # asked for; keep them so ``--api-fields timestamp`` still yields ``timestamp_iso``.
        if fields is not None and add_iso_timestamps and fmt in ("json", "jsonl", "csv", "yaml"):
            recs = self._records_of(data)
            fields = [
                f
                for name in fields
                for f in ((name, f"{name}_iso") if any(f"{name}_iso" in r for r in recs) else (name,))
            ]

        # Field precedence: explicit per-command fields -> global --fields ->
        # default_fields (table/human/csv only, not grouped, not wide).
        explicit = fields if fields is not None else self._global_fields
        effective_fields = explicit
        if is_grouped:
            effective_fields = None
        elif self._wide:
            effective_fields = None
        elif effective_fields is None and default_fields and fmt in ("table", "human", "csv"):
            effective_fields = list(default_fields)

        # An explicit selection always wins, whatever the format or mode.
        if effective_fields is None and explicit is not None:
            effective_fields = list(explicit)
        explicit_requested = explicit is not None

        # Apply field selection AFTER unwrapping so that --fields applies to
        # individual records, not envelope keys.
        pre_selection_data = data
        data = self._project(
            data,
            effective_fields,
            fmt=fmt,
            warn=explicit_requested,
            label="--api-fields" if fields is not None else "--fields",
            hidden_internal=strip_internal,
        )

        # Fallback: if default_fields removed every column (e.g. grouped
        # results whose keys differ), re-render without selection so the
        # user still sees output.  Never applied to an explicit selection.
        missing_marker = "" if fmt in ("table", "human", "csv") else None
        if (
            not explicit_requested
            and isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and all(all(v == missing_marker for v in row.values()) for row in data if isinstance(row, dict))
        ):
            data = pre_selection_data
        self._fields_applied = explicit_requested and effective_fields is not None

        handler = {
            "json": self._render_json,
            "table": self._render_table,
            "csv": self._render_csv,
            "yaml": self._render_yaml,
            "jsonl": self._render_jsonl,
            "human": self._render_human,
        }[fmt]

        handler(data, title=title)

    # ----- format auto-detection -------------------------------------------

    @staticmethod
    def _auto_detect_format() -> str:
        """Return ``'human'`` when stdout is a TTY, ``'json'`` otherwise."""
        if sys.stdout.isatty():
            return "human"
        return "json"

    # ----- field selection, filtering, sorting ------------------------------

    @staticmethod
    def _records_of(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    def _schema_for(self, records: Sequence[dict[str, Any]]) -> list[FieldInfo]:
        if self._schema_cache is None:
            self._schema_cache = discover_schema(records)
        return self._schema_cache

    def _suggestion_text(self, name: str, records: Sequence[dict[str, Any]]) -> str:
        candidates = [info.path for info in self._schema_for(records)]
        matches = suggest_fields(name, candidates)
        if not matches:
            return ""
        return " Did you mean " + ", ".join(f"[cyan]{rich_escape(m)}[/cyan]" for m in matches) + "?"

    def _project(
        self,
        data: Any,
        fields: Sequence[str] | None,
        *,
        fmt: str,
        warn: bool,
        label: str = "--fields",
        hidden_internal: bool = False,
    ) -> Any:
        """Project *data* onto *fields* (dotted paths, globs).

        A name or glob no record matches is a warning prefixed with *label*
        (with close matches) and renders blank/null.  *hidden_internal* says
        ``_``-prefixed keys were stripped, so such a name points at ``--raw``.
        """
        if fields is None:
            return data
        specs = [f.strip() for f in fields if f and f.strip()]
        if not specs:
            return data
        records = self._records_of(data)
        unmatched_globs: list[str] = []
        if any(is_glob(spec) for spec in specs) and records:
            paths, unmatched_globs = expand_field_specs(specs, self._schema_for(records))
        else:
            paths = list(dict.fromkeys(specs))
        if warn and records:
            problems = [f"pattern '{rich_escape(spec)}' matched no fields." for spec in unmatched_globs]
            for path in find_unmatched(records, paths):
                name = rich_escape(path)
                if path.endswith("_iso") and not find_unmatched(records, [path[:-4]]):
                    # Companions are synthesised for machine-readable formats only.
                    problems.append(
                        f"'{name}' is only added in json, jsonl, csv and yaml output "
                        f"(use '{rich_escape(path[:-4])}' here); column left blank."
                    )
                elif hidden_internal and path.startswith("_") and path.split(".")[0].split("[")[0] != "_id":
                    problems.append(f"'{name}' is internal and hidden unless you pass --raw; column left blank.")
                else:
                    problems.append(f"'{name}' not found in any record.{self._suggestion_text(path, records)}")
            for problem in problems:
                self.err_console.print(
                    f"[yellow]{label}:[/yellow] {problem} [dim]Run with --list-fields to see every field.[/dim]"
                )
        if not paths:
            return data
        missing = "" if fmt in ("table", "human", "csv") else None
        return project_records(data, paths, missing=missing)

    @staticmethod
    def _apply_field_selection(data: Any, fields: Sequence[str] | None) -> Any:
        """Backwards-compatible exact-key projection (see :func:`project_records`)."""
        if fields is None:
            return data
        return project_records(data, list(fields), missing=None)

    def _warn_where_paths(self, data: Any) -> None:
        """Warn when a --where field resolves in no record (the filter would match nothing)."""
        if self._where is None:
            return
        records = self._records_of(data)
        if not records:
            return
        for path in dict.fromkeys(self._where.paths()):
            if find_unmatched(records, [path]):
                self.err_console.print(
                    f"[yellow]--where:[/yellow] '{rich_escape(path)}' is not present in any record."
                    f"{self._suggestion_text(path, records)} [dim]Nothing will match; see --list-fields.[/dim]"
                )

    def _apply_sort(self, data: Any) -> Any:
        if not self._sort or not isinstance(data, list):
            return data
        records = self._records_of(data)
        if not records:
            return data
        specs = list(self._sort)
        unmatched = set(find_unmatched(records, [path for path, _ in specs]))
        for path in unmatched:
            self.err_console.print(
                f"[yellow]--sort:[/yellow] '{rich_escape(path)}' not found in any record."
                f"{self._suggestion_text(path, records)} [dim]Rows left in API order for that key.[/dim]"
            )
        specs = [(path, desc) for path, desc in specs if path not in unmatched]
        if not specs:
            return data
        return sort_records(data, specs)

    def _render_field_list(
        self, data: Any, *, fmt: str, default_fields: Sequence[str] | None, title: str | None
    ) -> None:
        """Render the discovered schema of *data* for ``--list-fields``."""
        records = self._records_of(data)
        if not records:
            self.err_console.print(
                "[dim]No records returned, so there are no fields to list. "
                "Widen the query (--limit, --start) or drop --where.[/dim]"
            )
            if fmt == "json":
                print("[]")
            return
        schema = self._schema_for(records)
        machine = fmt in ("json", "jsonl", "yaml", "csv")
        rows = schema_rows(schema, len(records), default_fields, machine=machine)
        if machine:
            handler = {
                "json": self._render_json,
                "csv": self._render_csv,
                "yaml": self._render_yaml,
                "jsonl": self._render_jsonl,
            }[fmt]
            handler(rows, title=title)
            return
        self._show_all_columns = True
        saved_width = self.max_col_width
        self.max_col_width = 0  # never truncate field paths; samples are pre-truncated
        try:
            self._render_table(rows, title=f"Fields in: {title}" if title else "Fields")
        finally:
            self.max_col_width = saved_width
        if self._quiet:
            return
        leaves = [info.path for info in schema if not info.container]
        pick = ",".join(leaves[:2]) if leaves else "a,b"
        str_info = next((info for info in schema if not info.container and "str" in info.types), None)
        if str_info is not None and str_info.sample is not None and not isinstance(str_info.sample, (list, dict)):
            where_example = f'{str_info.path} eq "{str_info.sample}"'
        else:
            where_example = f'{leaves[0] if leaves else "a"} eq "x"'
        sort_example = f"{leaves[0] if leaves else 'a'}:desc"
        self.err_console.print(
            rich_escape(
                f"{len(schema)} fields across {len(records)} records \u00b7 pick: --fields {pick} "
                f"\u00b7 filter: --where '{where_example}' \u00b7 sort: --sort {sort_example} "
                "\u00b7 nested: dots (a.b), lists: a[].b"
            ),
            style="dim",
            soft_wrap=True,
        )

    # ----- renderers --------------------------------------------------------

    def _render_json(self, data: Any, *, title: str | None = None) -> None:  # noqa: ARG002
        print(json.dumps(data, indent=2, default=str))

    def _render_jsonl(self, data: Any, *, title: str | None = None) -> None:  # noqa: ARG002
        if isinstance(data, list):
            for item in data:
                print(json.dumps(item, default=str))
        else:
            print(json.dumps(data, default=str))

    def _render_yaml(self, data: Any, *, title: str | None = None) -> None:  # noqa: ARG002
        print(yaml.dump(data, default_flow_style=False, sort_keys=False, Dumper=yaml.SafeDumper), end="")

    def _render_csv(self, data: Any, *, title: str | None = None) -> None:  # noqa: ARG002
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list) or not data:
            return

        # Collect all keys across every row to handle ragged dicts.
        all_keys: list[str] = []
        seen: set[str] = set()
        for row in data:
            if isinstance(row, dict):
                for k in row:
                    if k not in seen:
                        all_keys.append(k)
                        seen.add(k)

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            if isinstance(row, dict):
                writer.writerow({k: self._csv_cell(v) for k, v in row.items()})
        sys.stdout.write(buf.getvalue())

    @staticmethod
    def _csv_cell(value: Any) -> str:
        """Format a cell value for CSV output, truncating large nested objects."""
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, default=str)
            if len(rendered) > 200:
                if isinstance(value, list):
                    return f"[{len(value)} items]"
                return f"{{{len(value)} keys}}"
            return rendered
        return str(value)

    def _render_table(self, data: Any, *, title: str | None = None) -> None:
        data = self._humanize_timestamps(data)

        if isinstance(data, dict) and not any(isinstance(v, (dict, list)) for v in data.values()):
            self._render_kv_table(data, title=title)
            return

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list) or not data:
            return

        # If items are not dicts (e.g. list of strings), render single-column table.
        if data and not isinstance(data[0], dict):
            table = Table(title=title, show_header=True, header_style="bold cyan", expand=False)
            table.add_column("value")
            for item in data:
                table.add_row(self._format_cell(item))
            self.console.print(table)
            return

        all_keys: list[str] = []
        seen: set[str] = set()
        for row in data:
            if isinstance(row, dict):
                for k in row:
                    if k not in seen:
                        all_keys.append(k)
                        seen.add(k)

        # Wide-table auto-selection: when there are too many columns,
        # pick the most informative ones and notify the user.  Never trims a
        # column set the user chose explicitly with --fields.
        display_keys = all_keys
        wide_note: str | None = None
        show_all = getattr(self, "_show_all_columns", False) or getattr(self, "_fields_applied", False)
        if not show_all and len(all_keys) > _WIDE_TABLE_MAX_COLUMNS:
            display_keys = self._select_priority_columns(all_keys)
            # Suggest a handful of useful-looking fields drawn from ALL columns,
            # including the hidden ones, excluding internal '_' columns.
            _suggest_patterns = (
                "name",
                "id",
                "user",
                "timestamp",
                "status",
                "app",
                "type",
                "severity",
                "email",
                "action",
                "alert_name",
                "host",
            )
            suggestions = [
                k for k in all_keys if not k.startswith("_") and any(p in k.lower() for p in _suggest_patterns)
            ][:4]
            pick = ",".join(suggestions) if suggestions else "a,b,c"
            wide_note = (
                f"showing {len(display_keys)} of {len(all_keys)} columns \u00b7 see all: --list-fields "
                f"\u00b7 pick: --fields {pick} \u00b7 everything: -W"
            )

        table = Table(title=title, show_header=True, header_style="bold cyan", expand=False)
        for key in display_keys:
            table.add_column(key)

        for row in data:
            if not isinstance(row, dict):
                continue
            values = [self._format_cell(row.get(k, "")) for k in display_keys]
            table.add_row(*values)

        self.console.print(table)
        if wide_note:
            self.err_console.print(rich_escape(wide_note), style="dim", soft_wrap=True)

    def _render_kv_table(self, data: dict, *, title: str | None = None) -> None:
        table = Table(title=title, show_header=True, header_style="bold cyan", expand=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(str(k), self._format_cell(v))
        self.console.print(table)

    def _render_human(self, data: Any, *, title: str | None = None) -> None:
        data = self._humanize_timestamps(data)

        # Lists of dicts -> Rich table
        if isinstance(data, list) and data and isinstance(data[0], dict):
            self._render_table(data, title=title)
            return

        # Single flat dict -> key-value panel
        if isinstance(data, dict) and not any(isinstance(v, (dict, list)) for v in data.values()):
            lines = [f"[bold]{rich_escape(str(k))}[/bold]: {rich_escape(str(v))}" for k, v in data.items()]
            panel = Panel("\n".join(lines), title=title or "Result", border_style="blue")
            self.console.print(panel)
            return

        # Anything else: syntax-highlighted JSON inside a panel
        rendered = json.dumps(data, indent=2, default=str)
        syntax = Syntax(rendered, "json", theme="monokai", word_wrap=True)
        panel = Panel(syntax, title=title or "Result", border_style="blue")
        self.console.print(panel)

    # ----- helpers ----------------------------------------------------------

    @staticmethod
    def _flatten_grouped_results(data: list) -> list:
        return flatten_grouped_results(data)

    @staticmethod
    def _select_priority_columns(all_keys: list[str]) -> list[str]:
        """Pick up to ``_WIDE_TABLE_MAX_COLUMNS`` columns, preferring 'important' ones."""
        exact_match: list[str] = []
        substring_match: list[str] = []
        rest: list[str] = []

        exact_lower = {n.lower() for n in _PRIORITY_EXACT_NAMES}

        for key in all_keys:
            key_lower = key.lower()
            if key_lower in exact_lower or key in _PRIORITY_EXACT_NAMES:
                exact_match.append(key)
            elif any(sub in key_lower for sub in _PRIORITY_SUBSTRINGS):
                substring_match.append(key)
            else:
                rest.append(key)

        selected = exact_match[:_WIDE_TABLE_MAX_COLUMNS]
        remaining = _WIDE_TABLE_MAX_COLUMNS - len(selected)
        if remaining > 0:
            selected.extend(substring_match[:remaining])
            remaining = _WIDE_TABLE_MAX_COLUMNS - len(selected)
        if remaining > 0:
            selected.extend(rest[:remaining])

        # Preserve original column order.
        selected_set = set(selected)
        return [k for k in all_keys if k in selected_set]

    @staticmethod
    def _summarize_value(value: Any) -> str:
        """Return a short human-friendly summary for complex cell values."""
        if isinstance(value, dict):
            # For dicts with only simple scalar values and <= 5 keys, inline them
            if len(value) <= 5 and all(isinstance(v, (str, int, float, bool, type(None))) for v in value.values()):
                return ", ".join(f"{k}={v}" for k, v in value.items())
            # For a single-key dict where value is a scalar, show just the value
            if len(value) == 1:
                only_val = next(iter(value.values()))
                if isinstance(only_val, (str, int, float, bool, type(None))):
                    return str(only_val)
            return f"{{{len(value)} keys}}"
        if isinstance(value, list):
            if not value:
                return "[]"
            # If all items are simple scalars (str/int/float/bool), show first few
            if all(isinstance(v, (str, int, float, bool)) for v in value):
                preview = ", ".join(str(v) for v in value[:3])
                if len(value) > 3:
                    return f"{preview}, ... ({len(value)} items)"
                return preview
            # If all items are dicts with a common identifying key, inline those values.
            if all(isinstance(v, dict) for v in value):
                for label_key in ("name", "display_name", "label", "title", "id"):
                    if all(label_key in v and isinstance(v[label_key], (str, int, float, bool)) for v in value):
                        preview = ", ".join(str(v[label_key]) for v in value[:3])
                        if len(value) > 3:
                            return f"{preview}, ... ({len(value)} items)"
                        return preview
            return f"[{len(value)} items]"
        return str(value)

    def _format_cell(self, value: Any) -> str:
        """Format a cell value for table display with truncation.

        The result is escaped for Rich markup: API data such as NPA app names
        (``"[myapp]"``) would otherwise be parsed as a style tag and rendered
        as an empty cell (issue #16).
        """
        if isinstance(value, (dict, list)):
            text = self._summarize_value(value)
        else:
            text = str(value)
        return rich_escape(self._truncate(text))

    def _truncate(self, value: str) -> str:
        if self.max_col_width and len(value) > self.max_col_width:
            return value[: self.max_col_width - 1] + "\u2026"
        return value

    # ----- internal field stripping -----------------------------------------

    # Keys starting with '_' that are user-facing and should NOT be stripped.
    _KEEP_INTERNAL = frozenset({"_id"})

    @classmethod
    def _strip_internal_fields(cls, data: Any) -> Any:
        """Remove ``_``-prefixed internal fields from records.

        Preserves keys listed in ``_KEEP_INTERNAL`` (e.g. ``_id``).
        """
        if isinstance(data, list):
            return [cls._strip_internal_fields(item) for item in data]
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not k.startswith("_") or k in cls._KEEP_INTERNAL}
        return data

    # ----- ISO timestamp injection ------------------------------------------

    @classmethod
    def _add_iso_timestamps(cls, data: Any) -> Any:
        """Add ``{key}_iso`` companion fields for epoch timestamps."""
        if isinstance(data, list):
            return [cls._add_iso_timestamps(item) for item in data]
        if isinstance(data, dict):
            extra: dict[str, str] = {}
            for k, v in data.items():
                if cls._looks_like_timestamp(k, v):
                    iso = datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    extra[f"{k}_iso"] = iso
            if extra:
                merged = dict(data)
                merged.update(extra)
                return merged
            return data
        return data

    # ----- time range display ------------------------------------------------

    def _print_time_range(self, data: list[dict[str, Any]]) -> None:
        """Print the time range spanned by records to stderr.

        Scans all records for fields that look like Unix epoch timestamps,
        finds the global min and max, and prints a summary line.  Only prints
        when there are 2+ records with at least one timestamp field.
        """
        if len(data) < 2:
            return

        min_ts: float | None = None
        max_ts: float | None = None

        for row in data:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if self._looks_like_timestamp(k, v):
                    if min_ts is None or v < min_ts:
                        min_ts = v
                    if max_ts is None or v > max_ts:
                        max_ts = v

        if min_ts is None or max_ts is None:
            return

        fmt_min = datetime.fromtimestamp(min_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        fmt_max = datetime.fromtimestamp(max_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.err_console.print(f"[dim]Time range: {fmt_min} \u2192 {fmt_max}[/dim]")

    # ----- timestamp humanisation -------------------------------------------

    _TIMESTAMP_NAME_HINTS = ("timestamp", "time", "_at", "created", "modified")

    @classmethod
    def _looks_like_timestamp(cls, key: str, value: Any) -> bool:
        """Return True if *value* appears to be a Unix epoch timestamp."""
        if isinstance(value, (int, float)):
            if 1_000_000_000 < value < 2_000_000_000:
                return True
            key_lower = key.lower()
            if any(hint in key_lower for hint in cls._TIMESTAMP_NAME_HINTS):
                if 1_000_000_000 < value < 2_000_000_000:
                    return True
        return False

    @classmethod
    def _format_timestamp(cls, value: int | float) -> str:
        """Convert a Unix epoch value to a human-readable UTC string."""
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    @classmethod
    def _humanize_timestamps(cls, data: Any) -> Any:
        """Recursively convert timestamp-looking values to human-readable strings."""
        if isinstance(data, dict):
            return {
                k: (cls._format_timestamp(v) if cls._looks_like_timestamp(k, v) else cls._humanize_timestamps(v))
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [cls._humanize_timestamps(item) for item in data]
        return data


# ---------------------------------------------------------------------------
# Factory helper — builds a formatter from a Typer context
# ---------------------------------------------------------------------------


def build_formatter(ctx: Any) -> "OutputFormatter":
    """Create an ``OutputFormatter`` pre-configured from the global CLI state.

    Reads ``no_color``, ``count``, ``wide``, ``quiet`` and the query options
    (``fields``, ``where_expr``, ``sort_spec``, ``list_fields``) from
    ``ctx.obj`` (the ``State`` dataclass set by the main callback).  Safe to
    call even when ``ctx.obj`` is *None*.  Every command module's
    ``_get_formatter`` / ``_build_formatter`` helper delegates here so the
    global options are honoured uniformly.
    """
    state = getattr(ctx, "obj", None)

    def opt(name: str, default: Any) -> Any:
        return getattr(state, name, default) if state is not None else default

    return OutputFormatter(
        no_color=opt("no_color", False),
        count_only=opt("count", False),
        wide=opt("wide", False),
        quiet=opt("quiet", False),
        fields=opt("fields", None),
        where=opt("where_expr", None) or opt("where", None),
        sort=opt("sort_spec", None) or opt("sort", None),
        list_fields=opt("list_fields", False),
    )


# ---------------------------------------------------------------------------
# Convenience echo helpers
# ---------------------------------------------------------------------------


def echo_success(msg: str, *, no_color: bool = False) -> None:
    """Print a success message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold green]SUCCESS[/bold green] {rich_escape(msg)}")


def echo_error(msg: str, *, no_color: bool = False) -> None:
    """Print an error message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold red]ERROR[/bold red] {rich_escape(msg)}")


def echo_warning(msg: str, *, no_color: bool = False) -> None:
    """Print a warning message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold yellow]WARNING[/bold yellow] {rich_escape(msg)}")


def echo_info(msg: str, *, no_color: bool = False) -> None:
    """Print an informational message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold blue]INFO[/bold blue] {rich_escape(msg)}")


# ---------------------------------------------------------------------------
# Progress spinner context manager
# ---------------------------------------------------------------------------


@contextmanager
def spinner(
    message: str = "Loading...", *, no_color: bool = False, quiet: bool = False
) -> Generator[Progress | None, None, None]:
    """Context manager that shows a Rich spinner on stderr.

    Automatically suppressed when stderr is not a TTY (piped output)
    or when *quiet* is True.

    Usage::

        with spinner("Fetching data..."):
            do_slow_work()
    """
    # Suppress spinner when stderr isn't a TTY or quiet mode is active
    if quiet or not sys.stderr.isatty():
        yield None
        return

    console = _make_console(no_color=no_color, stderr=True)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )
    with progress:
        progress.add_task(description=message, total=None)
        yield progress
