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
from datetime import datetime, timezone
from typing import Any, Generator, Sequence

import yaml
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

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
        self, *, no_color: bool = False, max_col_width: int = 80, count_only: bool = False, wide: bool = False
    ) -> None:
        self.no_color = no_color
        self.max_col_width = 0 if wide else max_col_width
        self._default_count_only = count_only
        self._wide = wide
        self.console = _make_console(no_color=no_color)
        self.err_console = _make_console(no_color=no_color, stderr=True)

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
            Optional subset of keys/columns to include in the output.
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

        # Auto-unwrap API response envelopes so that table/csv/etc. operate
        # on the actual records instead of the envelope keys.
        metadata: dict[str, Any] = {}
        if unwrap:
            data, metadata = unwrap_api_response(data)
            # Only print metadata when verbose is True and format is
            # interactive, so it never pollutes machine-consumable output.
            if metadata and verbose and fmt in ("table", "human"):
                parts: list[str] = []
                for mk, mv in metadata.items():
                    parts.append(f"{mk}={mv}")
                self.err_console.print(f"[dim]API metadata: {', '.join(parts)}[/dim]")

            # Show record count for table/human/csv formats when there are results.
            if fmt in ("table", "human", "csv") and isinstance(data, list) and len(data) > 0:
                total = None
                if metadata:
                    total = (
                        metadata.get("total")
                        or metadata.get("totalResults")
                        or metadata.get("status.count")
                        or metadata.get("status.total")
                    )
                if total is not None:
                    try:
                        total_int = int(total)
                        if total_int != len(data):
                            self.err_console.print(f"[dim]Showing {len(data)} of {total_int} results[/dim]")
                        else:
                            self.err_console.print(f"[dim]{total_int} results[/dim]")
                    except (ValueError, TypeError):
                        self.err_console.print(f"[dim]{len(data)} results returned[/dim]")
                else:
                    self.err_console.print(f"[dim]{len(data)} results returned[/dim]")

            # Show time range for table/human formats with list data.
            if fmt in ("table", "human") and isinstance(data, list) and all(isinstance(r, dict) for r in data):
                self._print_time_range(data)

        # --count mode: print the count and return immediately.
        count_only = count_only or self._default_count_only
        if count_only:
            total = (
                metadata.get("total")
                or metadata.get("totalResults")
                or metadata.get("status.count")
                or metadata.get("status.total")
            )
            if total is not None:
                print(int(total))
            elif isinstance(data, list):
                print(len(data))
            else:
                print(1 if data else 0)
            return

        # If the unwrapped data is empty, inform the user (except
        # for JSON, which should faithfully output the raw value).
        if fmt != "json":
            if isinstance(data, list) and len(data) == 0:
                msg = "[dim]No matching records found.[/dim]"
                if empty_hint:
                    msg += f"\n[dim]{empty_hint}[/dim]"
                self.err_console.print(msg)
                return
            if data is None or data == {}:
                msg = "[dim]No matching records found.[/dim]"
                if empty_hint:
                    msg += f"\n[dim]{empty_hint}[/dim]"
                self.err_console.print(msg)
                return

        # Strip internal _-prefixed fields (except _id) from records.
        if strip_internal and isinstance(data, list):
            data = self._strip_internal_fields(data)

        # Add ISO timestamp companion fields for machine-readable formats.
        if add_iso_timestamps and fmt in ("json", "jsonl", "csv", "yaml"):
            data = self._add_iso_timestamps(data)

        # Flatten group-by responses before rendering.
        is_grouped = False
        if isinstance(data, list):
            old_data = data
            data = self._flatten_grouped_results(data)
            if data is not old_data:
                is_grouped = True

        # Apply default_fields for table/human when no explicit fields given.
        # When grouped results are detected, clear default_fields so all
        # aggregation columns (e.g. alert_type, count) are shown.
        # When wide mode is active, skip default_fields so all columns are visible.
        effective_fields = fields
        if is_grouped:
            effective_fields = None
        elif self._wide:
            effective_fields = None
        elif effective_fields is None and default_fields and fmt in ("table", "human", "csv"):
            effective_fields = list(default_fields)

        # For CSV/YAML/JSONL, apply explicit --fields even when default_fields
        # would normally be ignored, so that user-specified --fields always work.
        if effective_fields is None and fields is not None:
            effective_fields = list(fields)

        # Apply field selection AFTER unwrapping so that --fields applies to
        # individual records, not envelope keys.
        pre_selection_data = data
        data = self._apply_field_selection(data, effective_fields)

        # Fallback: if field selection removed all columns (e.g. grouped
        # results where default_fields don't match the aggregation keys),
        # re-render without field selection so the user still sees output.
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and all(len(row) == 0 for row in data if isinstance(row, dict))
        ):
            data = pre_selection_data

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

    # ----- field selection --------------------------------------------------

    @staticmethod
    def _apply_field_selection(data: Any, fields: Sequence[str] | None) -> Any:
        if fields is None:
            return data
        fields_set = list(fields)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in fields_set}
        if isinstance(data, list):
            return [{k: v for k, v in row.items() if k in fields_set} for row in data if isinstance(row, dict)]
        return data

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
        # pick the most informative ones and notify the user.
        display_keys = all_keys
        wide_note: str | None = None
        show_all = getattr(self, "_show_all_columns", False)
        if not show_all and len(all_keys) > _WIDE_TABLE_MAX_COLUMNS:
            display_keys = self._select_priority_columns(all_keys)
            # Suggest a handful of present fields that match common useful patterns,
            # excluding internal columns that start with '_'.
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
            )
            suggestions = [
                k for k in display_keys if not k.startswith("_") and any(p in k.lower() for p in _suggest_patterns)
            ][:6]
            if suggestions:
                hint = f" \u2014 try: --fields {','.join(suggestions)}"
            else:
                hint = ", use --fields to select specific columns"
            wide_note = f"(showing {len(display_keys)} of {len(all_keys)} columns{hint})"

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
            self.err_console.print(f"[dim]{wide_note}[/dim]")

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
        """Flatten group-by API responses.

        Detects responses shaped like ``[{"_id": {"field": "val"}, "count": N}, ...]``
        or ``[{"_id": {"field": "val"}}, ...]`` (no count from API) and flattens them
        to ``[{"field": "val", "count": N}, ...]``.
        """
        if not data or not isinstance(data, list):
            return data
        # Check if this looks like a group-by response (with or without count)
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
            return f"[{len(value)} items]"
        return str(value)

    def _format_cell(self, value: Any) -> str:
        """Format a cell value for table display with truncation."""
        if isinstance(value, (dict, list)):
            text = self._summarize_value(value)
        else:
            text = str(value)
        return self._truncate(text)

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

    Reads ``no_color``, ``count``, and ``wide`` from ``ctx.obj`` (the ``State``
    dataclass set by the main callback).  Safe to call even when ``ctx.obj`` is *None*.
    """
    state = getattr(ctx, "obj", None)
    no_color = getattr(state, "no_color", False) if state is not None else False
    count_only = getattr(state, "count", False) if state is not None else False
    wide = getattr(state, "wide", False) if state is not None else False
    return OutputFormatter(no_color=no_color, count_only=count_only, wide=wide)


# ---------------------------------------------------------------------------
# Convenience echo helpers
# ---------------------------------------------------------------------------


def echo_success(msg: str, *, no_color: bool = False) -> None:
    """Print a success message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold green]SUCCESS[/bold green] {msg}")


def echo_error(msg: str, *, no_color: bool = False) -> None:
    """Print an error message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold red]ERROR[/bold red] {msg}")


def echo_warning(msg: str, *, no_color: bool = False) -> None:
    """Print a warning message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold yellow]WARNING[/bold yellow] {msg}")


def echo_info(msg: str, *, no_color: bool = False) -> None:
    """Print an informational message to stderr."""
    console = _make_console(no_color=no_color, stderr=True)
    console.print(f"[bold blue]INFO[/bold blue] {msg}")


# ---------------------------------------------------------------------------
# Progress spinner context manager
# ---------------------------------------------------------------------------


@contextmanager
def spinner(
    message: str = "Loading...", *, no_color: bool = False, quiet: bool = False
) -> Generator[Progress, None, None]:
    """Context manager that shows a Rich spinner on stderr.

    Automatically suppressed when stderr is not a TTY (piped output)
    or when *quiet* is True.

    Usage::

        with spinner("Fetching data..."):
            do_slow_work()
    """
    # Suppress spinner when stderr isn't a TTY or quiet mode is active
    if quiet or not sys.stderr.isatty():
        yield None  # type: ignore[arg-type]
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
