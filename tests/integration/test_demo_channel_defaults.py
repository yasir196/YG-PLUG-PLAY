from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, ChannelRoute, Plugin, Workflow, WorkflowVersion
from core.workspace.service import WorkspaceService

DEMO = Path(__file__).resolve().parents[2] / "niches" / "demo"


def _load(relative: str) -> dict[str, Any]:
    return json.loads((DEMO / relative).read_text(encoding="utf-8"))


def _route_key(route: tuple[Any, ...]) -> tuple[str, str]:
    return (route[0], route[1] or "")


def _expected_routes() -> list[tuple[Any, ...]]:
    routes = _load("routing/default.routes.json")["routes"]
    rows = [
        (
            r["capability"],
            r.get("purpose"),
            r.get("variant"),
            r["primary_plugin_id"],
            r.get("options", {}),
        )
        for r in routes
    ]
    return sorted(rows, key=_route_key)


def _routes(session: Session, channel_id: str) -> list[tuple[Any, ...]]:
    rows = session.scalars(select(ChannelRoute).where(ChannelRoute.channel_id == channel_id))
    return sorted(
        (
            (r.capability, r.purpose, r.variant, r.primary_plugin_id, json.loads(r.options_json))
            for r in rows
        ),
        key=_route_key,
    )


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "workspace.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_demo_channel_materializes_checkout_defaults(session: Session) -> None:
    channel = WorkspaceService(session).create_channel("Demo", "demo", "1.0.0")
    session.commit()

    workflow_id = f"{channel.id}:demo-production"
    assert session.get(Workflow, workflow_id) is not None
    versions = list(
        session.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id))
    )
    expected = _load("workflows/default.workflow.json")
    assert len(versions) == 1
    assert versions[0].version == expected["version"]
    assert json.loads(versions[0].definition_json) == expected
    assert _routes(session, channel.id) == _expected_routes()
    assert session.get(Plugin, "demo-text-provider") is not None


def test_second_demo_channel_gets_isolated_defaults(session: Session) -> None:
    service = WorkspaceService(session)
    first = service.create_channel("First", "demo", "1.0.0")
    second = service.create_channel("Second", "demo", "1.0.0")
    session.commit()

    assert first.id != second.id
    for channel in (first, second):
        assert session.get(Workflow, f"{channel.id}:demo-production") is not None
        assert _routes(session, channel.id) == _expected_routes()
    plugins = session.scalars(select(Plugin).where(Plugin.id == "demo-text-provider")).all()
    assert len(plugins) == 1


def test_non_demo_niche_gets_no_demo_defaults(session: Session) -> None:
    channel = WorkspaceService(session).create_channel("Other", "other-niche", "1.0.0")
    session.commit()

    assert session.get(Workflow, f"{channel.id}:demo-production") is None
    assert _routes(session, channel.id) == []
