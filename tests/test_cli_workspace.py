"""C-epsilon contract: explicit CLI demo bootstrap and an operational workspace CLI."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from core.database import create_sqlite_engine, session_factory
from core.database.models import Niche, PluginVersion
from tools.yg.cli import app

runner = CliRunner()
BOOTSTRAP_LINE = re.compile(r"^([a-z-]+) 1\.0\.0 sha256:([0-9a-f]{64})$")
EXPECTED_ORDER = ["demo", "demo-prompts", "demo-text-provider"]


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "yg-data"


def _invoke(data_root: Path, *args: str):
    # Every invocation is isolated: never touch the runner's real LOCALAPPDATA.
    return runner.invoke(app, list(args), env={"YG_DATA_ROOT": str(data_root)})


def _detail(result) -> str:
    return f"exit={result.exit_code} exc={result.exception!r} out={result.output!r}"


def _ok(result) -> str:
    assert result.exception is None, _detail(result)
    assert result.exit_code == 0, _detail(result)
    return result.output


def _error(result, message: str) -> None:
    assert isinstance(result.exception, SystemExit), _detail(result)
    assert result.exit_code == 1, _detail(result)
    assert f"ERROR: {message}" in result.output, _detail(result)
    assert "Traceback" not in result.output, _detail(result)


def _bootstrap(data_root: Path) -> list[tuple[str, str]]:
    lines = _ok(_invoke(data_root, "demo", "bootstrap")).splitlines()
    parsed = [BOOTSTRAP_LINE.match(line) for line in lines]
    assert all(parsed), lines
    return [(match.group(1), match.group(2)) for match in parsed if match]


def _identities(data_root: Path) -> list[tuple[str, str, str]]:
    engine = create_sqlite_engine(data_root / "db" / "core.db")
    try:
        with session_factory(engine)() as db:
            rows = db.scalars(select(PluginVersion))
            return sorted((row.plugin_id, row.version, row.package_sha256) for row in rows)
    finally:
        engine.dispose()


def _niches(data_root: Path) -> list[tuple[str, str]]:
    engine = create_sqlite_engine(data_root / "db" / "core.db")
    try:
        with session_factory(engine)() as db:
            return sorted((row.id, row.version) for row in db.scalars(select(Niche)))
    finally:
        engine.dispose()


def test_channel_list_works_on_fresh_data_root(data_root: Path) -> None:
    assert _ok(_invoke(data_root, "channel", "list")) == ""


def test_demo_bootstrap_installs_bundled_packages(data_root: Path) -> None:
    installed = _bootstrap(data_root)
    assert [package_id for package_id, _sha in installed] == EXPECTED_ORDER
    assert _identities(data_root) == sorted((pid, "1.0.0", sha) for pid, sha in installed)
    assert _niches(data_root) == [("demo", "1.0.0")]


def test_demo_bootstrap_is_idempotent(data_root: Path) -> None:
    first = _bootstrap(data_root)
    identities = _identities(data_root)
    second = _bootstrap(data_root)
    assert second == first
    assert _identities(data_root) == identities
    assert len(identities) == 3


def test_channel_create_after_bootstrap(data_root: Path) -> None:
    _bootstrap(data_root)
    channel_id = _ok(_invoke(data_root, "channel", "create", "Demo", "demo")).strip()
    assert re.fullmatch(r"[0-9a-f]{32}", channel_id), channel_id
    listed = _ok(_invoke(data_root, "channel", "list"))
    assert listed == f"{channel_id}\tDemo\tdemo@1.0.0\n"


def test_channel_create_without_bootstrap_fails_closed(data_root: Path) -> None:
    result = _invoke(data_root, "channel", "create", "Demo", "demo")
    _error(result, "niche demo is not registered")
    assert _ok(_invoke(data_root, "channel", "list")) == ""


def test_unknown_channel_reports_error(data_root: Path) -> None:
    _error(_invoke(data_root, "channel", "open", "missing"), "channel not found")
