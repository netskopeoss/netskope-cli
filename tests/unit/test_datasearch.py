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
from netskope_cli.core.output import OutputFormatter, UnknownFieldError
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


def _out(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    captured = capsys.readouterr()
    return captured.out, captured.err


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


class TestFormatterStrictAndCapped:
    def test_unknown_field_raises_exit_2(self) -> None:
        with pytest.raises(UnknownFieldError) as exc:
            OutputFormatter(no_color=True, fields=["nope", "alert_name"]).format_output(ALERTS, fmt="json")
        assert exc.value.exit_code == 2
        assert "'nope' not found in any record" in exc.value.message
        assert "--lenient" in (exc.value.suggestion or "")

    def test_server_side_projection_missing_field_warns_under_api_fields_label(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        OutputFormatter(no_color=True).format_output(ALERTS, fmt="json", fields=["timestamp", "qdomainn"])
        out, err = _out(capsys)
        assert "--api-fields: 'qdomainn' not found in any record" in err
        assert "qdomain" in err  # close match suggested
        assert json.loads(out)[0] == {"timestamp": 1784851173, "qdomainn": None}

    def test_lenient_warns_and_prints_nulls(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, lenient=True, fields=["nope", "alert_name"]).format_output(ALERTS, fmt="json")
        out, err = _out(capsys)
        assert "'nope' not found in any record" in err
        assert json.loads(out)[0] == {"nope": None, "alert_name": "Block-Malicious-Domains"}

    def test_capped_count_and_banner(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True).format_output(
            {"result": ALERTS * 5, "status": {"count": 10}}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "10+"
        assert "10+ results (capped)" in err
        assert "Count capped at the API maximum of 10 rows" in err and "--exact" in err

    def test_capped_with_where_counts_filtered_rows(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, where='action eq "block"').format_output(
            {"result": ALERTS * 5}, fmt="table", count_only=True, capped_at=10
        )
        out, err = _out(capsys)
        assert out.strip() == "5+"
        assert "5 of 10 results matched --where" in err

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


def _invoke(runner: CliRunner, *argv: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, _hoist_global_options(["ntsk", *argv])[1:])


def _alert_route(rows: list[dict[str, Any]] | None = None) -> respx.Route:
    return respx.get(ALERT_URL).mock(
        return_value=httpx.Response(200, json={"result": rows if rows is not None else ALERTS})
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

    def test_unknown_field_exits_2_naming_it(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            sys, "argv", ["ntsk", "alerts", "list", "--limit", "2", "--fields", "nope,alert_name", "-o", "csv"]
        )
        with respx.mock:
            _alert_route()
            with pytest.raises(SystemExit) as exc:
                cli()
        assert exc.value.code == 2
        out, err = _out(capsys)
        assert out == ""
        assert "nope" in err and "--lenient" in err

    def test_lenient_downgrades_to_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            sys, "argv", ["ntsk", "alerts", "list", "--fields", "nope,alert_name", "-o", "csv", "--lenient"]
        )
        with respx.mock:
            _alert_route()
            cli()  # exit code 0: standalone_mode=False returns instead of raising SystemExit
        out, err = _out(capsys)
        assert out.splitlines()[0] == "nope,alert_name"
        assert out.splitlines()[1] == ",Block-Malicious-Domains"
        assert "'nope' not found" in err

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
        assert json.loads(result.stdout) == [{"timestamp": 1784851173, "qdomain": "bad.example"}]

    @respx.mock
    def test_projected_field_absent_from_response_does_not_fail(self, runner: CliRunner) -> None:
        # Sparse event schemas: the API accepts the name but no row in the window has it.
        _alert_route([{"timestamp": 1784851173, "alert_name": "DLP thing"}])
        result = _invoke(runner, "alerts", "list", "--api-fields", "timestamp,qdomain", "-o", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"timestamp": 1784851173, "qdomain": None}]
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
        assert json.loads(result.stdout) == [{"timestamp": 1784851173, "qdomain": "bad.example"}]
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
        assert "10,000+ results (capped)" in result.output
        assert "Count capped at the API maximum of 10,000 rows" in result.output
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
        result = _invoke(runner, "events", "network", "--count", "--exact")
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
        result = _invoke(runner, "alerts", "list", "--count", "--exact")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "20000+"
        assert route.call_count == 2
        assert "ceiling of 20,000 rows" in result.output

    @respx.mock
    def test_alerts_summary_notes_the_cap(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)
        _alert_route(FULL_PAGE)
        result = _invoke(runner, "alerts", "summary", "--by", "action")
        assert result.exit_code == 0, result.output
        assert "Summary covers only the first 10,000 alerts" in result.output
