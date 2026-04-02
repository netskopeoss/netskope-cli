"""Tests for the command-tree discovery module."""

from __future__ import annotations

import json

import click

from netskope_cli.commands.tree_cmd import _arg_signature, _walk_json


def _make_group() -> click.Group:
    """Build a small synthetic Click group for testing."""
    grp = click.Group("root")

    @grp.command("simple")
    def simple_cmd():
        """A simple command."""

    @grp.command("with-arg")
    @click.argument("resource_type")
    def arg_cmd(resource_type):
        """Takes a positional arg."""

    @grp.command("hidden", hidden=True)
    def hidden_cmd():
        """Should be skipped."""

    sub = click.Group("sub", help="A subgroup.")

    @sub.command("nested")
    @click.option("--limit", type=int, help="Max results.")
    def nested_cmd(limit):
        """Nested command with option."""

    grp.add_command(sub)
    return grp


class TestArgSignature:
    def test_no_args(self) -> None:
        cmd = click.Command("test", callback=lambda: None)
        assert _arg_signature(cmd) == ""

    def test_single_arg(self) -> None:
        cmd = click.Command("test", params=[click.Argument(["resource_type"])], callback=lambda x: None)
        assert _arg_signature(cmd) == "<RESOURCE_TYPE>"

    def test_multiple_args(self) -> None:
        cmd = click.Command(
            "test",
            params=[click.Argument(["src"]), click.Argument(["dst"])],
            callback=lambda x, y: None,
        )
        assert _arg_signature(cmd) == "<SRC> <DST>"


class TestWalkJson:
    def test_structure(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_json(grp, ctx)

        names = [e["name"] for e in result]
        assert "simple" in names
        assert "with-arg" in names
        assert "sub" in names
        assert "hidden" not in names

    def test_args_included(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_json(grp, ctx)

        arg_cmd = next(e for e in result if e["name"] == "with-arg")
        assert "args" in arg_cmd
        assert arg_cmd["args"][0]["name"].lower() == "resource_type"

    def test_options_included(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_json(grp, ctx)

        sub = next(e for e in result if e["name"] == "sub")
        assert "subcommands" in sub
        nested = sub["subcommands"][0]
        assert nested["name"] == "nested"
        assert any(o["name"] == "--limit" for o in nested["options"])

    def test_json_serialisable(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_json(grp, ctx)
        # Must not raise
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        assert isinstance(parsed, list)
