"""C-gamma contract: explicit, idempotent bootstrap of bundled demo packages."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config.data_root import DataRootLayout, initialize_data_root
from core.database import create_sqlite_engine, session_factory
from core.database.models import (
    Base,
    Capability,
    ChannelPluginAssignment,
    NamespaceRegistry,
    Niche,
    PluginTrustGrant,
    PluginVersion,
)
from core.plugin_registry.packing import pack_package
from core.plugin_registry.providers import resolve_capability_provider
from core.plugin_registry.registry import PluginRegistry
from core.workspace.service import WorkspaceService

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "plugin.schema.json"
ORDER = ["demo", "demo-prompts", "demo-text-provider"]
SOURCES = {
    "demo": ROOT / "niches" / "demo",
    "demo-prompts": ROOT / "plugins" / "demo-prompts",
    "demo-text-provider": ROOT / "plugins" / "demo-text-provider",
}


@pytest.fixture
def layout(tmp_path: Path) -> DataRootLayout:
    return initialize_data_root(install_root=ROOT, override=tmp_path / "data")


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "bootstrap.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def _bootstrap(session: Session, layout: DataRootLayout) -> list[tuple[str, str]]:
    from core.workspace.bootstrap import install_bundled_demo_packages

    installed = install_bundled_demo_packages(session, layout, source_root=ROOT)
    session.commit()
    return [(item.manifest.id, item.sha256) for item in installed]


def _versions(session: Session) -> set[tuple[str, str, str]]:
    rows = session.scalars(select(PluginVersion))
    return {(row.plugin_id, row.version, row.package_sha256) for row in rows}


def test_bootstrap_installs_bundled_packages_in_order(
    session: Session, layout: DataRootLayout
) -> None:
    installed = _bootstrap(session, layout)
    assert [plugin_id for plugin_id, _ in installed] == ORDER
    assert _versions(session) == {(plugin_id, "1.0.0", sha) for plugin_id, sha in installed}
    for plugin_id, sha in installed:
        kind = "niches" if plugin_id == "demo" else "plugins"
        assert (layout.packages / kind / plugin_id / "1.0.0" / sha / "plugin.json").is_file()


def test_bootstrap_identity_matches_core_pack(
    session: Session, layout: DataRootLayout, tmp_path: Path
) -> None:
    installed = dict(_bootstrap(session, layout))
    for plugin_id, source in SOURCES.items():
        _archive, digest = pack_package(source, tmp_path / "ref" / plugin_id, schema_path=SCHEMA)
        assert installed[plugin_id] == digest


def test_bootstrap_is_idempotent(session: Session, layout: DataRootLayout) -> None:
    first = _bootstrap(session, layout)
    namespaces = len(session.scalars(select(NamespaceRegistry)).all())
    second = _bootstrap(session, layout)
    assert second == first
    assert len(_versions(session)) == 3
    assert len(session.scalars(select(NamespaceRegistry)).all()) == namespaces


def test_bootstrap_grants_no_trust_and_no_assignment(
    session: Session, layout: DataRootLayout
) -> None:
    _bootstrap(session, layout)
    assert session.scalars(select(PluginTrustGrant)).all() == []
    assert session.scalars(select(ChannelPluginAssignment)).all() == []


def test_bootstrap_registers_niche_pin_and_capabilities(
    session: Session, layout: DataRootLayout
) -> None:
    _bootstrap(session, layout)
    niche = session.get(Niche, "demo")
    assert niche is not None and niche.version == "1.0.0"
    owner = session.get(NamespaceRegistry, "demo")
    assert owner is not None and (owner.owner_type, owner.owner_id) == ("niche", "demo")
    ids = set(session.scalars(select(Capability.id)))
    assert {"demo/brief-ready", "demo/writing", "demo/review"} <= ids


def test_bootstrapped_demo_channel_resolves_niche_and_assigned_prompts(
    session: Session, layout: DataRootLayout
) -> None:
    installed = dict(_bootstrap(session, layout))
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    brief = resolve_capability_provider(session, channel.id, "demo/brief-ready")
    assert (brief.plugin_id, brief.package_sha256) == ("demo", installed["demo"])
    writing = resolve_capability_provider(session, channel.id, "demo/writing")
    assert (writing.plugin_id, writing.package_sha256) == (
        "demo-prompts",
        installed["demo-prompts"],
    )


def test_bootstrapped_provider_is_installed_but_untrusted(
    session: Session, layout: DataRootLayout
) -> None:
    installed = dict(_bootstrap(session, layout))
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    availability = PluginRegistry(session).effective_availability(
        channel.id, "demo-text-provider", "1.0.0", installed["demo-text-provider"]
    )
    assert availability.available is False
    assert "package-not-installed" not in availability.reasons
    assert "trust-missing" in availability.reasons
    assert "not-assigned" in availability.reasons
