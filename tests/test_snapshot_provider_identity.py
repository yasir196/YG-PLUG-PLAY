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
    PluginSetting,
    PluginVersion,
    Project,
    User,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from core.plugin_registry.registry import PluginRegistry
from core.routing import PurposeRouter, RouteError
from core.routing.router import ResolvedRoute
from core.workflow.snapshot import freeze_run_snapshot

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
WORKFLOW = {
    "id": "w",
    "version": 1,
    "start": "done",
    "nodes": [{"id": "done", "type": "end", "status": "success"}],
}


def _manifest(version: str) -> str:
    return json.dumps(
        {
            "id": "provider",
            "name": "Provider",
            "type": "general",
            "version": version,
            "plugin_api": "v0",
            "minimum_core": "0.0.1",
            "runtime": {
                "kind": "python-subprocess",
                "python": "3.12",
                "entrypoint": "provider.py",
                "lock_file": "uv.lock",
            },
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


def _install(db: Session, version: str, sha: str) -> None:
    db.add(
        PluginVersion(
            plugin_id="provider",
            version=version,
            package_sha256=sha,
            manifest_json=_manifest(version),
        )
    )
    db.flush()
    PluginRegistry(db).grant_trust("provider", version, sha, actor_id="admin", actor_is_admin=True)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "provider-identity.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        db.add_all(
            [
                User(id="admin", username="admin"),
                Niche(id="demo", version="1.0.0"),
                Plugin(id="provider", kind="general"),
                Workflow(id="w", name="W"),
            ]
        )
        db.flush()
        db.add(Channel(id="c1", name="C", niche_id="demo", niche_version="1.0.0"))
        db.flush()
        _install(db, "1.0.0", SHA_A)
        PluginRegistry(db).assign("c1", "provider", "1.0.0", SHA_A, enabled=True)
        db.add(
            PluginSetting(
                plugin_id="provider",
                scope="channel",
                scope_id="c1",
                key="temperature",
                value_json=json.dumps(0.1),
            )
        )
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


def _resolve(session: Session, routes: list[dict[str, Any]]) -> ResolvedRoute:
    return PurposeRouter(session).resolve(
        channel_id="c1",
        capability="text-generation",
        purpose="demo-writing",
        frozen_routes=routes,
    )


def test_snapshot_route_freezes_provider_identity_and_settings(session: Session) -> None:
    routes = _frozen_routes(session)
    assert routes[0]["provider"] == {
        "version": "1.0.0",
        "package_sha256": SHA_A,
        "settings": {"temperature": 0.1},
    }


def test_frozen_setting_survives_live_setting_mutation(session: Session) -> None:
    routes = _frozen_routes(session)
    setting = session.query(PluginSetting).filter_by(plugin_id="provider", key="temperature").one()
    setting.value_json = json.dumps(0.9)
    session.commit()

    resolved = _resolve(session, routes)
    assert resolved.options["temperature"] == 0.1
    assert resolved.package_sha256 == SHA_A


def test_same_version_new_package_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    _install(session, "1.0.0", SHA_B)
    session.commit()

    with pytest.raises(RouteError, match="provider changed since run start"):
        _resolve(session, routes)


def test_version_change_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    _install(session, "1.1.0", SHA_C)
    PluginRegistry(session).assign("c1", "provider", "1.1.0", SHA_C, enabled=True)
    session.commit()

    with pytest.raises(RouteError, match="provider changed since run start"):
        _resolve(session, routes)


def test_trust_revocation_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    PluginRegistry(session).grant_trust(
        "provider",
        "1.0.0",
        SHA_A,
        actor_id="admin",
        actor_is_admin=True,
        trust_level="revoked",
    )
    session.commit()

    with pytest.raises(RouteError, match="provider unavailable: trust-missing"):
        _resolve(session, routes)


def test_disabled_assignment_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    PluginRegistry(session).assign("c1", "provider", "1.0.0", SHA_A, enabled=False)
    session.commit()

    with pytest.raises(RouteError, match="provider is not enabled for Channel"):
        _resolve(session, routes)


def test_legacy_route_without_provider_block_fails_closed(session: Session) -> None:
    routes = _frozen_routes(session)
    for route in routes:
        route.pop("provider", None)

    with pytest.raises(RouteError, match="snapshot provider identity missing"):
        _resolve(session, routes)


def test_unrelated_route_without_provider_block_does_not_block(session: Session) -> None:
    routes = _frozen_routes(session)
    unrelated = {
        **routes[0],
        "purpose": "demo-review",
        "route_id": routes[0]["route_id"] + 1000,
    }
    unrelated.pop("provider", None)
    routes.append(unrelated)

    resolved = _resolve(session, routes)
    assert resolved.package_sha256 == SHA_A
