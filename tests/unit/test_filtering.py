"""Unit tests for netskope_cli.core.filtering (client-side --where / --sort)."""

from __future__ import annotations

import pytest

from netskope_cli.core.filtering import (
    And,
    Comparison,
    FilterSyntaxError,
    Not,
    Or,
    SortSyntaxError,
    apply_filter,
    compare,
    like_match,
    parse_filter,
    parse_sort_spec,
    sort_records,
    tokenize,
)

DEVICES = [
    {
        "hostname": "LAPTOP-1",
        "host_info": {"os": "Windows", "os_version": "11"},
        "epdlp": {"criticalErrorsCount": 2},
        "last_event_timestamp": 1756000001,
        "idps": None,
        "on_premises_detail": [{"match_ip": "10.0.4.1"}, {"match_ip": "192.168.1.1"}],
        "tags": ["a", "b"],
        "client_version": "120.1",
        "active": True,
    },
    {
        "hostname": "mac-2",
        "host_info": {"os": "macOS", "os_version": "14"},
        "epdlp": {"criticalErrorsCount": 0},
        "last_event_timestamp": 1755000000,
        "idps": "x",
        "on_premises_detail": [],
        "tags": [],
        "client_version": "119.0",
        "active": False,
    },
    {"hostname": "[bracket-3]", "host_info": {"os": "Linux"}, "last_event_timestamp": 1754000000, "active": "true"},
]


def names(expr_text: str) -> list[str]:
    kept, _ = apply_filter(DEVICES, parse_filter(expr_text))
    return [r["hostname"] for r in kept]


class TestTokenizer:
    def test_kinds(self) -> None:
        toks = tokenize("a.b[].c eq \"x y\" and n >= -5 or z in [1, 'two']")
        kinds = [t.kind for t in toks]
        assert kinds == [
            "word", "word", "string", "word", "word", "op", "number", "word", "word", "word",
            "lbracket", "number", "comma", "string", "rbracket", "eof",
        ]  # fmt: skip
        assert toks[0].value == "a.b[].c"
        assert toks[2].value == "x y"
        assert toks[6].value == "-5"

    def test_escapes_and_barewords(self) -> None:
        toks = tokenize(r'user eq "a\"b" or user eq alice@example.com')
        assert toks[2].value == 'a"b'
        assert toks[6].value == "alice@example.com"

    def test_index_and_glob_words(self) -> None:
        toks = tokenize("protocols[0].port eq 443 and name like *DNS*")
        assert toks[0].value == "protocols[0].port"
        assert toks[6].value == "*DNS*"

    def test_unterminated_string_position(self) -> None:
        with pytest.raises(FilterSyntaxError) as exc:
            tokenize('a eq "oops')
        assert exc.value.pos == 5
        assert exc.value.exit_code == 2
        assert "^" in exc.value.message

    def test_unexpected_char(self) -> None:
        with pytest.raises(FilterSyntaxError):
            tokenize("a eq {x}")


class TestParser:
    def test_precedence_and_before_or(self) -> None:
        expr = parse_filter("a eq 1 or b eq 2 and c eq 3")
        assert isinstance(expr, Or)
        assert isinstance(expr.right, And)

    def test_parentheses_and_not(self) -> None:
        expr = parse_filter("not (a eq 1 or b eq 2) and c ne 3")
        assert isinstance(expr, And)
        assert isinstance(expr.left, Not)
        assert isinstance(expr.left.inner, Or)

    def test_symbolic_aliases_and_case(self) -> None:
        expr = parse_filter("A == 1 AND b != 2 And c >= 3 and d <= 4 and e > 5 and f < 6 and g = 7")
        comps = []

        def walk(e: object) -> None:
            if isinstance(e, Comparison):
                comps.append(e.op)
            elif isinstance(e, And):
                walk(e.left)
                walk(e.right)

        walk(expr)
        assert comps == ["eq", "ne", "ge", "le", "gt", "lt", "eq"]

    def test_values(self) -> None:
        expr = parse_filter("a eq true and b eq false and c eq null and d eq 1.5 and e eq bare and f eq 'q'")
        values = []

        def walk(e: object) -> None:
            if isinstance(e, Comparison):
                values.append(e.value)
            elif isinstance(e, And):
                walk(e.left)
                walk(e.right)

        walk(expr)
        assert values == [True, False, None, 1.5, "bare", "q"]

    def test_in_not_in_between_like(self) -> None:
        assert parse_filter('s in ["a", "b"]') == Comparison("s", "in", ["a", "b"])
        assert parse_filter("s not in [1]") == Comparison("s", "not in", [1])
        assert parse_filter("n between [10, 100]") == Comparison("n", "between", [10, 100])
        assert parse_filter('n like "*x*"') == Comparison("n", "like", "*x*")
        assert parse_filter("s in []") == Comparison("s", "in", [])

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("", "empty"),
            ("hostname", "expected an operator"),
            ("hostname eq", "expected a value"),
            ("hostname equals 1", "did you mean 'eq'"),
            ("hostname eq 1 and", "expected a field name"),
            ("(hostname eq 1", "missing ')'"),
            ("hostname eq 1)", "unbalanced ')'"),
            ("hostname eq 1 hostname eq 2", "unexpected"),
            ("eq eq 1", "keyword"),
            ("n between [1]", "exactly two"),
            ("s in 1", "expected a list"),
            ("s in [1 2]", "expected ',' or ']'"),
            ("s not eq 1", "expected 'in' after 'not'"),
            ("a eq and", "found keyword"),
        ],
    )
    def test_errors(self, text: str, fragment: str) -> None:
        with pytest.raises(FilterSyntaxError) as exc:
            parse_filter(text)
        assert fragment in exc.value.message
        assert exc.value.exit_code == 2
        assert "docs fields" in (exc.value.suggestion or "")


class TestCompare:
    @pytest.mark.parametrize(
        ("op", "actual", "expected", "result"),
        [
            ("eq", "Windows", "windows", True),
            ("eq", 443, "443", True),
            ("eq", "443", 443, True),
            ("eq", True, "true", True),
            ("eq", "false", False, True),
            ("eq", 1, True, False),
            ("eq", None, None, True),
            ("eq", "x", None, False),
            ("ne", None, "x", True),
            ("gt", 10, 9, True),
            ("gt", "10", 9, True),
            ("gt", "b", "A", True),
            ("gt", None, 1, False),
            ("le", 5, 5, True),
            ("between", 50, [10, 100], True),
            ("between", 5, [10, 100], False),
            ("between", "m", ["a", "z"], True),
            ("in", "B", ["a", "b"], True),
            ("not in", "c", ["a", "b"], True),
            ("like", "Windows 11", "win*", True),
            ("like", "Windows 11", "*11", True),
            ("like", "Windows 11", "windows", False),
            ("like", "[npm.x]", "[npm*", True),
            ("like", None, "*", False),
            ("eq", ["a"], ["a"], True),
            ("gt", {"a": 1}, 1, False),
        ],
    )
    def test_table(self, op: str, actual: object, expected: object, result: bool) -> None:
        assert compare(op, actual, expected) is result

    def test_like_match_literal_brackets(self) -> None:
        assert like_match("[a]", "[a]")
        assert not like_match("a", "[a]")


class TestEvaluate:
    def test_nested_and_glob(self) -> None:
        assert names('host_info.os like "win*"') == ["LAPTOP-1"]
        assert names("host_info.os like windows") == ["LAPTOP-1"]

    def test_numeric_and_logic(self) -> None:
        expr = "epdlp.criticalErrorsCount gt 0 or last_event_timestamp lt 1754500000"
        assert names(expr) == ["LAPTOP-1", "[bracket-3]"]
        assert names("last_event_timestamp between [1754000000, 1755000000]") == ["mac-2", "[bracket-3]"]

    def test_null_and_missing(self) -> None:
        assert names("idps eq null") == ["LAPTOP-1", "[bracket-3]"]
        assert names("idps ne null") == ["mac-2"]
        assert names("epdlp.criticalErrorsCount eq null") == ["[bracket-3]"]
        assert names("nope eq 1") == []
        assert names("nope ne 1") == ["LAPTOP-1", "mac-2", "[bracket-3]"]

    def test_bool_coercion(self) -> None:
        assert names("active eq true") == ["LAPTOP-1", "[bracket-3]"]

    def test_list_any_semantics(self) -> None:
        assert names('on_premises_detail[].match_ip like "10.*"') == ["LAPTOP-1"]
        assert names('on_premises_detail.match_ip like "10.*"') == ["LAPTOP-1"]
        assert names("tags eq a") == ["LAPTOP-1"]
        assert names("tags ne a") == ["mac-2", "[bracket-3]"]
        assert names('tags in ["b", "zzz"]') == ["LAPTOP-1"]

    def test_string_version_compare(self) -> None:
        assert names('client_version lt "120"') == ["mac-2"]

    def test_in_not_in(self) -> None:
        assert names('host_info.os in ["macos", "linux"]') == ["mac-2", "[bracket-3]"]
        assert names('host_info.os not in ["macos", "linux"]') == ["LAPTOP-1"]

    def test_not(self) -> None:
        assert names("not host_info.os eq windows") == ["mac-2", "[bracket-3]"]

    def test_apply_filter_shapes(self) -> None:
        expr = parse_filter("a eq 1")
        assert apply_filter({"a": 1}, expr) == ({"a": 1}, 0)
        assert apply_filter({"a": 2}, expr) == ([], 1)
        assert apply_filter("text", expr) == ("text", 0)
        assert apply_filter([{"a": 1}, "junk", {"a": 2}], expr) == ([{"a": 1}], 2)

    def test_paths(self) -> None:
        assert parse_filter("a.b eq 1 and (c eq 2 or not d eq 3)").paths() == ["a.b", "c", "d"]


class TestSort:
    def test_parse_sort_spec(self) -> None:
        assert parse_sort_spec("a") == [("a", False)]
        assert parse_sort_spec("a:desc, b:asc ,c") == [("a", True), ("b", False), ("c", False)]
        with pytest.raises(SortSyntaxError) as exc:
            parse_sort_spec("a:down")
        assert exc.value.exit_code == 2
        with pytest.raises(SortSyntaxError):
            parse_sort_spec(" , ")
        with pytest.raises(SortSyntaxError):
            parse_sort_spec(":desc")

    def test_sort_mixed_and_missing_last(self) -> None:
        rows = [{"v": "b"}, {"v": None}, {"v": 2}, {}, {"v": "A"}, {"v": 10}]
        asc = sort_records(rows, [("v", False)])
        assert [r.get("v") for r in asc] == [2, 10, "A", "b", None, None]
        desc = sort_records(rows, [("v", True)])
        assert [r.get("v") for r in desc] == ["b", "A", 10, 2, None, None]

    def test_numeric_strings_column(self) -> None:
        rows = [{"n": "10"}, {"n": "9"}, {"n": 100}]
        assert [r["n"] for r in sort_records(rows, [("n", False)])] == ["9", "10", 100]

    def test_multi_key_stable_and_nested(self) -> None:
        rows = [
            {"os": "b", "h": "2"},
            {"os": "a", "h": "9"},
            {"os": "b", "h": "1"},
            {"os": "a", "h": "3"},
        ]
        out = sort_records(rows, [("os", False), ("h", True)])
        assert [(r["os"], r["h"]) for r in out] == [("a", "9"), ("a", "3"), ("b", "2"), ("b", "1")]
        nested = sort_records(DEVICES, [("host_info.os", False)])
        assert [r["host_info"]["os"] for r in nested] == ["Linux", "macOS", "Windows"]

    def test_non_list_passthrough(self) -> None:
        assert sort_records({"a": 1}, [("a", False)]) == {"a": 1}
        assert sort_records([{"a": 2}, "x", {"a": 1}], [("a", False)]) == [{"a": 1}, {"a": 2}, "x"]
