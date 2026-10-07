from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import (
    Base,
    Channel,
    ChannelRoute,
    Niche,
    Plugin,
    PluginVersion,
    Project,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from core.plugin_registry.registry import PluginRegistry
from core.routing import PurposeRouter, RouteError
from core.workflow.snapshot import freeze_run_snapshot

SHA = "a" * 64
WORKFLOW = {
    "id": "w",
    "version": 1,
    "start": "done",
    "nodes": [{"id": "done", "type": "end", "status": "success"}],
}


def _provider_manifest() -> str:
    return json.dumps(
        {
            "id": "provider",
            "name": "Provider",
            "type": "general",
            "version": "1.0.0",
            "plugin_api": "v0",
            "minimum_core": "0.0.1",
            "runtime": {"kind": "config-only"},
            "compatible_niches": ["*"],
            "permissions": [],
            "provides": [
                {
                    "capability": "text-generation",
                    "input": {"contract": "text-generation.request", "version": "^1.0"},
                    "output": {"contract": "text-generation.result", "version": "^1.0"},
                }
            ],
        }
    )


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "snapshot-routing.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        db.add_all(
            [
                Niche(id="demo", version="1.0.0"),
                Plugin(id="provider", kind="general"),
                Workflow(id="w", name="W"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Channel(id="c1", name="C", niche_id="demo", niche_version="1.0.0"),
                PluginVersion(
                    plugin_id="provider",
                    version="1.0.0",
                    package_sha256=SHA,
                    manifest_json=_provider_manifest(),
                ),
            ]
        )
        db.flush()
        PluginRegistry(db).assign("c1", "provider", "1.0.0", SHA, enabled=True)
        db.add(Project(id="p", channel_id="c1", title="P"))
        version = WorkflowVersion(workflow_id="w", version=1, definition_json=json.dumps(WORKFLOW))
        db.add(version)
        db.add(
            ChannelRoute(
                channel_id="c1",
                capability="text-generation",
                purpose="demo-writing",
                primary_plugin_id="provider",
                options_json=json.dumps({"model": "frozen-model"}),
            )
        )
        db.flush()
        db.add(
            WorkflowRun(
                id="r",
                project_id="p",
                workflow_version_id=version.id,
                status="running",
                current_node_id="done",
            )
        )
        db.commit()
        yield db
    engine.dispose()


def _frozen_routes(session: Session) -> list[dict[str, Any]]:
    routes = freeze_run_snapshot(session, "r")["routes"]
    session.commit()
    return routes


def _live_route(session: Session) -> ChannelRoute:
    return session.query(ChannelRoute).filter_by(channel_id="c1").one()


def test_snapshot_routes_carry_stable_route_identity(session: Session) -> None:
    live_id = _live_route(session).id
    routes = _frozen_routes(session)
    assert [route["route_id"] for route in routes] == [live_id]


def test_frozen_route_wins_over_live_option_mutation(session: Session) -> None:
    live = _live_route(session)
    frozen_id = live.id
    routes = _frozen_routes(session)
    live.options_json = json.dumps({"model": "live-model"})
    session.commit()

    resolved = PurposeRouter(session).resolve(
        channel_id="c1",
        capability="text-generation",
        purpose="demo-writing",
        frozen_routes=routes,
    )
    assert resolved.model == "frozen-model"
    assert resolved.route_id == frozen_id


def test_frozen_route_survives_live_route_deletion(session: Session) -> None:
    routes = _frozen_routes(session)
    session.delete(_live_route(session))
    session.commit()

    resolved = PurposeRouter(session).resolve(
        channel_id="c1",
        capability="text-generation",
        purpose="demo-writing",
        frozen_routes=routes,
    )
    assert resolved.model == "frozen-model"


def test_legacy_snapshot_route_without_identity_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    for route in routes:
        route.pop("route_id", None)

    with pytest.raises(RouteError, match="snapshot route identity missing"):
        PurposeRouter(session).resolve(
            channel_id="c1",
            capability="text-generation",
            purpose="demo-writing",
            frozen_routes=routes,
        )


def test_unrelated_legacy_route_does_not_block_selected_route(session: Session) -> None:
    routes = _frozen_routes(session)
    unrelated = {**routes[0], "purpose": "demo-review"}
    unrelated.pop("route_id", None)
    routes.append(unrelated)

    resolved = PurposeRouter(session).resolve(
        channel_id="c1",
        capability="text-generation",
        purpose="demo-writing",
        frozen_routes=routes,
    )
    assert resolved.model == "frozen-model"
    assert resolved.route_id == _live_route(session).id
