"""Characterize the unbootstrapped checkout: demo packages are not installed.

Evidence for ERRATA_V5 E18. These tests record current behavior and are expected
to change intentionally when bundled demo packages are bootstrapped (Cycle C).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, PluginVersion
from core.plugin_registry.providers import ProviderResolutionError, resolve_capability_provider
from core.plugin_registry.registry import PluginRegistry
from core.workspace.service import WorkspaceService

UNINSTALLED_SHA = "0" * 64


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "checkout-gap.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def _demo_channel(session: Session) -> str:
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()
    return channel.id


def test_demo_channel_has_no_installed_packages(session: Session) -> None:
    _demo_channel(session)
    assert session.scalars(select(PluginVersion)).all() == []


@pytest.mark.parametrize("capability", ["demo/brief-ready", "demo/writing"])
def test_demo_capabilities_have_no_provider(session: Session, capability: str) -> None:
    channel_id = _demo_channel(session)
    with pytest.raises(ProviderResolutionError, match="^no capability provider$"):
        resolve_capability_provider(session, channel_id, capability)


def test_demo_text_provider_is_not_installed(session: Session) -> None:
    channel_id = _demo_channel(session)
    availability = PluginRegistry(session).effective_availability(
        channel_id, "demo-text-provider", "1.0.0", UNINSTALLED_SHA
    )
    assert availability.available is False
    assert availability.reasons == ("package-not-installed",)
