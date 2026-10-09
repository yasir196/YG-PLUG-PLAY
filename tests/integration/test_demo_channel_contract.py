"""C-delta contract: Channel creation consumes installed state and fails closed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config.data_root import DataRootLayout, initialize_data_root
from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, ChannelPluginAssignment, Niche, PluginTrustGrant
from core.plugin_registry.installer import ZipInstaller
from core.plugin_registry.packing import pack_package
from core.plugin_registry.providers import resolve_capability_provider
from core.workspace.bootstrap import install_bundled_demo_packages
from core.workspace.service import WorkspaceService

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "plugin.schema.json"


def _error() -> type[Exception]:
    from core.workspace.service import ChannelCreationError

    return ChannelCreationError


@pytest.fixture
def layout(tmp_path: Path) -> DataRootLayout:
    return initialize_data_root(install_root=ROOT, override=tmp_path / "data")


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "channel-contract.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def _bootstrap(session: Session, layout: DataRootLayout) -> dict[str, str]:
    installed = install_bundled_demo_packages(session, layout, source_root=ROOT)
    session.commit()
    return {item.manifest.id: item.sha256 for item in installed}


def _assert_rejected(session: Session, niche_id: str, version: str) -> None:
    with pytest.raises(_error()):
        WorkspaceService(session).create_channel("Rejected", niche_id, version)
    assert not session.new
    session.rollback()
    assert session.scalars(select(Channel)).all() == []


def test_channel_creation_error_is_value_error() -> None:
    assert issubclass(_error(), ValueError)


def test_demo_channel_assigns_demo_prompts_enabled(
    session: Session, layout: DataRootLayout
) -> None:
    _bootstrap(session, layout)
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    rows = session.scalars(
        select(ChannelPluginAssignment).where(ChannelPluginAssignment.channel_id == channel.id)
    ).all()
    assert [(r.plugin_id, r.plugin_version, r.enabled) for r in rows] == [
        ("demo-prompts", "1.0.0", True)
    ]


def test_demo_channel_grants_no_trust(session: Session, layout: DataRootLayout) -> None:
    _bootstrap(session, layout)
    WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    assert session.scalars(select(PluginTrustGrant)).all() == []


def test_demo_writing_resolves_to_current_demo_prompts_package(
    session: Session, layout: DataRootLayout
) -> None:
    installed = _bootstrap(session, layout)
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    resolved = resolve_capability_provider(session, channel.id, "demo/writing")
    assert (resolved.plugin_id, resolved.version, resolved.package_sha256) == (
        "demo-prompts",
        "1.0.0",
        installed["demo-prompts"],
    )


def test_niche_pin_without_installed_package_is_rejected(session: Session) -> None:
    session.add(Niche(id="other-niche", version="1.0.0"))
    session.commit()
    _assert_rejected(session, "other-niche", "1.0.0")


def test_installed_niche_without_registered_pin_is_rejected(
    session: Session, layout: DataRootLayout
) -> None:
    _bootstrap(session, layout)
    niche = session.get(Niche, "demo")
    assert niche is not None
    session.delete(niche)
    session.commit()
    _assert_rejected(session, "demo", "1.0.0")
    assert session.get(Niche, "demo") is None


def test_niche_version_mismatch_is_rejected(session: Session, layout: DataRootLayout) -> None:
    _bootstrap(session, layout)
    _assert_rejected(session, "demo", "2.0.0")


def test_demo_channel_requires_installed_demo_prompts(
    session: Session, layout: DataRootLayout, tmp_path: Path
) -> None:
    archive, _digest = pack_package(ROOT / "niches" / "demo", tmp_path / "dist", schema_path=SCHEMA)
    ZipInstaller(layout.packages, SCHEMA, session).install(archive)
    session.add(Niche(id="demo", version="1.0.0"))
    session.commit()
    _assert_rejected(session, "demo", "1.0.0")
