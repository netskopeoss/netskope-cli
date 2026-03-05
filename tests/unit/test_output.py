"""Tests for netskope_cli.core.output."""

from __future__ import annotations

import json
import sys

import pytest

from netskope_cli.core.output import (
    OutputFormatter,
    echo_error,
    echo_info,
    echo_success,
    echo_warning,
)

# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_dict_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"name": "test", "value": 42}, fmt="json")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"name": "test", "value": 42}

    def test_list_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output([{"id": 1}, {"id": 2}], fmt="json")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1

    def test_json_pretty_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"a": 1}, fmt="json")
        captured = capsys.readouterr()
        assert "\n" in captured.out  # pretty-printed has newlines


# ---------------------------------------------------------------------------
# CSV format
# ---------------------------------------------------------------------------


class TestCsvFormat:
    def test_csv_single_row(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"name": "alice", "age": "30"}, fmt="csv")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "name" in lines[0]
        assert "alice" in lines[1]

    def test_csv_list_of_dicts(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        data = [{"x": "1", "y": "2"}, {"x": "3", "y": "4"}]
        fmt.format_output(data, fmt="csv")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_csv_empty_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output([], fmt="csv")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_csv_ragged_dicts(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        data = [{"a": "1"}, {"a": "2", "b": "3"}]
        fmt.format_output(data, fmt="csv")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        header = lines[0]
        assert "a" in header
        assert "b" in header


# ---------------------------------------------------------------------------
# Table format
# ---------------------------------------------------------------------------


class TestTableFormat:
    def test_table_list_of_dicts(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter(no_color=True)
        data = [{"name": "alice", "role": "admin"}, {"name": "bob", "role": "user"}]
        fmt.format_output(data, fmt="table")
        captured = capsys.readouterr()
        assert "alice" in captured.out
        assert "bob" in captured.out

    def test_table_single_flat_dict_becomes_kv(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter(no_color=True)
        data = {"key1": "val1", "key2": "val2"}
        fmt.format_output(data, fmt="table")
        captured = capsys.readouterr()
        assert "key1" in captured.out
        assert "val1" in captured.out

    def test_table_empty_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter(no_color=True)
        fmt.format_output([], fmt="table")
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------


class TestFieldSelection:
    def test_dict_field_selection(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"a": 1, "b": 2, "c": 3}, fmt="json", fields=["a", "c"])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"a": 1, "c": 3}

    def test_list_field_selection(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        fmt.format_output(data, fmt="json", fields=["a"])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == [{"a": 1}, {"a": 3}]

    def test_no_fields_returns_all(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"a": 1, "b": 2}, fmt="json", fields=None)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"a": 1, "b": 2}

    def test_non_dict_data_unaffected(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output("plain string", fmt="json", fields=["x"])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == "plain string"


# ---------------------------------------------------------------------------
# Auto-detect format
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def test_auto_detect_non_tty_returns_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert OutputFormatter._auto_detect_format() == "json"

    def test_auto_detect_tty_returns_human(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert OutputFormatter._auto_detect_format() == "human"


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------


class TestUnsupportedFormat:
    def test_raises_on_bad_format(self) -> None:
        fmt = OutputFormatter()
        with pytest.raises(ValueError, match="Unsupported format"):
            fmt.format_output({"a": 1}, fmt="xml")


# ---------------------------------------------------------------------------
# Echo helpers
# ---------------------------------------------------------------------------


class TestEchoHelpers:
    def test_echo_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        echo_success("it worked", no_color=True)
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.err
        assert "it worked" in captured.err

    def test_echo_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        echo_error("something broke", no_color=True)
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "something broke" in captured.err

    def test_echo_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        echo_warning("careful now", no_color=True)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "careful now" in captured.err

    def test_echo_info(self, capsys: pytest.CaptureFixture[str]) -> None:
        echo_info("fyi", no_color=True)
        captured = capsys.readouterr()
        assert "INFO" in captured.err
        assert "fyi" in captured.err


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_truncate_short_value(self) -> None:
        fmt = OutputFormatter(max_col_width=10)
        assert fmt._truncate("short") == "short"

    def test_truncate_long_value(self) -> None:
        fmt = OutputFormatter(max_col_width=10)
        result = fmt._truncate("a" * 20)
        assert len(result) == 10
        assert result.endswith("\u2026")

    def test_truncate_disabled_with_zero(self) -> None:
        fmt = OutputFormatter(max_col_width=0)
        assert fmt._truncate("a" * 200) == "a" * 200


# ---------------------------------------------------------------------------
# JSONL format
# ---------------------------------------------------------------------------


class TestJsonlFormat:
    def test_jsonl_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output([{"a": 1}, {"b": 2}], fmt="jsonl")
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_jsonl_single_dict(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"a": 1}, fmt="jsonl")
        captured = capsys.readouterr()
        assert json.loads(captured.out.strip()) == {"a": 1}


# ---------------------------------------------------------------------------
# YAML format
# ---------------------------------------------------------------------------


class TestCountOnly:
    def test_count_only_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output([{"id": 1}, {"id": 2}, {"id": 3}], fmt="json", count_only=True)
        captured = capsys.readouterr()
        assert captured.out.strip() == "3"

    def test_count_only_with_metadata_total(self, capsys: pytest.CaptureFixture[str]) -> None:
        data = {"result": [{"id": 1}], "total": 42}
        fmt = OutputFormatter()
        fmt.format_output(data, fmt="json", count_only=True)
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

    def test_default_count_only_on_formatter(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter(count_only=True)
        fmt.format_output([{"id": 1}, {"id": 2}], fmt="json")
        captured = capsys.readouterr()
        assert captured.out.strip() == "2"

    def test_count_only_single_item(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"id": 1}, fmt="json", count_only=True, unwrap=False)
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"


class TestYamlFormat:
    def test_yaml_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        fmt = OutputFormatter()
        fmt.format_output({"name": "test", "value": 42}, fmt="yaml")
        captured = capsys.readouterr()
        assert "name: test" in captured.out
        assert "value: 42" in captured.out
