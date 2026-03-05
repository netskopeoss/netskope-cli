from __future__ import annotations

import pytest
from typer.testing import CliRunner

from netskope_cli.main import app  # noqa: F401


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("NETSKOPE_TENANT", "test.goskope.com")
    monkeypatch.setenv("NETSKOPE_API_TOKEN", "testtoken123")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
