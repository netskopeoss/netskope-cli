"""Tests for core.datasearch: --api-fields widening and the 10,000-row --count cap.

Covers the two 1.4.8 bugs: a local ``--fields`` that
shadowed the global one and was never passed to the formatter, and ``--count``
reporting the API page cap as if it were the total.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.core.datasearch import (
    DATASEARCH_PAGE_CAP,
    DEFAULT_COUNT_CEILING,
    ApiFieldSelection,
    ExactCount,
    count_ceiling,
    count_exact,
    is_page_capped,
    print_exact_count,
    resolve_api_fields,
    split_names,
)
from netskope_cli.core.exceptions import ValidationError
from netskope_cli.core.fieldpaths import top_level_name
from netskope_cli.core.output import OutputFormatter
from netskope_cli.main import State, _hoist_global_options, app, cli

BASE = "https://test.goskope.com"
ALERT_URL = f"{BASE}/api/v2/events/datasearch/alert"

ALERTS = [
    {
        "_id": "a1",
        "alert_name": "Block-Malicious-Domains",
        "alert_type": "policy",
        "action": "block",
        "app": "DNS",
        "qdomain": "bad.example",
        "timestamp": 1784851173,
        "tags": ["x"],
    },
    {
        "_id": "a2",
        "alert_name": "Block-Malicious-Domains",
        "alert_type": "policy",
        "action": "allow",
        "app": "DNS",
        "qdomain": "ok.example",
        "timestamp": 1784851100,
    },
]


def _without_iso(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the ``*_iso`` companions the formatter adds to machine-readable output."""
    return [{k: v for k, v in r.items() if not k.endswith("_iso")} for r in rows]


def _out(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    captured = capsys.readouterr()
    return captured.out, captured.err


def _flat(text: str) -> str:
    """Collapse the line wrapping Rich applies to stderr notices in the 80-column test runner."""
    return " ".join(text.split())


def _request_query(route: respx.Route, index: int = 0) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(route.calls[index].request.url)).query)


# ---------------------------------------------------------------------------
# fieldpaths.top_level_name and split_names
# ---------------------------------------------------------------------------


class TestTopLevelName:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("timestamp", "timestamp"),
            ("host_info.os", "host_info"),
            ("protocols[].port", "protocols"),
            ("protocols[0].port", "protocols"),
            ("epdlp.*", "epdlp"),
            ("*_timestamp", None),
            ("host?name", None),
            ("", None),
            ("  spaced  ", "spaced"),
        ],
    )
    def test_cases(self, spec: str, expected: str | None) -> None:
        assert top_level_name(spec) == expected

    def test_split_names(self) -> None:
        assert split_names(None) == []
        assert split_names("") == []
        assert split_names(" a, b ,,c ") == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# resolve_api_fields
# ---------------------------------------------------------------------------


class _Ctx:
    def __init__(self, **kw: Any) -> None:
        self.obj = State(**kw)


class TestResolveApiFields:
    def test_absent_sends_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert resolve_api_fields(_Ctx(), None) == ApiFieldSelection(None, None)
        assert resolve_api_fields(_Ctx(), " , ") == ApiFieldSelection(None, None)
        assert _out(capsys)[1] == ""

    def test_plain_global_fields_print_transition_note(self, capsys: pytest.CaptureFixture[str]) -> None:
        sel = resolve_api_fields(_Ctx(fields=["timestamp", "alert_name"]), None)
        assert sel == ApiFieldSelection(None, None)
        _, err = _out(capsys)
        assert "--api-fields" in err and "client-side" in err

    def test_nested_or_glob_global_fields_do_not_note(self, capsys: pytest.CaptureFixture[str]) -> None:
        resolve_api_fields(_Ctx(fields=["host_info.os"]), None)
        resolve_api_fields(_Ctx(fields=["epdlp.*"]), None)
        assert _out(capsys)[1] == ""

    def test_note_ignores_auto_quiet_but_not_an_explicit_quiet(self, capsys: pytest.CaptureFixture[str]) -> None:
        # main() switches ``quiet`` on for piped stdout; scripts are the note's
        # audience, so only the flag the user typed suppresses it.
        resolve_api_fields(_Ctx(fields=["a", "b"], quiet=True), None)
        assert "--api-fields" in _out(capsys)[1]
        resolve_api_fields(_Ctx(fields=["a", "b"], quiet=True, quiet_explicit=True), None)
        assert _out(capsys)[1] == ""

    def test_widens_with_where_sort_and_global_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        ctx = _Ctx(
            fields=["timestamp", "host_info.os", "*_x"],
            where='action eq "block" and (user like "*@corp" or epdlp.count gt 1)',
            where_expr=None,
            sort="severity:desc,timestamp",
        )
        from netskope_cli.core.filtering import parse_filter, parse_sort_spec

        ctx.obj.where_expr = parse_filter(ctx.obj.where)
        ctx.obj.sort_spec = parse_sort_spec(ctx.obj.sort)
        sel = resolve_api_fields(ctx, "timestamp,qdomain")
        assert sel.request == "timestamp,qdomain,host_info,action,user,epdlp,severity"
        # global --fields wins for display, so nothing is forced here
        assert sel.display is None
        assert _out(capsys)[1] == ""

    def test_display_is_requested_list_without_global_fields(self) -> None:
        sel = resolve_api_fields(_Ctx(), "timestamp, qdomain,timestamp")
        assert sel == ApiFieldSelection("timestamp,qdomain", ["timestamp", "qdomain"])
        assert sel.projected and not ApiFieldSelection(None, None).projected

    def test_iso_companions_widen_to_the_base_field(self) -> None:
        sel = resolve_api_fields(_Ctx(fields=["alert_name", "timestamp_iso"]), "alert_name")
        assert sel.request == "alert_name,timestamp"


# ---------------------------------------------------------------------------
# Page cap detection and exact counting
# ---------------------------------------------------------------------------


class TestIsPageCapped:
    def test_short_page_not_capped(self) -> None:
        assert is_page_capped({"result": [{"a": 1}] * 5}, 10) is False

    def test_full_page_without_total_is_capped(self) -> None:
        assert is_page_capped({"result": [{"a": 1}] * 10}, 10) is True
        assert is_page_capped([{"a": 1}] * 10, 10) is True

    def test_status_count_equal_to_rows_is_capped(self) -> None:
        assert is_page_capped({"result": [{"a": 1}] * 10, "status": {"count": 10}}, 10) is True

    def test_larger_total_is_exact(self) -> None:
        assert is_page_capped({"result": [{"a": 1}] * 10, "total": 500}, 10) is False

    def test_non_list_never_capped(self) -> None:
        assert is_page_capped({"result": {"a": 1}}, 1) is False
        assert is_page_capped(None, 1) is False


class _FakeClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None) -> Any:
        assert method == "GET"
        params = dict(params or {})
        self.calls.append(params)
        offset, size = params["offset"], params["limit"]
        return {"result": self.rows[offset : offset + size]}


class TestCountExact:
    def test_pages_until_short_page(self) -> None:
        client = _FakeClient([{"n": i} for i in range(7)])
        result = count_exact(client, "/x", {"query": "q", "limit": 99}, page_size=3, ceiling=1000, quiet=True)
        assert result == ExactCount(count=7, fetched=7, requests=3, reached_ceiling=False)
        assert [c["offset"] for c in client.calls] == [0, 3, 6]
        assert all(c["limit"] == 3 and c["query"] == "q" for c in client.calls)

    def test_exact_multiple_of_page_size_needs_one_more_request(self) -> None:
        client = _FakeClient([{"n": i} for i in range(6)])
        result = count_exact(client, "/x", {}, page_size=3, ceiling=1000, quiet=True)
        assert result.count == 6 and result.requests == 3 and not result.reached_ceiling

    def test_stops_at_ceiling(self) -> None:
        client = _FakeClient([{"n": i} for i in range(100)])
        result = count_exact(client, "/x", {}, page_size=3, ceiling=6, quiet=True)
        assert result == ExactCount(count=6, fetched=6, requests=2, reached_ceiling=True)

    def test_ceiling_not_a_page_multiple_trims_the_last_page(self) -> None:
        client = _FakeClient([{"n": i} for i in range(100)])
        result = count_exact(client, "/x", {}, page_size=3, ceiling=5, quiet=True)
        assert result == ExactCount(count=5, fetched=5, requests=2, reached_ceiling=True)
        assert [c["limit"] for c in client.calls] == [3, 2]

    def test_total_below_ceiling_is_exact(self) -> None:
        client = _FakeClient([{"n": i} for i in range(4)])
        result = count_exact(client, "/x", {}, page_size=3, ceiling=5, quiet=True)
        assert result == ExactCount(count=4, fetched=4, requests=2, reached_ceiling=False)

    def test_error_envelope_is_raised_not_counted(self) -> None:
        from netskope_cli.core.exceptions import NetskopeError

        class Broken:
            def request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None) -> Any:
                return {"ok": 0, "message": "bad query"}

        with pytest.raises(NetskopeError, match="bad query"):
            count_exact(Broken(), "/x", {}, page_size=3, ceiling=10, quiet=True)

    def test_where_sees_flattened_groups_and_warns_on_unknown_paths(self, capsys: pytest.CaptureFixture[str]) -> None:
        from netskope_cli.core.filtering import parse_filter

        grouped = _FakeClient([{"_id": {"app": "DNS"}, "count": 5}, {"_id": {"app": "SSH"}, "count": 2}])
        result = count_exact(
            grouped, "/x", {}, where=parse_filter('app eq "DNS"'), page_size=10, ceiling=100, quiet=True
        )
        assert result.count == 1
        assert _out(capsys)[1] == ""
        count_exact(
            _FakeClient([{"n": 1}]), "/x", {}, where=parse_filter("nope eq 1"), page_size=10, ceiling=100, quiet=True
        )
        assert "--where: 'nope' is not present in any record" in _out(capsys)[1]

    def test_error_envelope_message_is_markup_safe(self) -> None:
        from netskope_cli.core.exceptions import NetskopeError

        class Broken:
            def request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None) -> Any:
                return {"ok": 0, "message": "Invalid field [timestamp] in query"}

        with pytest.raises(NetskopeError) as exc:
            count_exact(Broken(), "/x", {}, page_size=3, ceiling=10, quiet=True)
        assert "\\[timestamp]" in exc.value.message

    def test_where_filters_each_page(self) -> None:
        from netskope_cli.core.filtering import parse_filter

        client = _FakeClient([{"n": i} for i in range(10)])
        result = count_exact(client, "/x", {}, where=parse_filter("n ge 7"), page_size=4, ceiling=1000, quiet=True)
        assert result.count == 3 and result.fetched == 10

    def test_empty(self) -> None:
        result = count_exact(_FakeClient([]), "/x", {}, page_size=3, ceiling=10, quiet=True)
        assert result == ExactCount(0, 0, 1, False)


class TestPrintExactCount:
    def test_plain(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_exact_count(ExactCount(42, 42, 1, False), where=False, ceiling=100, quiet=False, no_color=True)
        out, err = _out(capsys)
        assert out == "42\n" and err == ""

    def test_ceiling_and_where(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_exact_count(ExactCount(5, 100, 10, True), where=True, ceiling=100, quiet=False, no_color=True)
        out, err = _out(capsys)
        assert out == "5+\n"
        assert "5 of 100 rows matched --where" in err
        assert "ceiling of 100 rows after 10 requests" in err

    def test_quiet_keeps_the_ceiling_warning_but_drops_the_where_note(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_exact_count(ExactCount(5, 100, 10, True), where=True, ceiling=100, quiet=True, no_color=True)
        out, err = _out(capsys)
        assert out == "5+\n"
        assert "matched --where" not in err
        assert "ceiling of 100 rows" in err


class TestCountCeiling:
    def test_default_and_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETSKOPE_COUNT_CEILING", raising=False)
        assert count_ceiling() == DEFAULT_COUNT_CEILING
        monkeypatch.setenv("NETSKOPE_COUNT_CEILING", "50_000")
        assert count_ceiling() == 50_000

    @pytest.mark.parametrize("bad", ["0", "-5", "lots"])
    def test_invalid_raises(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        monkeypatch.setenv("NETSKOPE_COUNT_CEILING", bad)
        with pytest.raises(ValidationError):
            count_ceiling()


# ---------------------------------------------------------------------------
# Formatter: strict unknown fields and capped counts
# ---------------------------------------------------------------------------


class TestFormatterWarningsAndCapped:
    def test_unknown_field_warns_and_prints_nulls(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["nope", "alert_name"]).format_output(ALERTS, fmt="json")
        out, err = _out(capsys)
        assert "'nope' not found in any record" in err and "--list-fields" in err
        assert json.loads(out)[0] == {"nope": None, "alert_name": "Block-Malicious-Domains"}

    def test_server_side_projection_missing_field_warns_under_api_fields_label(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        OutputFormatter(no_color=True).format_output(ALERTS, fmt="json", fields=["timestamp", "qdomainn"])
        out, err = _out(capsys)
        assert "--api-fields: 'qdomainn' not found in any record" in err
        assert "qdomain" in err  # close match suggested
        row = json.loads(out)[0]
        assert row["timestamp_iso"].startswith("2026-")  # the companion of a projected field survives
        assert {k: v for k, v in row.items() if k != "timestamp_iso"} == {"timestamp": 1784851173, "qdomainn": None}

    def test_capped_count_and_banner(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True).format_output(
            {"result": ALERTS * 5, "status": {"count": 10}}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "10+"
        assert "results (capped)" not in err  # --count prints its own notice; no second banner
        assert "Count capped at the API maximum of 10 rows" in err and "narrow the time range" in err
        OutputFormatter(no_color=True).format_output({"result": ALERTS * 5}, fmt="table", capped_at=10)
        _out_, err = _out(capsys)
        assert "10+ results (capped)" in err  # the banner belongs to the listing, not the count

    def test_capped_with_where_counts_filtered_rows(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, where='action eq "block"').format_output(
            {"result": ALERTS * 5}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "5+"
        assert "5 of 10 results matched --where" in err

    def test_null_or_empty_parents_warn(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = [{"user": "a", "tags": [], "host_info": None}, {"user": "b", "tags": []}]
        OutputFormatter(no_color=True, fields=["user", "tags[].name", "host_info.os"]).format_output(rows, fmt="json")
        out, err = _out(capsys)
        assert json.loads(out)[0] == {"user": "a", "tags[].name": None, "host_info.os": None}
        assert "'tags[].name' not found in any record" in err and "'host_info.os' not found" in err

    def test_hidden_internal_field_points_at_raw(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["_insertion_epoch_timestamp"]).format_output(
            {"result": [{"_insertion_epoch_timestamp": 1, "alert_name": "x"}]}, fmt="json"
        )
        assert "hidden unless you pass --raw" in _flat(_out(capsys)[1])

    def test_uncapped_count_unchanged(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, quiet=True).format_output({"result": ALERTS}, fmt="table", count_only=True)
        out, err = _out(capsys)
        assert out.strip() == "2" and "capped" not in err


# ---------------------------------------------------------------------------
# End-to-end through the CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("NETSKOPE_TENANT", "test.goskope.com")
    monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken123")
    monkeypatch.setenv("XDG_CONFIG_HOME", f"{tmp_path}/config")
    monkeypatch.setenv("XDG_DATA_HOME", f"{tmp_path}/data")
    monkeypatch.delenv("NETSKOPE_COUNT_CEILING", raising=False)
    # Tests assert the human-facing ``N+`` marker; a real pipe (see TestFourthReview) prints the bare integer.
    monkeypatch.setattr("netskope_cli.core.output.stdout_is_tty", lambda: True)


def _invoke(runner: CliRunner, *argv: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, _hoist_global_options(["ntsk", *argv])[1:])


def _alert_route(rows: list[dict[str, Any]] | None = None) -> respx.Route:
    return respx.get(ALERT_URL).mock(
        return_value=httpx.Response(200, json={"result": rows if rows is not None else ALERTS})
    )


def _urllist_route() -> respx.Route:
    """A fixed-schema (non-events) endpoint, where an unknown --fields name is provably wrong."""
    return respx.get(f"{BASE}/api/v2/policy/urllist").mock(
        return_value=httpx.Response(200, json={"result": [{"id": 1, "name": "Blocked"}], "total": 1})
    )


class TestGlobalFieldsOnDatasearchCommands:
    """Bug 1: the global --fields must reach the formatter on every command."""

    @respx.mock
    def test_alerts_csv_header_is_exactly_the_requested_columns(self, runner: CliRunner) -> None:
        route = _alert_route()
        result = _invoke(runner, "alerts", "list", "--limit", "2", "-o", "csv", "--fields", "timestamp,alert_name")
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[0] == "timestamp,alert_name"
        assert result.stdout.splitlines()[1] == "1784851173,Block-Malicious-Domains"
        assert "fields" not in _request_query(route)  # nothing sent server-side

    @respx.mock
    def test_alerts_json_keys_in_requested_order(self, runner: CliRunner) -> None:
        _alert_route()
        result = _invoke(runner, "alerts", "list", "--limit", "1", "-o", "json", "--fields", "timestamp,alert_name,app")
        assert result.exit_code == 0, result.output
        rows = json.loads(result.stdout)
        assert [list(r.keys()) for r in rows] == [["timestamp", "alert_name", "app"]] * 2

    @respx.mock
    def test_short_f_is_the_global_option_on_events(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/application").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "u", "app": "a", "extra": 1}]})
        )
        result = _invoke(runner, "events", "application", "-f", "app,user", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"app": "a", "user": "u"}]

    @respx.mock
    @pytest.mark.parametrize(
        ("argv", "url"),
        [
            (("events", "network"), f"{BASE}/api/v2/events/datasearch/network"),
            (("incidents", "list"), f"{BASE}/api/v2/events/datasearch/incident"),
            (("incidents", "search", "--query", "x eq 1"), f"{BASE}/api/v2/events/datasearch/incident"),
            (("steering", "private-apps", "list"), f"{BASE}/api/v2/steering/apps/private"),
            (("npa", "apps", "list"), f"{BASE}/api/v2/steering/apps/private"),
            (("policy", "url-list", "list"), f"{BASE}/api/v2/policy/urllist"),
            (("services", "private-apps", "list"), f"{BASE}/api/v2/steering/apps/private"),
        ],
    )
    def test_other_commands_project_and_order(self, runner: CliRunner, argv: tuple[str, ...], url: str) -> None:
        route = respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": [{"b": 2, "a": 1, "c": 3}], "total": 1})
        )
        result = _invoke(runner, *argv, "-o", "json", "--fields", "c,a")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"c": 3, "a": 1}]
        assert "fields" not in _request_query(route)

    def test_unknown_field_warns_and_renders_blank(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Never exit 2: which keys a page has depends on the rows that landed in it (optional
        # attributes on fixed-schema endpoints, subtypes on events), so the exit code would be
        # page-dependent.  A warning with close matches and a blank column is the contract.
        monkeypatch.setattr(sys, "argv", ["ntsk", "policy", "url-list", "list", "--fields", "nope,name", "-o", "csv"])
        with respx.mock:
            _urllist_route()
            cli()  # exit code 0: standalone_mode=False returns instead of raising SystemExit
        out, err = _out(capsys)
        assert out.splitlines()[0] == "nope,name"
        assert out.splitlines()[1] == ",Blocked"
        assert "'nope' not found" in err and "--list-fields" in err

    @respx.mock
    def test_transition_note_reaches_piped_stderr_unless_quiet(self, runner: CliRunner) -> None:
        # CliRunner's stdout is not a TTY, so this is the piped (auto-quiet) case.
        _alert_route()
        plain = _invoke(runner, "alerts", "list", "--fields", "timestamp,alert_name")
        assert "--api-fields" in plain.output
        quiet = _invoke(runner, "alerts", "list", "--fields", "timestamp,alert_name", "-q")
        assert "--api-fields" not in quiet.output
        nested = _invoke(runner, "alerts", "list", "--fields", "timestamp,tags[0]")
        assert "--api-fields" not in nested.output
        both = _invoke(runner, "alerts", "list", "--api-fields", "timestamp", "--fields", "timestamp")
        assert "Add --api-fields" not in both.output


class TestApiFields:
    @respx.mock
    def test_sent_to_api_and_shown_in_order(self, runner: CliRunner) -> None:
        route = _alert_route([{"qdomain": "bad.example", "timestamp": 1784851173, "_id": "a1"}])
        result = _invoke(runner, "alerts", "list", "--api-fields", "timestamp,qdomain", "-o", "json")
        assert result.exit_code == 0, result.output
        assert _request_query(route)["fields"] == ["timestamp,qdomain"]
        rows = json.loads(result.stdout)
        assert list(rows[0]) == ["timestamp", "timestamp_iso", "qdomain"]  # companion follows its field
        assert _without_iso(rows) == [{"timestamp": 1784851173, "qdomain": "bad.example"}]

    @respx.mock
    def test_projected_field_absent_from_response_does_not_fail(self, runner: CliRunner) -> None:
        # Sparse event schemas: the API accepts the name but no row in the window has it.
        _alert_route([{"timestamp": 1784851173, "alert_name": "DLP thing"}])
        result = _invoke(runner, "alerts", "list", "--api-fields", "timestamp,qdomain", "-o", "json")
        assert result.exit_code == 0, result.output
        assert _without_iso(json.loads(result.stdout)) == [{"timestamp": 1784851173, "qdomain": None}]
        assert "--api-fields: 'qdomain' not found" in result.output
        assert "--fields:" not in result.output

    @respx.mock
    def test_widened_for_where_and_filter_matches(self, runner: CliRunner) -> None:
        route = _alert_route()
        result = _invoke(
            runner,
            "alerts",
            "list",
            "--limit",
            "200",
            "--api-fields",
            "timestamp,qdomain",
            "--where",
            'action eq "block"',
            "-o",
            "json",
        )
        assert result.exit_code == 0, result.output
        assert _request_query(route)["fields"] == ["timestamp,qdomain,action"]
        assert _without_iso(json.loads(result.stdout)) == [{"timestamp": 1784851173, "qdomain": "bad.example"}]
        assert "not present in any record" not in result.output

    @respx.mock
    def test_widened_for_sort_and_global_fields(self, runner: CliRunner) -> None:
        route = respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"result": [{"srcip": "1", "dstport": 2, "action": "x"}]})
        )
        result = _invoke(
            runner,
            "events",
            "network",
            "--api-fields",
            "srcip",
            "--sort",
            "dstport:desc",
            "--fields",
            "action,srcip",
            "-o",
            "json",
        )
        assert result.exit_code == 0, result.output
        assert _request_query(route)["fields"] == ["srcip,action,dstport"]
        assert json.loads(result.stdout) == [{"action": "x", "srcip": "1"}]

    @respx.mock
    def test_events_list_and_audit_and_incidents(self, runner: CliRunner) -> None:
        page = respx.get(f"{BASE}/api/v2/events/datasearch/page").mock(
            return_value=httpx.Response(200, json={"result": [{"url": "u", "user": "x"}]})
        )
        audit = respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "x", "audit_log_event": "e"}]})
        )
        incident = respx.get(f"{BASE}/api/v2/events/datasearch/incident").mock(
            return_value=httpx.Response(200, json={"result": [{"incident_id": 1, "user": "x"}]})
        )
        assert _invoke(runner, "events", "list", "--type", "page", "--api-fields", "url", "-o", "json").exit_code == 0
        assert _request_query(page)["fields"] == ["url"]
        assert _invoke(runner, "events", "audit", "--api-fields", "user", "-o", "json").exit_code == 0
        assert _request_query(audit)["fields"] == ["user"]
        result = _invoke(runner, "incidents", "list", "--api-fields", "incident_id", "-o", "json")
        assert result.exit_code == 0, result.output
        assert _request_query(incident)["fields"] == ["incident_id"]
        assert json.loads(result.stdout) == [{"incident_id": 1}]

    @respx.mock
    def test_npa_policy_rules_api_fields(self, runner: CliRunner) -> None:
        route = respx.get(f"{BASE}/api/v2/policy/npa/rules").mock(
            return_value=httpx.Response(200, json={"data": [{"rule_id": 1, "rule_name": "r", "enabled": True}]})
        )
        result = _invoke(runner, "npa", "policy", "rules", "list", "--api-fields", "rule_name,rule_id", "-o", "json")
        assert result.exit_code == 0, result.output
        assert _request_query(route)["fields"] == ["rule_name,rule_id"]
        assert json.loads(result.stdout) == [{"rule_name": "r", "rule_id": 1}]

    def test_api_fields_is_never_hoisted_and_has_no_short_flag(self) -> None:
        assert _hoist_global_options(["ntsk", "events", "alerts", "--api-fields", "a", "-o", "json"]) == [
            "ntsk",
            "-o",
            "json",
            "events",
            "alerts",
            "--api-fields",
            "a",
        ]


FULL_PAGE = [
    {"alert_name": "x", "timestamp": 1784851173 - i, "action": "block" if i % 2 else "allow"}
    for i in range(DATASEARCH_PAGE_CAP)
]


class TestCountCap:
    """Bug 2: a full datasearch page is a lower bound, not a total."""

    @respx.mock
    def test_alerts_count_reports_lower_bound(self, runner: CliRunner) -> None:
        route = _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "list", "--since", "24h", "--count")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "10000+"
        assert "results (capped)" not in result.output
        assert "Count capped at the API maximum of 10,000 rows" in result.output and "--exact" in result.output
        assert _request_query(route)["limit"] == ["10000"]

    @respx.mock
    def test_small_window_is_exact_without_notice(self, runner: CliRunner) -> None:
        _alert_route()
        result = _invoke(runner, "alerts", "list", "--since", "1h", "--count")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "2"
        assert "capped" not in result.output

    @respx.mock
    def test_count_with_where_is_a_lower_bound_too(self, runner: CliRunner) -> None:
        _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "list", "--count", "--where", 'action eq "block"')
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "5000+"

    @respx.mock
    def test_events_and_incidents_count_use_the_full_page(self, runner: CliRunner) -> None:
        network = respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"result": FULL_PAGE})
        )
        incident = respx.get(f"{BASE}/api/v2/events/datasearch/incident").mock(
            return_value=httpx.Response(200, json={"result": ALERTS})
        )
        result = _invoke(runner, "events", "network", "--count")
        assert result.stdout.strip() == "10000+", result.output
        assert _request_query(network)["limit"] == ["10000"]
        result = _invoke(runner, "events", "list", "--type", "network", "--count")
        assert result.stdout.strip() == "10000+", result.output
        result = _invoke(runner, "incidents", "list", "--count")
        assert result.stdout.strip() == "2", result.output
        assert _request_query(incident)["limit"] == ["10000"]

    @respx.mock
    def test_events_count_prefers_an_envelope_total(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": ALERTS, "total": 5000})
        )
        result = _invoke(runner, "events", "audit", "--count")
        assert result.stdout.strip() == "5000", result.output
        assert "capped" not in result.output

        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"result": FULL_PAGE, "total": 50000})
        )
        for argv in (("events", "network", "--count"), ("events", "list", "--type", "network", "--count")):
            result = _invoke(runner, *argv)
            assert result.stdout.strip() == "50000", result.output
            assert "capped" not in result.output

    @respx.mock
    def test_events_banner_shows_envelope_total(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"result": ALERTS, "total": 40})
        )
        result = _invoke(runner, "events", "network", "-o", "csv")
        assert result.exit_code == 0, result.output
        assert "Showing 2 of 40 results" in result.output

    @respx.mock
    def test_exact_surfaces_api_error_envelope(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"ok": 0, "message": "bad query"})
        )
        result = _invoke(runner, "events", "network", "--start", "1h", "--count", "--exact")
        assert result.exit_code != 0
        assert "bad query" in (result.output + str(result.exception))

    @respx.mock
    def test_exact_pages_with_offset(self, runner: CliRunner) -> None:
        def pages(request: httpx.Request) -> httpx.Response:
            offset = int(parse_qs(urlparse(str(request.url)).query)["offset"][0])
            size = {0: DATASEARCH_PAGE_CAP, DATASEARCH_PAGE_CAP: DATASEARCH_PAGE_CAP, 2 * DATASEARCH_PAGE_CAP: 500}[
                offset
            ]
            return httpx.Response(200, json={"result": FULL_PAGE[:size]})

        route = respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(side_effect=pages)
        result = _invoke(runner, "events", "network", "--start", "7d", "--count", "--exact")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "20500"
        assert route.call_count == 3
        assert "capped" not in result.output

    @respx.mock
    def test_exact_reports_ceiling(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETSKOPE_COUNT_CEILING", "20000")
        route = _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "list", "--since", "7d", "--count", "--exact")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "20000+"
        assert route.call_count == 2
        assert "ceiling of 20,000 rows" in result.output

    @respx.mock
    def test_plain_count_raises_on_error_envelope(self, runner: CliRunner) -> None:
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"ok": 0, "message": "bad query"}))
        result = _invoke(runner, "alerts", "list", "--count")
        assert result.exit_code != 0
        assert "bad query" in (result.output + str(result.exception))
        respx.get(f"{BASE}/api/v2/events/datasearch/incident").mock(
            return_value=httpx.Response(200, json={"ok": 0, "message": "bad query"})
        )
        result = _invoke(runner, "incidents", "list", "--count")
        assert result.exit_code != 0

    @respx.mock
    def test_exact_counts_one_page_off_datasearch(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)  # not auto-quiet
        route = respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": ALERTS, "total": 5000})
        )
        result = _invoke(runner, "events", "audit", "--count", "--exact")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "5000"
        assert route.call_count == 1
        assert "datasearch endpoints only" in result.output

    @respx.mock
    def test_alerts_summary_notes_the_cap(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)
        _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "summary", "--by", "action")
        assert result.exit_code == 0, result.output
        assert "Summary covers only the first 10,000 alerts" in result.output


class TestReviewRegressions:
    """Envelope shapes, grouping and strictness cases found in review."""

    @respx.mock
    def test_rules_get_projects_the_rule_not_the_envelope(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/policy/npa/rules/42").mock(
            return_value=httpx.Response(
                200, json={"data": {"rule_id": 42, "rule_name": "Allow Web", "enabled": "1"}, "status": "success"}
            )
        )
        result = _invoke(runner, "npa", "policy", "rules", "get", "42", "--api-fields", "rule_name", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {"rule_name": "Allow Web"}
        result = _invoke(runner, "npa", "policy", "rules", "get", "42", "--fields", "rule_id", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {"rule_id": 42}

    @respx.mock
    def test_events_dict_result_and_empty_envelope_are_not_records(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/metrics/transactionevents").mock(
            return_value=httpx.Response(200, json={"ok": 1, "result": {"total_bytes": 5, "count": 3}})
        )
        result = _invoke(runner, "events", "transaction", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {"total_bytes": 5, "count": 3}
        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"ok": 1, "msg": "nothing"})
        )
        result = _invoke(runner, "events", "network", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == []

    @respx.mock
    def test_grouped_rows_keep_count_under_api_fields(self, runner: CliRunner) -> None:
        _alert_route([{"_id": {"app": "Slack"}, "count": 5}, {"_id": {"app": "Box"}, "count": 2}])
        result = _invoke(runner, "alerts", "list", "--group-by", "app", "--api-fields", "app", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"app": "Slack", "count": 5}, {"app": "Box", "count": 2}]

    @respx.mock
    def test_global_fields_warn_not_fail_while_projected(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/epdlp").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "u"}]})
        )
        result = _invoke(
            runner, "events", "epdlp", "--api-fields", "user,dlp_rule", "--fields", "user,dlp_rule", "-o", "json"
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"user": "u", "dlp_rule": None}]
        assert "--fields: 'dlp_rule' not found" in result.output

    @respx.mock
    def test_events_get_prints_no_transition_note(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/application").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "u", "app": "a"}]})
        )
        result = _invoke(
            runner, "events", "get", "--type", "application", "--user", "u", "--fields", "user", "-o", "json"
        )
        assert result.exit_code == 0, result.output
        assert "--api-fields" not in result.output
        assert json.loads(result.stdout) == [{"user": "u"}]


class TestSecondReview:
    """Findings from the second review of the branch (Q1-Q15), by number."""

    @respx.mock
    def test_q1_single_object_envelope_warns_instead_of_failing(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/infrastructure/publishers/42").mock(
            return_value=httpx.Response(
                200, json={"data": {"publisher_name": "P", "status": "connected"}, "status": "success"}
            )
        )
        result = _invoke(runner, "npa", "publishers", "get", "42", "--fields", "publisher_name", "-o", "json")
        assert result.exit_code == 0, result.output
        assert "--fields: 'publisher_name' not found" in result.output  # warned, as before the strict mode

    @respx.mock
    def test_q2_widened_name_rejected_by_api_names_the_option(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(400, json={"message": "unrecognized field usr"})
        )
        result = _invoke(runner, "events", "network", "--api-fields", "timestamp", "--where", 'usr eq "x"')
        assert result.exit_code != 0
        assert "usr was added to --api-fields" in (getattr(result.exception, "suggestion", "") or "")

    @respx.mock
    def test_q3_count_uses_envelope_total_without_a_result_list(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(return_value=httpx.Response(200, json={"ok": 1, "total": 5}))
        result = _invoke(runner, "events", "audit", "--count")
        assert result.stdout.strip() == "5", result.output

    @respx.mock
    def test_q4_where_over_a_full_page_is_a_lower_bound_despite_a_total(self, runner: CliRunner) -> None:
        _alert_route(FULL_PAGE)  # no way to know what the 40,000 uninspected rows hold
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"result": FULL_PAGE, "total": 50000}))
        result = _invoke(runner, "alerts", "list", "--count", "--where", 'action eq "block"')
        assert result.stdout.strip() == "5000+", result.output

    @respx.mock
    def test_q5_events_error_envelope_is_markup_safe(self, runner: CliRunner) -> None:
        from netskope_cli.core.exceptions import NetskopeError

        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"ok": 0, "message": "bad query near [/user]"})
        )
        result = _invoke(runner, "events", "network", "--query", "x")
        assert isinstance(result.exception, NetskopeError)
        assert "\\[/user]" in result.exception.message

    def test_q7_iso_companion_name_is_not_a_typo_in_table_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["alert_name", "timestamp_iso"]).format_output(ALERTS, fmt="table")
        assert "column left blank" in _out(capsys)[1]

    def test_q8_glob_matching_nothing_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = [{"user": "a", "host_info": None}, {"user": "b"}]
        OutputFormatter(no_color=True, fields=["user", "host_info.*"]).format_output(rows, fmt="json")
        assert "pattern 'host_info.*' matched no fields" in _flat(_out(capsys)[1])

    def test_q9_grouped_rows_warn_for_a_non_group_column(self, capsys: pytest.CaptureFixture[str]) -> None:
        grouped = [{"_id": {"app": "Box"}, "count": 3}, {"_id": {"app": "Slack"}, "count": 1}]
        OutputFormatter(no_color=True, fields=["alert_name", "app"]).format_output(grouped, fmt="json")
        out, err = _out(capsys)
        assert "'alert_name' not found" in err
        assert json.loads(out) == [{"alert_name": None, "app": "Box"}, {"alert_name": None, "app": "Slack"}]

    @respx.mock
    def test_q10_audit_count_keeps_limit_because_it_states_a_total(self, runner: CliRunner) -> None:
        route = respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": ALERTS, "total": 5000})
        )
        result = _invoke(runner, "events", "audit", "--count")
        assert _request_query(route)["limit"] == ["25"]  # rows would only be fetched to be discarded
        assert result.stdout.strip() == "5000" and "capped" not in result.output

    def test_q11_a_stated_total_is_exact_and_status_count_is_consulted_last(self) -> None:
        from netskope_cli.core.output import envelope_total

        five = [{"a": 1}] * 5
        assert is_page_capped({"result": five, "status": {"count": 5, "total": 250}}, 5) is False
        assert is_page_capped({"result": five, "total": 5}, 5) is False
        assert is_page_capped({"result": five, "status": {"count": 5}}, 5) is True
        assert is_page_capped({"result": five, "total": 250}, 5, where_active=True) is True
        assert envelope_total({"status.count": 5, "status.total": 250}) == 250
        assert envelope_total({"total": 0}) == 0
        assert envelope_total({}) is None

    @respx.mock
    def test_q12_projected_timestamp_keeps_its_iso_companion(self, runner: CliRunner) -> None:
        _alert_route()
        result = _invoke(runner, "alerts", "list", "--api-fields", "timestamp,alert_name", "-o", "json")
        assert result.exit_code == 0, result.output
        assert list(json.loads(result.stdout)[0]) == ["timestamp", "timestamp_iso", "alert_name"]

    @respx.mock
    def test_q13_exact_needs_a_window_and_does_not_page_group_by(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)  # not auto-quiet
        route = _alert_route()
        result = _invoke(runner, "alerts", "list", "--count", "--exact")
        # No --since/--end: paging the API's rolling default window would count a moving target.
        assert isinstance(result.exception, ValidationError) and route.call_count == 0
        assert "--start" in str(result.exception)
        result = _invoke(runner, "alerts", "list", "--since", "1h", "--count", "--exact")
        assert result.exit_code == 0 and result.stdout.strip() == "2", result.output
        calls_before = route.call_count
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"result": [{"_id": {"app": "Box"}, "count": 3}]})
        )
        result = _invoke(runner, "alerts", "list", "--since", "1h", "--group-by", "app", "--count", "--exact")
        assert result.stdout.strip() == "1" and route.call_count == calls_before + 1  # one page, no paging
        assert "does not page group-by results" in result.output

    @respx.mock
    def test_q15_alerts_summary_raises_on_error_envelope(self, runner: CliRunner) -> None:
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"ok": 0, "message": "Invalid query"}))
        result = _invoke(runner, "alerts", "summary", "--by", "severity")
        assert result.exit_code != 0
        assert "Invalid query" in (result.output + str(result.exception))


class TestThirdReview:
    """Findings from the third review of #19."""

    @respx.mock
    def test_f1_every_events_endpoint_counts_a_full_page(self, runner: CliRunner) -> None:
        infra = respx.get(f"{BASE}/api/v2/events/data/infrastructure").mock(
            return_value=httpx.Response(200, json={"result": FULL_PAGE})
        )
        for argv in (
            ("events", "infrastructure", "--count"),
            ("events", "list", "--type", "infrastructure", "--count"),
        ):
            result = _invoke(runner, *argv)
            assert result.exit_code == 0, result.output
            assert result.stdout.strip() == "10000+"
            assert "--exact cannot page this endpoint" in _flat(result.output)
            assert "or use --exact" not in result.output
        assert all(_request_query(infra, i)["limit"] == ["10000"] for i in range(infra.call_count))

    @respx.mock
    def test_f2_unknown_fields_warn_on_event_commands(self, runner: CliRunner) -> None:
        # Whether dlp_rule is in the window depends on which alert subtypes landed in it,
        # so a script must not exit 0 one night and 2 the next.
        _alert_route()
        result = _invoke(runner, "alerts", "list", "--fields", "alert_name,dlp_rule", "-o", "csv")
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[0] == "alert_name,dlp_rule"
        assert "--fields: 'dlp_rule' not found" in result.output
        respx.get(f"{BASE}/api/v2/events/datasearch/incident").mock(
            return_value=httpx.Response(200, json={"result": ALERTS})
        )
        result = _invoke(runner, "incidents", "list", "--fields", "dlp_rule", "-o", "json")
        assert result.exit_code == 0, result.output

    def test_f3_larger_status_count_on_a_full_page_is_the_lower_bound(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True).format_output(
            {"result": ALERTS * 5, "status": {"count": 25}}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "25+" and "capped" in err

    @respx.mock
    def test_f4_exact_sends_the_same_window_on_every_page(self, runner: CliRunner) -> None:
        def pages(request: httpx.Request) -> httpx.Response:
            offset = int(parse_qs(urlparse(str(request.url)).query)["offset"][0])
            return httpx.Response(200, json={"result": FULL_PAGE if offset == 0 else FULL_PAGE[:5]})

        route = respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(side_effect=pages)
        result = _invoke(runner, "events", "network", "--start", "24h", "--count", "--exact")
        assert result.exit_code == 0 and result.stdout.strip() == "10005", result.output
        windows = {(q["starttime"][0], q["endtime"][0]) for q in (_request_query(route, i) for i in range(2))}
        assert len(windows) == 1

    def test_f5_ignored_offset_is_an_error_not_an_exact_count(self) -> None:
        from netskope_cli.core.exceptions import NetskopeError

        class IgnoresOffset(_FakeClient):
            def request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None) -> Any:
                params = dict(params or {})
                self.calls.append(params)
                return {"result": self.rows[: params["limit"]]}  # offset never applied

        rows = [{"_id": f"r{i}", "n": i} for i in range(6)]
        with pytest.raises(NetskopeError) as exc:
            count_exact(IgnoresOffset(rows), "/x", {}, page_size=3, ceiling=1000, quiet=True)
        assert "not honouring offset" in exc.value.message and "r0" in exc.value.message
        # Rows without _id are legitimately repetitive, so there is no check; a --api-fields
        # projection is therefore widened with _id (the rows are counted, never shown).
        client = _FakeClient([{"action": "allow"}] * 7)
        assert count_exact(client, "/x", {"fields": "action"}, page_size=3, ceiling=1000, quiet=True).count == 7
        assert client.calls[0]["fields"] == "action,_id"
        count_exact(client, "/x", {"fields": "_id,action"}, page_size=3, ceiling=1000, quiet=True)
        assert client.calls[-1]["fields"] == "_id,action"

    @respx.mock
    def test_f6_widened_name_400_is_explained_on_exact_and_npa(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(400, json={"message": "unrecognized field usr"})
        )
        result = _invoke(
            runner,
            "events",
            "network",
            "-s",
            "1h",
            "--api-fields",
            "timestamp",
            "--where",
            'usr eq "x"',
            "--count",
            "--exact",
        )
        assert result.exit_code != 0
        assert "usr was added to --api-fields" in (getattr(result.exception, "suggestion", "") or "")
        respx.get(f"{BASE}/api/v2/policy/npa/rules").mock(
            return_value=httpx.Response(400, json={"message": "unknown field enabledd"})
        )
        result = _invoke(
            runner, "npa", "policy", "rules", "list", "--api-fields", "rule_name", "--where", "enabledd eq 1"
        )
        assert result.exit_code != 0
        assert "enabledd was added to --api-fields" in (getattr(result.exception, "suggestion", "") or "")

    @respx.mock
    def test_f7_machine_formats_print_a_bare_integer_for_capped_counts(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        route = _alert_route(FULL_PAGE)
        for fmt in ("json", "jsonl", "yaml", "csv"):
            result = _invoke(runner, "alerts", "list", "--count", "-o", fmt)
            assert result.exit_code == 0, result.output
            assert json.loads(result.stdout) == 10000
            assert "Count capped at the API maximum" in result.output
        result = _invoke(runner, "alerts", "list", "--count", "-o", "table")
        assert result.stdout.strip() == "10000+"
        monkeypatch.setenv("NETSKOPE_COUNT_CEILING", "20000")
        result = _invoke(runner, "alerts", "list", "--since", "7d", "--count", "--exact", "-o", "json")
        assert json.loads(result.stdout) == 20000 and "ceiling of 20,000 rows" in result.output
        assert route.call_count == 7

    def test_f8_iso_companion_in_table_output_says_why_it_is_blank(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["alert_name", "timestamp_iso"]).format_output(ALERTS, fmt="table")
        _out_, err = _out(capsys)
        assert "'timestamp_iso' is only added in json, jsonl, csv and yaml output" in _flat(err)
        assert "use 'timestamp' here" in _flat(err) and "parent is null" not in err

    def test_f9_quiet_capped_count_prints_one_notice(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, quiet=True).format_output(
            {"result": ALERTS * 5}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "10+"
        assert err.count("Count capped") == 1 and "results (capped)" not in err

    @respx.mock
    def test_f10_raw_epoch_and_limit_validation_apply_to_audit(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": [{"_internal": 1, "user": "u", "timestamp": 1784851173}]})
        )
        plain = json.loads(_invoke(runner, "events", "audit", "-o", "json").stdout)[0]
        assert "_internal" not in plain and plain["timestamp_iso"].startswith("2026-")
        raw = json.loads(_invoke(runner, "--raw", "events", "audit", "-o", "json").stdout)[0]
        assert raw["_internal"] == 1
        epoch = json.loads(_invoke(runner, "--epoch", "events", "list", "--type", "audit", "-o", "json").stdout)[0]
        assert "timestamp_iso" not in epoch
        result = _invoke(runner, "events", "audit", "--limit", "0")
        assert result.exit_code != 0 and "Invalid --limit" in (str(result.exception) + result.output)


class TestFourthReview:
    """Findings from the fourth review of #19."""

    @respx.mock
    def test_g1_a_pipe_gets_the_bare_integer_whatever_the_format(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("netskope_cli.core.output.stdout_is_tty", lambda: False)
        _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "list", "--count")  # default table format, stdout piped
        assert result.stdout.strip() == "10000"  # $(ntsk ... --count) keeps parsing
        assert "Count capped at the API maximum" in result.output  # the lower bound is still recorded
        print_exact_count(ExactCount(5, 100, 10, True), where=False, ceiling=100, quiet=True, no_color=True)
        out, err = _out(capsys)
        assert out == "5\n" and "ceiling of 100 rows" in err

    @respx.mock
    def test_g3_exact_without_a_window_is_a_validation_error(self, runner: CliRunner) -> None:
        route = respx.get(f"{BASE}/api/v2/events/datasearch/network").mock(
            return_value=httpx.Response(200, json={"result": ALERTS})
        )
        result = _invoke(runner, "events", "network", "--count", "--exact")
        assert isinstance(result.exception, ValidationError) and route.call_count == 0
        assert result.exception.exit_code == 2 and "--start" in str(result.exception)
        # incidents always resolve a window, so --exact needs nothing extra there
        respx.get(f"{BASE}/api/v2/events/datasearch/incident").mock(
            return_value=httpx.Response(200, json={"result": ALERTS})
        )
        result = _invoke(runner, "incidents", "list", "--count", "--exact")
        assert result.exit_code == 0 and result.stdout.strip() == "2", result.output

    @respx.mock
    def test_g6_single_page_notices_respect_quiet(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": ALERTS, "total": 5})
        )
        piped = _invoke(runner, "events", "audit", "--count", "--exact")  # CliRunner is not a TTY: auto-quiet
        assert "counting a single page" not in piped.output and piped.stdout.strip() == "5"
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)
        loud = _invoke(runner, "events", "audit", "--count", "--exact")
        assert "counting a single page" in loud.output
        quiet = _invoke(runner, "-q", "events", "audit", "--count", "--exact")
        assert "counting a single page" not in quiet.output
        _alert_route([{"_id": {"app": "Box"}, "count": 3}])
        quiet = _invoke(runner, "-q", "alerts", "list", "--since", "1h", "--group-by", "app", "--count", "--exact")
        assert "group-by" not in quiet.output and quiet.stdout.strip() == "1"

    @respx.mock
    def test_g7_total_is_stated_once_and_verbose_metadata_skips_ok(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"ok": 1, "message": "x", "result": ALERTS, "total": 50})
        )
        result = _invoke(runner, "events", "audit", "-o", "table")
        assert result.exit_code == 0, result.output
        assert "Showing 2 of 50 results" in result.output
        assert "total, showing" not in result.output  # the banner already says it
        assert "message=x" not in result.output and "ok=1" not in result.output

    def test_g8_status_and_count_share_one_page_rule(self) -> None:
        from netskope_cli.core.output import page_count, page_is_capped

        meta = {"status.count": 25000}
        assert page_is_capped(meta, 10000, 10000) is True
        assert page_count(meta, 10000, capped=True) == 25000  # the better lower bound
        assert page_is_capped({"total": 25000}, 10000, 10000) is False
        assert page_count({"total": 25000}, 10000, capped=False) == 25000
        assert page_count({"total": 25000}, 3, capped=True, where_active=True) == 3
        assert page_is_capped({}, 9999, 10000) is False and page_count({}, 9999, capped=False) == 9999


class TestFifthReview:
    """Findings from the fifth review of #19."""

    @respx.mock
    def test_h1_a_limit_counted_endpoint_still_reports_a_full_page_as_a_lower_bound(self, runner: CliRunner) -> None:
        """Audit counts with --limit rather than a full page, but a full page is still a lower bound.

        Both of these once printed a bare number as if it were exact: the API's
        ``total`` cannot answer a client-side ``--where`` (only the 25 rows
        fetched were examined), and an audit response without a ``total`` has
        nothing to fall back on but the row count.
        """
        rows = [{"severity_level": 1 if i < 3 else 2, "user": "u"} for i in range(25)]
        route = respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": rows, "total": 9999})
        )
        filtered = _invoke(runner, "events", "audit", "--count", "--where", "severity_level eq 1")
        assert filtered.exit_code == 0, filtered.output
        assert filtered.stdout.strip() == "3+"
        assert "--limit" in _flat(filtered.output)
        assert _request_query(route)["limit"] == ["25"]  # still no 10,000-row fetch

        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "u"} for _ in range(25)]})
        )
        no_total = _invoke(runner, "events", "audit", "--count")
        assert no_total.exit_code == 0, no_total.output
        assert no_total.stdout.strip() == "25+"

    @respx.mock
    def test_h1_a_stated_total_or_a_short_page_still_counts_exactly(self, runner: CliRunner) -> None:
        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": [{"user": "u"} for _ in range(25)], "total": 9999})
        )
        stated = _invoke(runner, "events", "audit", "--count")
        assert stated.stdout.strip() == "9999" and "+" not in stated.stdout

        respx.get(f"{BASE}/api/v2/events/data/audit").mock(
            return_value=httpx.Response(200, json={"result": [{"severity_level": 1} for _ in range(4)]})
        )
        short = _invoke(runner, "events", "audit", "--count", "--where", "severity_level eq 1")
        assert short.stdout.strip() == "4" and "+" not in short.stdout
