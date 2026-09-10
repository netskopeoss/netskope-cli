"""Formatter and end-to-end tests for the global --fields / --list-fields / --where / --sort options."""

from __future__ import annotations

import json
import sys

import httpx
import pytest
import respx
from typer.testing import CliRunner

from netskope_cli.core.output import OutputFormatter, build_formatter
from netskope_cli.main import State, _hoist_global_options, app, cli

BASE = "https://test.goskope.com"

DEVICES = [
    {
        "_id": "1",
        "hostname": "LAPTOP-1",
        "host_info": {"os": "Windows", "os_version": "11"},
        "epdlp": {"criticalErrorsCount": 2},
        "last_event_timestamp": 1756000001,
        "_internal": "x",
    },
    {
        "_id": "2",
        "hostname": "mac-2",
        "host_info": {"os": "macOS", "os_version": "14"},
        "epdlp": {"criticalErrorsCount": 0},
        "last_event_timestamp": 1755000000,
    },
    {"_id": "3", "hostname": "linux-3", "host_info": {"os": "Linux"}, "last_event_timestamp": 1754000000},
]


def _out(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    captured = capsys.readouterr()
    return captured.out, captured.err


# ---------------------------------------------------------------------------
# OutputFormatter behaviour
# ---------------------------------------------------------------------------


class TestFormatterFields:
    def test_dotted_paths_request_order_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(fields=["host_info.os", "hostname"]).format_output(DEVICES, fmt="json")
        out, _ = _out(capsys)
        rows = json.loads(out)
        assert list(rows[0].keys()) == ["host_info.os", "hostname"]
        assert rows[0] == {"host_info.os": "Windows", "hostname": "LAPTOP-1"}

    def test_missing_is_null_in_json_and_blank_in_csv(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(fields=["hostname", "epdlp.criticalErrorsCount"]).format_output(DEVICES, fmt="json")
        out, _ = _out(capsys)
        assert json.loads(out)[2]["epdlp.criticalErrorsCount"] is None
        OutputFormatter(fields=["hostname", "epdlp.criticalErrorsCount"]).format_output(DEVICES, fmt="csv")
        out, _ = _out(capsys)
        assert out.splitlines()[0] == "hostname,epdlp.criticalErrorsCount"
        assert out.splitlines()[3] == "linux-3,"

    def test_glob_expansion_table(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["hostname", "host_info.*"]).format_output(DEVICES, fmt="table")
        out, _ = _out(capsys)
        assert "host_info.os_version" in out and "host_info.os" in out

    def test_explicit_param_beats_global(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(fields=["hostname"]).format_output(DEVICES, fmt="json", fields=["_id"])
        out, _ = _out(capsys)
        assert json.loads(out)[0] == {"_id": "1"}

    def test_global_beats_default_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(fields=["hostname"]).format_output(DEVICES, fmt="csv", default_fields=["_id"])
        out, _ = _out(capsys)
        assert out.splitlines()[0] == "hostname"

    def test_unknown_field_warns_with_suggestion(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, fields=["hostnme", "nothing.*"]).format_output(DEVICES, fmt="json")
        out, err = _out(capsys)
        assert "'hostnme' not found in any record" in err
        assert "hostname" in err
        assert "pattern 'nothing.*' matched no fields" in err
        assert "--list-fields" in err
        assert json.loads(out)[0] == {"hostnme": None}

    def test_default_fields_do_not_warn(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True).format_output(DEVICES, fmt="csv", default_fields=["nope"])
        out, err = _out(capsys)
        assert "not found" not in err
        # all-empty fallback keeps the full rows
        assert "hostname" in out.splitlines()[0]

    def test_legacy_apply_field_selection_shim(self) -> None:
        assert OutputFormatter._apply_field_selection({"a": 1, "b": 2}, ["b"]) == {"b": 2}
        assert OutputFormatter._apply_field_selection([{"a": 1}], None) == [{"a": 1}]

    def test_explicit_fields_never_trimmed_by_wide_logic(self, capsys: pytest.CaptureFixture[str]) -> None:
        wide = [{f"c{i}": i for i in range(15)}]
        OutputFormatter(no_color=True, fields=[f"c{i}" for i in range(15)]).format_output(wide, fmt="table")
        out, err = _out(capsys)
        assert "showing" not in err
        header = out.splitlines()[1]
        assert header.count("\u2503") == 16  # 15 columns rendered, none trimmed


class TestFormatterWhereSortCount:
    def test_where_filters_and_reports(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(
            no_color=True, where='host_info.os like "win*" or epdlp.criticalErrorsCount eq 0'
        ).format_output(DEVICES, fmt="csv")
        out, err = _out(capsys)
        assert len(out.splitlines()) == 3  # header + 2 rows
        assert "2 of 3 results matched --where" in err

    def test_where_count_ignores_envelope_total(self, capsys: pytest.CaptureFixture[str]) -> None:
        envelope = {"total": 999, "result": DEVICES}
        OutputFormatter(where='host_info.os eq "linux"', count_only=True).format_output(envelope, fmt="json")
        out, _ = _out(capsys)
        assert out.strip() == "1"

    def test_where_zero_matches_hint_and_json_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, where='hostname eq "zzz"').format_output(DEVICES, fmt="json")
        out, err = _out(capsys)
        assert json.loads(out) == []
        assert "--where matched 0 of 3 records" in err
        assert "--list-fields" in err

    def test_where_unknown_path_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, where='host.os eq "x"').format_output(DEVICES, fmt="json")
        _, err = _out(capsys)
        assert "'host.os' is not present in any record" in err
        assert "host_info.os" in err

    def test_where_on_single_dict(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(where="a eq 1").format_output({"a": 1}, fmt="json", unwrap=False)
        out, _ = _out(capsys)
        assert json.loads(out) == {"a": 1}

    def test_sort_desc_and_unknown_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, sort="last_event_timestamp:desc", fields=["hostname"]).format_output(
            DEVICES, fmt="json"
        )
        out, _ = _out(capsys)
        assert [r["hostname"] for r in json.loads(out)] == ["LAPTOP-1", "mac-2", "linux-3"]
        OutputFormatter(no_color=True, sort="host_info.os,nope").format_output(DEVICES, fmt="json")
        out, err = _out(capsys)
        assert [r["hostname"] for r in json.loads(out)] == ["linux-3", "mac-2", "LAPTOP-1"]
        assert "--sort: 'nope' not found" in err

    def test_grouped_results_still_flatten(self, capsys: pytest.CaptureFixture[str]) -> None:
        grouped = [{"_id": {"alert_type": "DLP"}, "count": 5}, {"_id": {"alert_type": "Malware"}, "count": 1}]
        OutputFormatter(where="count gt 2").format_output(grouped, fmt="json")
        out, _ = _out(capsys)
        assert json.loads(out) == [{"alert_type": "DLP", "count": 5}]


class TestListFields:
    def test_table_shape_and_footer(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, list_fields=True).format_output(
            DEVICES, fmt="table", default_fields=["hostname"], title="Devices"
        )
        out, err = _out(capsys)
        assert "Fields in: Devices" in out
        assert "host_info.os_version" in out
        assert "epdlp.criticalErrorsCount" in out
        assert "_internal" not in out  # stripped unless --raw
        assert "67%" in out  # epdlp present in 2 of 3
        assert "fields across 3 records" in err
        assert "--fields" in err and "--where" in err and "--sort" in err

    def test_raw_keeps_internal(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, list_fields=True).format_output(DEVICES, fmt="table", strip_internal=False)
        out, _ = _out(capsys)
        assert "_internal" in out

    def test_json_shape(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(list_fields=True).format_output(DEVICES, fmt="json", default_fields=["hostname"])
        out, _ = _out(capsys)
        rows = json.loads(out)
        host = next(r for r in rows if r["field"] == "hostname")
        assert host == {
            "field": "hostname",
            "type": "str",
            "present_pct": 100,
            "sample": "LAPTOP-1",
            "in_default": True,
        }
        assert set(rows[0].keys()) == {"field", "type", "present_pct", "sample", "in_default"}

    def test_where_applies_before_list_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(list_fields=True, where='host_info.os eq "linux"').format_output(DEVICES, fmt="json")
        out, _ = _out(capsys)
        assert all(r["present_pct"] == 100 for r in json.loads(out))

    def test_empty_result_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(no_color=True, list_fields=True).format_output([], fmt="table")
        _, err = _out(capsys)
        assert "no fields to list" in err
        OutputFormatter(list_fields=True).format_output([], fmt="json")
        out, _ = _out(capsys)
        assert json.loads(out) == []

    def test_count_wins_over_list_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter(list_fields=True, count_only=True).format_output(DEVICES, fmt="json")
        out, _ = _out(capsys)
        assert out.strip() == "3"


class TestWideHint:
    def test_hint_names_list_fields_and_draws_from_hidden_columns(self, capsys: pytest.CaptureFixture[str]) -> None:
        row = {f"col{i}": i for i in range(12)}
        row["zz_hostname"] = "h"  # sorted last, would be hidden
        OutputFormatter(no_color=True).format_output([row], fmt="table")
        _, err = _out(capsys)
        assert "showing 10 of 13 columns" in err
        assert "--list-fields" in err and "-W" in err
        assert "--fields zz_hostname" in err


class TestFactory:
    def test_build_formatter_reads_state(self) -> None:
        class Ctx:
            obj = State(fields=["a"], where="x eq 1", sort="a:desc", list_fields=True, quiet=True, wide=True)

        fmt = build_formatter(Ctx())
        assert fmt._global_fields == ["a"]
        assert fmt._where is not None and fmt._sort == [("a", True)] and fmt._list_fields and fmt._quiet
        assert build_formatter(object())._global_fields is None


# ---------------------------------------------------------------------------
# End-to-end through the CLI (hoisting + State + formatter)
# ---------------------------------------------------------------------------

USERS = {
    "Resources": [
        {"id": "u2", "userName": "bob", "email": "bob@x.com", "active": False, "parentGroups": ["g1"]},
        {"id": "u1", "userName": "alice", "email": "alice@x.com", "active": True, "parentGroups": []},
    ],
    "totalResults": 2,
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("NETSKOPE_TENANT", "test.goskope.com")
    monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken123")
    monkeypatch.setenv("XDG_CONFIG_HOME", f"{tmp_path}/config")
    monkeypatch.setenv("XDG_DATA_HOME", f"{tmp_path}/data")


def _invoke_hoisted(runner: CliRunner, *argv: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, _hoist_global_options(["ntsk", *argv])[1:])


class TestEndToEnd:
    @respx.mock
    def test_users_list_fields_where_sort(self, runner: CliRunner) -> None:
        respx.post(f"{BASE}/api/v2/users/getusers").mock(return_value=httpx.Response(200, json=USERS))
        result = _invoke_hoisted(
            runner, "users", "list", "-o", "json", "--fields", "userName,email", "--where", "active eq true"
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == [{"userName": "alice", "email": "alice@x.com"}]

        result = _invoke_hoisted(runner, "users", "list", "-o", "json", "--sort", "userName", "--fields", "id")
        assert json.loads(result.stdout) == [{"id": "u1"}, {"id": "u2"}]

    @respx.mock
    def test_users_list_fields_json(self, runner: CliRunner) -> None:
        respx.post(f"{BASE}/api/v2/users/getusers").mock(return_value=httpx.Response(200, json=USERS))
        result = _invoke_hoisted(runner, "users", "list", "--list-fields", "-o", "json")
        assert result.exit_code == 0, result.output
        fields = {r["field"]: r for r in json.loads(result.stdout)}
        assert fields["parentGroups"]["type"] in ("list[str]|list", "list|list[str]")
        assert fields["active"]["present_pct"] == 100

    @respx.mock
    def test_users_where_count(self, runner: CliRunner) -> None:
        respx.post(f"{BASE}/api/v2/users/getusers").mock(return_value=httpx.Response(200, json=USERS))
        result = _invoke_hoisted(runner, "users", "list", "--where", 'userName like "*ali*"', "--count")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "1"

    @respx.mock
    def test_events_api_fields_go_server_side_and_fields_stay_client_side(self, runner: CliRunner) -> None:
        route = respx.get(f"{BASE}/api/v2/events/datasearch/alert").mock(
            return_value=httpx.Response(200, json={"ok": 1, "result": [{"alert_name": "x", "severity": "high"}]})
        )
        result = _invoke_hoisted(runner, "events", "alerts", "--api-fields", "alert_name,severity", "-o", "json")
        assert result.exit_code == 0, result.output
        url = str(route.calls[0].request.url)
        assert "fields=alert_name%2Cseverity" in url or "fields=alert_name,severity" in url

        result = _invoke_hoisted(runner, "events", "alerts", "--fields", "severity", "-o", "json")
        assert result.exit_code == 0, result.output
        assert "fields=" not in str(route.calls[1].request.url)
        assert json.loads(result.stdout) == [{"severity": "high"}]

    def test_where_syntax_error_exits_2_before_any_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["ntsk", "users", "list", "--where", "userName eq"])
        with respx.mock(assert_all_called=False) as mock:
            mock.post(f"{BASE}/api/v2/users/getusers").mock(return_value=httpx.Response(200, json=USERS))
            with pytest.raises(SystemExit) as exc:
                cli()
            assert exc.value.code == 2
            assert not mock.calls

    def test_unknown_option_hint(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(sys, "argv", ["ntsk", "users", "list", "--field", "id"])
        with pytest.raises(SystemExit) as exc:
            cli()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "Did you mean --fields?" in err
        assert "docs fields" in err

    def test_where_client_side_note_on_query_commands(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["ntsk", "--where", "a eq 1", "events", "alerts"])
        monkeypatch.setattr("netskope_cli.main._stdout_is_tty", lambda: True)
        with respx.mock:
            respx.get(f"{BASE}/api/v2/events/datasearch/alert").mock(
                return_value=httpx.Response(200, json={"ok": 1, "result": []})
            )
            result = runner.invoke(app, ["--where", "a eq 1", "events", "alerts"])
        assert "filters client-side" in result.output
