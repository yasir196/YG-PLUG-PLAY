"""Unbootstrapped checkout: Channel creation fails closed (C-delta).

Supersedes the C-alpha characterization recorded in ERRATA_V5 E18: without
installed packages, create_channel no longer invents a Niche row or a Channel.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Niche, PluginVersion
from core.plugin_registry.registry import PluginRegistry
from core.workspace.service import WorkspaceService

UNINSTALLED_SHA = "0" * 64


def _error() -> type[Exception]:
    from core.workspace.service import ChannelCreationError

    return ChannelCreationError


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "checkout-gap.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_unbootstrapped_demo_channel_fails_closed(session: Session) -> None:
    with pytest.raises(_error()):
        WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")


def test_rejected_demo_channel_leaves_no_state(session: Session) -> None:
    with pytest.raises(_error()):
        WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    assert not session.new
    session.commit()
    assert session.scalars(select(Niche)).all() == []
    assert session.scalars(select(Channel)).all() == []
    assert session.scalars(select(PluginVersion)).all() == []


def test_demo_text_provider_is_not_installed(session: Session) -> None:
    availability = PluginRegistry(session).effective_availability(
        "missing-channel", "demo-text-provider", "1.0.0", UNINSTALLED_SHA
    )
    assert availability.available is False
    assert availability.reasons == ("package-not-installed",)
