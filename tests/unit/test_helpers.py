"""Tests for netskope_cli.utils.helpers."""

from __future__ import annotations

import time

import pytest

from netskope_cli.utils.helpers import (
    format_timestamp,
    parse_key_value_args,
    truncate_string,
    validate_time_range,
)

# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------


class TestFormatTimestamp:
    def test_epoch_zero(self) -> None:
        assert format_timestamp(0) == "1970-01-01 00:00:00 UTC"

    def test_known_timestamp(self) -> None:
        # 2024-01-01 00:00:00 UTC = 1704067200
        assert format_timestamp(1704067200) == "2024-01-01 00:00:00 UTC"

    def test_float_timestamp(self) -> None:
        result = format_timestamp(1704067200.999)
        assert result == "2024-01-01 00:00:00 UTC"  # truncated to seconds

    def test_negative_timestamp(self) -> None:
        # Before epoch should still work
        result = format_timestamp(-86400)
        assert "1969" in result


# ---------------------------------------------------------------------------
# truncate_string
# ---------------------------------------------------------------------------


class TestTruncateString:
    def test_short_string_unchanged(self) -> None:
        assert truncate_string("hello", max_len=80) == "hello"

    def test_exact_length_unchanged(self) -> None:
        s = "a" * 80
        assert truncate_string(s, max_len=80) == s

    def test_long_string_truncated(self) -> None:
        s = "a" * 100
        result = truncate_string(s, max_len=80)
        assert len(result) == 80
        assert result.endswith("\u2026")

    def test_max_len_1(self) -> None:
        result = truncate_string("hello", max_len=1)
        assert result == "\u2026"

    def test_empty_string(self) -> None:
        assert truncate_string("", max_len=80) == ""

    def test_default_max_len(self) -> None:
        s = "x" * 81
        result = truncate_string(s)
        assert len(result) == 80


# ---------------------------------------------------------------------------
# parse_key_value_args
# ---------------------------------------------------------------------------


class TestParseKeyValueArgs:
    def test_single_pair(self) -> None:
        assert parse_key_value_args(["name=alice"]) == {"name": "alice"}

    def test_multiple_pairs(self) -> None:
        result = parse_key_value_args(["a=1", "b=2", "c=3"])
        assert result == {"a": "1", "b": "2", "c": "3"}

    def test_value_with_equals(self) -> None:
        # partition only splits on first =
        result = parse_key_value_args(["expr=a=b"])
        assert result == {"expr": "a=b"}

    def test_empty_value(self) -> None:
        result = parse_key_value_args(["key="])
        assert result == {"key": ""}

    def test_whitespace_stripped(self) -> None:
        result = parse_key_value_args(["  key  =  value  "])
        assert result == {"key": "value"}

    def test_empty_list(self) -> None:
        assert parse_key_value_args([]) == {}

    def test_no_equals_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid key=value argument"):
            parse_key_value_args(["noequals"])

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty key"):
            parse_key_value_args(["=value"])


# ---------------------------------------------------------------------------
# validate_time_range
# ---------------------------------------------------------------------------


class TestValidateTimeRange:
    def test_absolute_timestamps(self) -> None:
        start, end = validate_time_range(1000, 2000)
        assert start == 1000
        assert end == 2000

    def test_string_numeric_timestamps(self) -> None:
        start, end = validate_time_range("1000", "2000")
        assert start == 1000
        assert end == 2000

    def test_relative_time_1h(self) -> None:
        now = time.time()
        start, end = validate_time_range("1h")
        # start should be approximately now - 3600
        assert abs(start - (now - 3600)) < 2
        assert abs(end - now) < 2

    def test_relative_time_7d(self) -> None:
        now = time.time()
        start, end = validate_time_range("7d")
        assert abs(start - (now - 7 * 86400)) < 2
        assert abs(end - now) < 2

    def test_relative_time_30m(self) -> None:
        now = time.time()
        start, end = validate_time_range("30m")
        assert abs(start - (now - 30 * 60)) < 2

    def test_relative_time_seconds(self) -> None:
        now = time.time()
        start, end = validate_time_range("120s")
        assert abs(start - (now - 120)) < 2

    def test_relative_time_weeks(self) -> None:
        now = time.time()
        start, end = validate_time_range("2w")
        assert abs(start - (now - 2 * 604800)) < 2

    def test_end_defaults_to_now(self) -> None:
        now = time.time()
        _, end = validate_time_range(0)
        assert abs(end - now) < 2

    def test_explicit_end(self) -> None:
        start, end = validate_time_range(100, 200)
        assert start == 100
        assert end == 200

    def test_start_after_end_raises(self) -> None:
        with pytest.raises(ValueError, match="Start time.*after end time"):
            validate_time_range(2000, 1000)

    def test_invalid_relative_time_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse time value"):
            validate_time_range("abc")

    def test_float_timestamps(self) -> None:
        start, end = validate_time_range(1000.5, 2000.9)
        assert start == 1000
        assert end == 2000

    def test_case_insensitive_units(self) -> None:
        now = time.time()
        start, _ = validate_time_range("1H")
        assert abs(start - (now - 3600)) < 2
