"""Tests for global-option hoisting and leaf-command resolution in main.py."""

from __future__ import annotations

import pytest
import typer
import typer.main

from netskope_cli.core import clickshim as click
from netskope_cli.main import _hoist_global_options, _local_option_names, _resolve_leaf_command


def hoist(*argv: str) -> list[str]:
    return _hoist_global_options(["ntsk", *argv])


class TestExistingFlagsUnchanged:
    def test_output_after_subcommand(self) -> None:
        assert hoist("alerts", "list", "-o", "json", "--limit", "5") == [
            "ntsk",
            "-o",
            "json",
            "alerts",
            "list",
            "--limit",
            "5",
        ]

    def test_output_equals_form(self) -> None:
        assert hoist("users", "list", "--output=csv") == ["ntsk", "--output=csv", "users", "list"]

    def test_bool_flags(self) -> None:
        assert hoist("users", "list", "--wide", "-q") == ["ntsk", "--wide", "-q", "users", "list"]

    def test_short_argv_untouched(self) -> None:
        assert _hoist_global_options(["ntsk"]) == ["ntsk"]

    def test_unknown_command_falls_back_to_blind_hoist(self) -> None:
        assert hoist("nonsense", "--fields", "a") == ["ntsk", "--fields", "a", "nonsense"]

    def test_help_token(self) -> None:
        assert hoist("devices", "help", "-o", "json") == ["ntsk", "-o", "json", "devices", "help"]


class TestQueryOptions:
    def test_fields_hoisted_for_command_without_local_option(self) -> None:
        assert hoist("devices", "list", "--fields", "a,b") == ["ntsk", "--fields", "a,b", "devices", "list"]
        assert hoist("users", "list", "-f", "id") == ["ntsk", "-f", "id", "users", "list"]
        assert hoist("users", "list", "--fields=id,email") == ["ntsk", "--fields=id,email", "users", "list"]

    def test_fields_is_global_even_on_events(self) -> None:
        # events/alerts/incidents no longer declare --fields; their server-side
        # projection is --api-fields, which is local and stays put.
        argv = hoist("events", "alerts", "--fields", "a,b", "-o", "json")
        assert argv == ["ntsk", "--fields", "a,b", "-o", "json", "events", "alerts"]
        argv = hoist("events", "alerts", "--api-fields", "a,b", "-o", "json")
        assert argv == ["ntsk", "-o", "json", "events", "alerts", "--api-fields", "a,b"]
        assert hoist("alerts", "list", "--api-fields=a") == ["ntsk", "alerts", "list", "--api-fields=a"]

    def test_short_f_is_global_unless_declared(self) -> None:
        assert hoist("events", "alerts", "-f", "a") == ["ntsk", "-f", "a", "events", "alerts"]
        assert hoist("atp", "scan-file", "-f", "./x") == ["ntsk", "atp", "scan-file", "-f", "./x"]

    def test_exact_is_a_global_bool_flag(self) -> None:
        assert hoist("alerts", "list", "--count", "--exact") == ["ntsk", "--exact", "alerts", "list", "--count"]

    def test_where_hoisted_and_kept_local_for_dem(self) -> None:
        assert hoist("users", "list", "--where", "a eq 1") == ["ntsk", "--where", "a eq 1", "users", "list"]
        assert hoist("dem", "metrics", "query", "--where", "[1]") == [
            "ntsk",
            "dem",
            "metrics",
            "query",
            "--where",
            "[1]",
        ]
        assert hoist("dem", "sites", "summary", "--where", "[1]") == [
            "ntsk",
            "dem",
            "sites",
            "summary",
            "--where",
            "[1]",
        ]

    def test_sort_and_list_fields(self) -> None:
        assert hoist("devices", "list", "--sort", "a:desc", "--list-fields") == [
            "ntsk",
            "--sort",
            "a:desc",
            "--list-fields",
            "devices",
            "list",
        ]

    def test_aicc_sort_by_untouched(self) -> None:
        assert hoist("aicc", "apps", "list", "--sort-by", "bytes") == [
            "ntsk",
            "aicc",
            "apps",
            "list",
            "--sort-by",
            "bytes",
        ]

    def test_local_count_stays_local(self) -> None:
        # policy url-list list declares --count itself and ORs it with state.count
        assert hoist("policy", "url-list", "list", "--count") == ["ntsk", "policy", "url-list", "list", "--count"]

    def test_global_before_subcommand_still_resolves_leaf(self) -> None:
        # --fields consumes its value while walking so "a,b" is not mistaken for a command
        assert hoist("--fields", "a,b", "devices", "list", "-o", "json") == [
            "ntsk",
            "--fields",
            "a,b",
            "-o",
            "json",
            "devices",
            "list",
        ]


def _make_group() -> click.Group:
    root = typer.Typer(add_completion=False)
    sub = typer.Typer()

    @sub.command("leaf")
    def leaf(  # pragma: no cover - never invoked
        fields: str = typer.Option(None, "--fields"),
        flag: bool = typer.Option(False, "--flag"),
        limit: int = typer.Option(None, "--limit"),
    ) -> None:
        pass

    @root.command("plain")
    def plain() -> None:  # pragma: no cover - never invoked
        pass

    root.add_typer(sub, name="sub")
    group = typer.main.get_command(root)
    assert isinstance(group, click.Group)
    return group


class TestResolveLeaf:
    def test_real_app_resolves_nested_leaf(self) -> None:
        leaf = _resolve_leaf_command(["ntsk", "-o", "json", "events", "alerts", "--limit", "5"])
        assert leaf is not None
        assert leaf.name == "alerts"
        assert {"--api-fields", "--query"} <= _local_option_names(leaf)
        assert not {"--fields", "-f"} & _local_option_names(leaf)

    def test_real_app_group_only_returns_none(self) -> None:
        assert _resolve_leaf_command(["ntsk", "devices"]) is None
        assert _resolve_leaf_command(["ntsk", "bogus", "list"]) is None
        assert _resolve_leaf_command(["ntsk"]) is None

    def test_real_app_stops_at_leaf_before_args(self) -> None:
        leaf = _resolve_leaf_command(["ntsk", "devices", "list", "--fields", "hostname", "--limit", "3"])
        assert leaf is not None and leaf.name == "list"
        assert "--fields" not in _local_option_names(leaf)

    def test_local_option_names_synthetic(self) -> None:
        root = _make_group()
        ctx = click.Context(root, info_name="root")
        sub = root.get_command(ctx, "sub")
        assert isinstance(sub, click.Group)
        leaf = sub.get_command(click.Context(sub, parent=ctx, info_name="sub"), "leaf")
        assert _local_option_names(leaf) == {"--fields", "--flag", "--limit"}
        assert _local_option_names(None) == set()

    @pytest.mark.parametrize(
        "argv", [["ntsk", "--where", "x eq", "users", "list"], ["ntsk", "--profile", "p", "users", "list"]]
    )
    def test_value_flags_skipped_while_walking(self, argv: list[str]) -> None:
        leaf = _resolve_leaf_command(argv)
        assert leaf is not None and leaf.name == "list"
