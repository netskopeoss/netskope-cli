"""Dotted field-path resolution, schema discovery and projection.

This module powers the global ``--fields``, ``--list-fields``, ``--where`` and
``--sort`` options.  It has no third-party dependencies and operates on plain
JSON-like data (dicts, lists and scalars).

Path grammar
------------
``a.b.c``       nested dict keys
``a[].b``       map over every element of the list ``a`` and take ``b``
``a.b``         when ``a`` is a list, implicitly the same as ``a[].b``
``a[0].b``      index into the list ``a``
``status.count`` a *literal* key containing a dot is tried before splitting,
                so Netskope's dotted metadata keys keep working.

Glob patterns (``*`` and ``?``) are expanded against the discovered schema by
:func:`expand_field_specs`.  Square brackets are always literal (NPA app names
are literally ``[myapp]``), so ``fnmatch`` is deliberately not used.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Final, Sequence


class _Missing:
    """Sentinel for "path did not resolve" (distinct from ``None``)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"

    def __bool__(self) -> bool:
        return False


MISSING: Final[_Missing] = _Missing()

_SEGMENT_RE = re.compile(r"^(?P<key>[^\[\]]*)(?:\[(?P<idx>-?\d*)\])?$")
_SCALAR_TYPES = (str, int, float, bool, type(None))


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def split_path(path: str) -> list[str]:
    """Split ``"a.b[].c"`` into ``["a", "b[]", "c"]``.

    A leading ``[]``/``[N]`` after a dot (``"a.[].b"``) is attached to the
    preceding segment so both spellings resolve identically.
    """
    parts = [p for p in path.strip().split(".") if p != ""]
    merged: list[str] = []
    for part in parts:
        if part.startswith("[") and merged:
            merged[-1] += part
        else:
            merged.append(part)
    return merged


def _parse_segment(segment: str) -> tuple[str, str | None]:
    """Return ``(key, index_spec)`` where index_spec is ``None``, ``""`` or a digit string."""
    m = _SEGMENT_RE.match(segment)
    if m is None:
        return segment, None
    return m.group("key"), m.group("idx")


class _Walk:
    """Mutable state for a single resolution walk."""

    __slots__ = ("crossed_list",)

    def __init__(self) -> None:
        self.crossed_list = False


def _resolve(obj: Any, segments: list[str], walk: _Walk) -> list[Any]:
    if not segments:
        return [obj]

    # Literal-key precedence: the longest dotted prefix that is a real key wins.
    if isinstance(obj, dict):
        for n in range(len(segments), 0, -1):
            literal = ".".join(segments[:n])
            if literal in obj:
                return _resolve(obj[literal], segments[n:], walk)

    key, idx = _parse_segment(segments[0])
    rest = segments[1:]

    if key:
        if isinstance(obj, dict):
            if key not in obj:
                return []
            value = obj[key]
        elif isinstance(obj, list):
            # Implicit map over list elements: ``protocols.port``.
            walk.crossed_list = True
            out: list[Any] = []
            for element in obj:
                out.extend(_resolve(element, segments, walk))
            return out
        else:
            return []
    else:
        value = obj

    if idx is None:
        return _resolve(value, rest, walk)
    if not isinstance(value, list):
        return []
    if idx == "":
        walk.crossed_list = True
        out = []
        for element in value:
            out.extend(_resolve(element, rest, walk))
        return out
    position = int(idx)
    if -len(value) <= position < len(value):
        return _resolve(value[position], rest, walk)
    return []


def resolve_path(obj: Any, path: str) -> list[Any]:
    """Return **every** value that *path* matches in *obj* (``[]`` when none)."""
    return _resolve(obj, split_path(path), _Walk())


def get_path(obj: Any, path: str) -> Any:
    """Return the value at *path*.

    A scalar when the path does not cross a list, a list of values when it
    does, and :data:`MISSING` when nothing matched.
    """
    walk = _Walk()
    values = _resolve(obj, split_path(path), walk)
    if not values:
        return MISSING
    if walk.crossed_list:
        return values
    return values[0]


# ---------------------------------------------------------------------------
# Schema discovery
# ---------------------------------------------------------------------------


@dataclass
class FieldInfo:
    """Facts about one field path observed across a set of records."""

    path: str
    types: list[str] = field(default_factory=list)
    present: int = 0
    sample: Any = MISSING
    container: bool = False

    @property
    def type_label(self) -> str:
        return "|".join(self.types) if self.types else "null"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        if not value:
            return "list"
        inner = {_type_name(v) for v in value}
        if len(inner) == 1:
            return f"list[{inner.pop()}]"
        return "list"
    return type(value).__name__


def _is_list_of_dicts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def discover_schema(records: Sequence[Any], *, max_depth: int = 8) -> list[FieldInfo]:
    """Return the union of field paths across *records*, in first-seen order.

    Dicts recurse with ``.``; lists of dicts recurse with ``[].``; lists of
    scalars are leaves typed ``list[str]`` etc.  ``present`` counts records
    (not elements) in which the path resolved at least once.
    """
    infos: dict[str, FieldInfo] = {}

    def visit(value: Any, prefix: str, depth: int, seen: set[str]) -> None:
        if depth > max_depth or not isinstance(value, dict):
            return
        for key, val in value.items():
            path = f"{prefix}{key}"
            info = infos.get(path)
            if info is None:
                info = FieldInfo(path=path)
                infos[path] = info
            tname = _type_name(val)
            if tname not in info.types:
                info.types.append(tname)
            if path not in seen:
                seen.add(path)
                info.present += 1
            if info.sample is MISSING and val is not None and not isinstance(val, (dict, list)):
                info.sample = val
            elif info.sample is MISSING and isinstance(val, list) and val and not _is_list_of_dicts(val):
                info.sample = val
            if isinstance(val, dict):
                info.container = True
                visit(val, f"{path}.", depth + 1, seen)
            elif _is_list_of_dicts(val):
                info.container = True
                for element in val:
                    visit(element, f"{path}[].", depth + 1, seen)

    for record in records:
        if isinstance(record, dict):
            visit(record, "", 0, set())
    return list(infos.values())


# ---------------------------------------------------------------------------
# Glob expansion, projection, suggestions
# ---------------------------------------------------------------------------


def is_glob(spec: str) -> bool:
    return "*" in spec or "?" in spec


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a ``*``/``?`` glob into a compiled, case-insensitive regex.

    Every other character (including ``[`` and ``]``) is matched literally.
    """
    out: list[str] = []
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out), re.IGNORECASE)


def expand_field_specs(specs: Sequence[str], schema: Sequence[FieldInfo]) -> tuple[list[str], list[str]]:
    """Expand glob specs against *schema*.

    Returns ``(ordered_paths, unmatched_glob_specs)``.  Non-glob specs are
    passed through untouched (their existence is checked per record by
    :func:`find_unmatched`).  Container paths (objects, lists of objects)
    are skipped during expansion so a glob yields leaf columns only.
    """
    leaf_paths = [info.path for info in schema if not info.container]
    ordered: list[str] = []
    unmatched: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        if is_glob(spec):
            regex = glob_to_regex(spec)
            matches = [p for p in leaf_paths if regex.fullmatch(p)]
            if not matches:
                unmatched.append(spec)
            for p in matches:
                if p not in seen:
                    seen.add(p)
                    ordered.append(p)
        elif spec not in seen:
            seen.add(spec)
            ordered.append(spec)
    return ordered, unmatched


def find_unmatched(records: Sequence[Any], paths: Sequence[str]) -> list[str]:
    """Return the *paths* that resolve in none of *records*."""
    unmatched: list[str] = []
    for path in paths:
        if not any(resolve_path(r, path) for r in records if isinstance(r, dict)):
            unmatched.append(path)
    return unmatched


def project_records(data: Any, fields: Sequence[str], *, missing: Any = None) -> Any:
    """Project *data* (dict or list of dicts) onto *fields*, in request order.

    Output keys are the requested path strings.  Unresolved paths take the
    *missing* value.  Non-dict rows in a list are dropped, matching the
    historical behaviour of field selection.
    """

    def one(row: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for path in fields:
            value = get_path(row, path)
            out[path] = missing if value is MISSING else value
        return out

    if isinstance(data, dict):
        return one(data)
    if isinstance(data, list):
        return [one(row) for row in data if isinstance(row, dict)]
    return data


def suggest_fields(name: str, candidates: Sequence[str], n: int = 3) -> list[str]:
    """Suggest close matches for an unknown field name.

    Paths whose last segment equals *name* (``hostname`` -> ``host_info.hostname``)
    rank first, then difflib close matches.
    """
    lowered = name.lower()
    tail = lowered.rsplit(".", 1)[-1]
    exact_tail = [c for c in candidates if c.lower().rsplit(".", 1)[-1].rstrip("[]") == tail and c.lower() != lowered]
    fuzzy = difflib.get_close_matches(name, list(candidates), n=n, cutoff=0.6)
    out: list[str] = []
    for c in exact_tail + fuzzy:
        if c not in out:
            out.append(c)
    return out[:n]


def truncate_sample(value: Any, width: int = 40) -> str:
    """Render a sample value as a short single-line string."""
    if value is MISSING:
        return ""
    text = str(value) if not isinstance(value, (dict, list)) else repr(value)
    text = text.replace("\n", " ")
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def schema_rows(
    schema: Sequence[FieldInfo],
    total: int,
    default_fields: Sequence[str] | None = None,
    *,
    machine: bool = False,
) -> list[dict[str, Any]]:
    """Turn a schema into rows for rendering.

    *machine* selects the JSON/CSV shape (``present_pct`` int, ``in_default``
    bool, untruncated sample); otherwise the human table shape.
    """
    defaults = set(default_fields or ())
    rows: list[dict[str, Any]] = []
    for info in schema:
        pct = int(round(100 * info.present / total)) if total else 0
        if machine:
            sample: Any = None if info.sample is MISSING else info.sample
            if not isinstance(sample, _SCALAR_TYPES + (list,)):
                sample = truncate_sample(sample)
            rows.append(
                {
                    "field": info.path,
                    "type": info.type_label,
                    "present_pct": pct,
                    "sample": sample,
                    "in_default": info.path in defaults,
                }
            )
        else:
            rows.append(
                {
                    "field": info.path,
                    "type": info.type_label,
                    "present": f"{pct}%",
                    "sample": truncate_sample(info.sample),
                    "default": "*" if info.path in defaults else "",
                }
            )
    return rows
