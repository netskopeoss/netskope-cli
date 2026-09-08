"""Tests for the command-tree discovery module."""

from __future__ import annotations

import json

import typer
import typer.main
from typer.core import TyperCommand

from netskope_cli.commands.tree_cmd import _WRITE_COMMAND_NAMES, _arg_signature, _walk_flat, _walk_json
from netskope_cli.core import clickshim as click


def _make_group() -> click.Group:
    """Build a small synthetic command tree the way the real CLI does: from Typer apps."""
    root = typer.Typer(add_completion=False)

    @root.command("simple")
    def simple_cmd() -> None:
        """A simple command."""

    @root.command("with-arg")
    def arg_cmd(resource_type: str) -> None:
        """Takes a positional arg."""

    @root.command("hidden", hidden=True)
    def hidden_cmd() -> None:
        """Should be skipped."""

    @root.command("delete")
    def delete_cmd(resource_id: str, yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation.")) -> None:
        """Delete a resource."""

    sub = typer.Typer(help="A subgroup.")

    @sub.command("nested")
    def nested_cmd(limit: int = typer.Option(None, "--limit", help="Max results.")) -> None:
        """Nested command with option."""

    root.add_typer(sub, name="sub")
    group = typer.main.get_command(root)
    assert isinstance(group, click.Group)
    return group


class TestArgSignature:
    def test_no_args(self) -> None:
        cmd = TyperCommand("test", callback=lambda: None)
        assert _arg_signature(cmd) == ""

    def test_single_arg(self) -> None:
        cmd = TyperCommand("test", params=[click.Argument(param_decls=["resource_type"])], callback=lambda x: None)
        assert _arg_signature(cmd) == "<RESOURCE_TYPE>"

    def test_multiple_args(self) -> None:
        cmd = TyperCommand(
            "test",
            params=[click.Argument(param_decls=["src"]), click.Argument(param_decls=["dst"])],
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


class TestWalkFlat:
    def test_leaf_commands_only(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_flat(grp, ctx, prefix="ntsk ")
        commands = [r[0] for r in result]
        # "sub" is a group — should not appear as a leaf
        assert not any(c.endswith(" sub") for c in commands)
        # "nested" (under sub) should appear
        assert any("nested" in c for c in commands)

    def test_write_classification(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_flat(grp, ctx, prefix="ntsk ")
        by_name = {r[0].split()[-1]: r for r in result}
        assert by_name["delete"][3] == "write"
        assert by_name["simple"][3] == "read"

    def test_has_yes_flag(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_flat(grp, ctx, prefix="ntsk ")
        by_name = {r[0].split()[-1]: r for r in result}
        assert by_name["delete"][4] is True
        assert by_name["simple"][4] is False

    def test_hidden_excluded(self) -> None:
        grp = _make_group()
        ctx = click.Context(grp, info_name="root")
        result = _walk_flat(grp, ctx, prefix="ntsk ")
        commands = [r[0] for r in result]
        assert not any("hidden" in c for c in commands)


class TestWriteCommandNames:
    def test_expected_names_present(self) -> None:
        for name in ("create", "delete", "deploy", "update", "revoke"):
            assert name in _WRITE_COMMAND_NAMES

    def test_read_names_absent(self) -> None:
        for name in ("list", "get", "show", "status", "search"):
            assert name not in _WRITE_COMMAND_NAMES
