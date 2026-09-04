"""Client-side JQL filtering and sorting for the global ``--where`` / ``--sort`` options.

The expression language is the JQL subset already documented by
``ntsk docs jql`` (``eq ne gt ge lt le in like between and or not`` with
parentheses), evaluated locally against the records a command returned.

Grammar::

    expr       = or_expr ;
    or_expr    = and_expr , { OR , and_expr } ;
    and_expr   = not_expr , { AND , not_expr } ;
    not_expr   = NOT , not_expr | primary ;
    primary    = "(" , expr , ")" | comparison ;
    comparison = path , ( cmp_op , value
                        | IN , list | NOT IN , list
                        | BETWEEN , "[" value "," value "]"
                        | LIKE , value ) ;
    cmp_op     = eq | ne | gt | ge | lt | le | == | != | > | >= | < | <= | = ;
    value      = STRING | NUMBER | true | false | null | WORD ;
    list       = "[" , [ value , { "," , value } ] , "]" ;

Keywords are case-insensitive.  Paths use the :mod:`fieldpaths` grammar.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

from netskope_cli.core.exceptions import ValidationError
from netskope_cli.core.fieldpaths import MISSING, get_path, glob_to_regex, resolve_path

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_DOCS_HINT = "Run 'ntsk docs fields' for the --where syntax, or 'ntsk docs jql' for the operator reference."


class FilterSyntaxError(ValidationError):
    """A ``--where`` or ``--sort`` expression could not be parsed (exit code 2)."""

    def __init__(self, message: str, *, text: str, pos: int) -> None:
        self.pos = pos
        self.text = text
        caret = " " * max(pos, 0) + "^"
        full = f"Invalid --where expression: {message}\n\n    {text}\n    {caret}"
        super().__init__(full, suggestion=_DOCS_HINT)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

TokenKind = Literal["word", "string", "number", "op", "lparen", "rparen", "lbracket", "rbracket", "comma", "eof"]


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str
    pos: int


_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_WORD_CHAR = re.compile(r"[A-Za-z0-9_.\-@:/*?+]")
_INDEX_RE = re.compile(r"\[-?\d*\]")
_SYMBOL_OPS = ("==", "!=", ">=", "<=", ">", "<", "=")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}


def _scan_word(text: str, i: int) -> int:
    """Advance past a word/path starting at *i*; ``[]``/``[N]`` glued to it are part of the path."""
    n = len(text)
    while i < n:
        if _WORD_CHAR.match(text[i]):
            i += 1
            continue
        if text[i] == "[":
            m = _INDEX_RE.match(text, i)
            if m:
                i = m.end()
                continue
        break
    return i


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        simple = {"(": "lparen", ")": "rparen", ",": "comma", "[": "lbracket", "]": "rbracket"}
        if ch in simple:
            tokens.append(Token(simple[ch], ch, i))  # type: ignore[arg-type]
            i += 1
            continue
        if ch in "\"'":
            start = i
            quote = ch
            i += 1
            buf: list[str] = []
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    buf.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                    continue
                buf.append(text[i])
                i += 1
            if i >= n:
                raise FilterSyntaxError("unterminated string literal", text=text, pos=start)
            i += 1  # closing quote
            tokens.append(Token("string", "".join(buf), start))
            continue
        symbol = next((s for s in _SYMBOL_OPS if text.startswith(s, i)), None)
        if symbol is not None:
            tokens.append(Token("op", symbol, i))
            i += len(symbol)
            continue
        if _WORD_CHAR.match(ch):
            start = i
            i = _scan_word(text, i)
            word = text[start:i]
            kind: TokenKind = "number" if _NUMBER_RE.match(word) else "word"
            tokens.append(Token(kind, word, start))
            continue
        raise FilterSyntaxError(f"unexpected character {ch!r}", text=text, pos=i)
    tokens.append(Token("eof", "", n))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


class Expr(Protocol):
    def evaluate(self, record: Any) -> bool: ...

    def paths(self) -> list[str]: ...


@dataclass(frozen=True)
class Comparison:
    path: str
    op: str
    value: Any  # scalar, or list for in / not in / between

    def evaluate(self, record: Any) -> bool:
        candidates = _candidates(record, self.path)
        if self.op in ("ne", "not in"):
            positive = "eq" if self.op == "ne" else "in"
            return not any(compare(positive, c, self.value) for c in candidates)
        return any(compare(self.op, c, self.value) for c in candidates)

    def paths(self) -> list[str]:
        return [self.path]


@dataclass(frozen=True)
class And:
    left: Expr
    right: Expr

    def evaluate(self, record: Any) -> bool:
        return self.left.evaluate(record) and self.right.evaluate(record)

    def paths(self) -> list[str]:
        return self.left.paths() + self.right.paths()


@dataclass(frozen=True)
class Or:
    left: Expr
    right: Expr

    def evaluate(self, record: Any) -> bool:
        return self.left.evaluate(record) or self.right.evaluate(record)

    def paths(self) -> list[str]:
        return self.left.paths() + self.right.paths()


@dataclass(frozen=True)
class Not:
    inner: Expr

    def evaluate(self, record: Any) -> bool:
        return not self.inner.evaluate(record)

    def paths(self) -> list[str]:
        return self.inner.paths()


def _candidates(record: Any, path: str) -> list[Any]:
    """Resolve *path* and flatten list values so comparisons use ANY semantics."""
    values = resolve_path(record, path)
    flat: list[Any] = []
    for v in values:
        if isinstance(v, list):
            flat.extend(v)
        else:
            flat.append(v)
    return flat or [MISSING]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_WORD_OPS = ("eq", "ne", "gt", "ge", "lt", "le", "like", "in", "between")
_SYMBOL_TO_WORD = {"==": "eq", "=": "eq", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le"}
_KEYWORDS = frozenset(_WORD_OPS + ("and", "or", "not", "true", "false", "null"))


class _Parser:
    def __init__(self, tokens: list[Token], text: str) -> None:
        self.tokens = tokens
        self.text = text
        self.i = 0

    # -- helpers ---------------------------------------------------------
    @property
    def cur(self) -> Token:
        return self.tokens[self.i]

    def advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def is_keyword(self, *names: str) -> bool:
        return self.cur.kind == "word" and self.cur.value.lower() in names

    def error(self, message: str, tok: Token | None = None) -> FilterSyntaxError:
        tok = tok or self.cur
        return FilterSyntaxError(message, text=self.text, pos=tok.pos)

    # -- grammar ---------------------------------------------------------
    def parse(self) -> Expr:
        if self.cur.kind == "eof":
            raise self.error("expression is empty")
        expr = self.parse_or()
        if self.cur.kind != "eof":
            if self.cur.kind == "rparen":
                raise self.error("unbalanced ')' with no matching '('")
            raise self.error(
                f"unexpected {self.cur.value!r}; expected 'and', 'or' or end of expression",
            )
        return expr

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.is_keyword("or"):
            self.advance()
            right = self.parse_and()
            left = Or(left, right)
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self.is_keyword("and"):
            self.advance()
            right = self.parse_not()
            left = And(left, right)
        return left

    def parse_not(self) -> Expr:
        if self.is_keyword("not"):
            self.advance()
            return Not(self.parse_not())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        if self.cur.kind == "lparen":
            open_tok = self.advance()
            inner = self.parse_or()
            if self.cur.kind != "rparen":
                raise self.error("missing ')' to close this '('", open_tok)
            self.advance()
            return inner
        return self.parse_comparison()

    def parse_comparison(self) -> Comparison:
        tok = self.cur
        if tok.kind != "word":
            if tok.kind == "eof":
                raise self.error("expected a field name")
            raise self.error(f"expected a field name, found {tok.value!r}")
        if tok.value.lower() in _KEYWORDS:
            raise self.error(f"expected a field name, found keyword {tok.value!r}")
        path = self.advance().value

        op_tok = self.cur
        if op_tok.kind == "op":
            self.advance()
            op = _SYMBOL_TO_WORD[op_tok.value]
        elif op_tok.kind == "word":
            word = op_tok.value.lower()
            if word == "not":
                self.advance()
                if not self.is_keyword("in"):
                    raise self.error("expected 'in' after 'not'")
                self.advance()
                op = "not in"
            elif word in _WORD_OPS:
                self.advance()
                op = word
            else:
                close = difflib.get_close_matches(word, list(_WORD_OPS), n=1, cutoff=0.5)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                raise self.error(
                    f"unknown operator {op_tok.value!r} after '{path}'; "
                    f"expected one of eq, ne, gt, ge, lt, le, in, like, between{hint}",
                    op_tok,
                )
        elif op_tok.kind == "eof":
            raise self.error(f"expected an operator after '{path}' (eq, ne, gt, ge, lt, le, in, like, between)")
        else:
            raise self.error(f"expected an operator after '{path}', found {op_tok.value!r}", op_tok)

        if op in ("in", "not in"):
            return Comparison(path, op, self.parse_list(op))
        if op == "between":
            values = self.parse_list(op)
            if len(values) != 2:
                raise self.error("'between' needs exactly two values, e.g. between [10, 100]", op_tok)
            return Comparison(path, op, values)
        return Comparison(path, op, self.parse_value(op))

    def parse_list(self, op: str) -> list[Any]:
        if self.cur.kind != "lbracket":
            raise self.error(f'expected a list after \'{op}\', e.g. {op} ["a", "b"]')
        self.advance()
        values: list[Any] = []
        if self.cur.kind == "rbracket":
            self.advance()
            return values
        while True:
            values.append(self.parse_value(op))
            if self.cur.kind == "comma":
                self.advance()
                continue
            if self.cur.kind == "rbracket":
                self.advance()
                return values
            raise self.error("expected ',' or ']' in list")

    def parse_value(self, op: str) -> Any:
        tok = self.cur
        if tok.kind == "string":
            self.advance()
            return tok.value
        if tok.kind == "number":
            self.advance()
            return float(tok.value) if "." in tok.value else int(tok.value)
        if tok.kind == "word":
            lowered = tok.value.lower()
            if lowered in ("and", "or", "not"):
                raise self.error(f"expected a value after '{op}', found keyword {tok.value!r}")
            self.advance()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            if lowered == "null":
                return None
            return tok.value
        if tok.kind == "eof":
            raise self.error(f"expected a value after '{op}'")
        raise self.error(f"expected a value after '{op}', found {tok.value!r}")


def parse_filter(text: str) -> Expr:
    """Parse a ``--where`` expression into an :class:`Expr` (raises :class:`FilterSyntaxError`)."""
    return _Parser(tokenize(text), text).parse()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _as_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and _NUMBER_RE.match(value.strip()):
        return float(value) if "." in value else int(value)
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _is_absent(value: Any) -> bool:
    return value is MISSING or value is None


def like_match(value: Any, pattern: str) -> bool:
    """Case-insensitive ``*``/``?`` glob match against ``str(value)``."""
    if _is_absent(value):
        return False
    return glob_to_regex(pattern).fullmatch(str(value)) is not None


def _equals(actual: Any, expected: Any) -> bool:
    if expected is None:
        return _is_absent(actual)
    if _is_absent(actual):
        return False
    if isinstance(expected, bool) or isinstance(actual, bool):
        a, e = _as_bool(actual), _as_bool(expected)
        return a is not None and e is not None and a == e
    a_num, e_num = _as_number(actual), _as_number(expected)
    if a_num is not None and e_num is not None:
        return a_num == e_num
    if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
        return bool(actual == expected)
    return str(actual).lower() == str(expected).lower()


def _order(actual: Any, expected: Any) -> int | None:
    """Return -1/0/1 comparing *actual* to *expected*, or ``None`` when incomparable."""
    if _is_absent(actual) or expected is None:
        return None
    a_num, e_num = _as_number(actual), _as_number(expected)
    if a_num is not None and e_num is not None:
        return (a_num > e_num) - (a_num < e_num)
    if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
        return None
    a_str, e_str = str(actual).lower(), str(expected).lower()
    return (a_str > e_str) - (a_str < e_str)


def compare(op: str, actual: Any, expected: Any) -> bool:
    """Evaluate ``actual <op> expected`` with the CLI's coercion rules. Never raises."""
    if op == "eq":
        return _equals(actual, expected)
    if op == "ne":
        return not _equals(actual, expected)
    if op == "like":
        return like_match(actual, str(expected))
    if op == "in":
        return any(_equals(actual, e) for e in (expected or []))
    if op == "not in":
        return not any(_equals(actual, e) for e in (expected or []))
    if op == "between":
        low, high = expected
        lo = _order(actual, low)
        hi = _order(actual, high)
        return lo is not None and hi is not None and lo >= 0 and hi <= 0
    order = _order(actual, expected)
    if order is None:
        return False
    if op == "gt":
        return order > 0
    if op == "ge":
        return order >= 0
    if op == "lt":
        return order < 0
    if op == "le":
        return order <= 0
    return False


def apply_filter(data: Any, expr: Expr) -> tuple[Any, int]:
    """Filter *data* by *expr*. Returns ``(kept, removed_count)``.

    A dict is treated as a single record: it is returned unchanged when it
    matches and replaced by an empty list otherwise.
    """
    if isinstance(data, list):
        kept = [row for row in data if isinstance(row, dict) and expr.evaluate(row)]
        return kept, len(data) - len(kept)
    if isinstance(data, dict):
        if expr.evaluate(data):
            return data, 0
        return [], 1
    return data, 0


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


class SortSyntaxError(ValidationError):
    """A ``--sort`` specification could not be parsed (exit code 2)."""

    def __init__(self, message: str, *, spec: str) -> None:
        super().__init__(
            f"Invalid --sort specification {spec!r}: {message}",
            suggestion="Use --sort FIELD or --sort FIELD:desc (comma-separate several keys). See 'ntsk docs fields'.",
        )


def parse_sort_spec(spec: str) -> list[tuple[str, bool]]:
    """Parse ``"a,b:desc,c:asc"`` into ``[(path, descending), ...]``."""
    out: list[tuple[str, bool]] = []
    for raw in spec.split(","):
        item = raw.strip()
        if not item:
            continue
        path, _, direction = item.partition(":")
        path = path.strip()
        direction = direction.strip().lower()
        if not path:
            raise SortSyntaxError("field name is empty", spec=spec)
        if direction not in ("", "asc", "desc"):
            raise SortSyntaxError(f"direction must be 'asc' or 'desc', got {direction!r}", spec=spec)
        out.append((path, direction == "desc"))
    if not out:
        raise SortSyntaxError("nothing to sort by", spec=spec)
    return out


def _sort_key_factory(rows: Sequence[dict[str, Any]], path: str) -> Any:
    values = [get_path(row, path) for row in rows]
    present = [v for v in values if not _is_absent(v)]
    numeric_column = bool(present) and all(_as_number(v) is not None for v in present)

    def key(row: dict[str, Any]) -> tuple[int, Any]:
        value = get_path(row, path)
        if isinstance(value, list):
            value = value[0] if value else MISSING
        if _is_absent(value):
            return (3, 0)
        if isinstance(value, bool):
            return (0, int(value))
        if numeric_column:
            return (1, _as_number(value))
        if isinstance(value, (int, float)):
            return (1, value)
        return (2, str(value).lower())

    return key


def sort_records(data: Any, specs: Sequence[tuple[str, bool]]) -> Any:
    """Stable multi-key sort; missing values sort last regardless of direction."""
    if not isinstance(data, list) or not specs:
        return data
    rows = [r for r in data if isinstance(r, dict)]
    others = [r for r in data if not isinstance(r, dict)]
    for path, descending in reversed(list(specs)):
        key = _sort_key_factory(rows, path)
        if descending:
            present = [r for r in rows if key(r)[0] != 3]
            absent = [r for r in rows if key(r)[0] == 3]
            present.sort(key=key, reverse=True)
            rows = present + absent
        else:
            rows.sort(key=key)
    return rows + others
