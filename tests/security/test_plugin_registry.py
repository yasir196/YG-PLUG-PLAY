from __future__ import annotations

import json

import pytest

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Niche, Plugin, PluginVersion, User
from core.plugin_registry.registry import PluginRegistry, RegistryError


def executable_manifest(compatible: object = "*") -> str:
    return json.dumps(
        {
            "id": "demo-provider",
            "name": "Demo Provider",
            "type": "general",
            "version": "1.0.0",
            "plugin_api": "v0",
            "minimum_core": "0.0.1",
            "runtime": {
                "kind": "python-subprocess",
                "python": ">=3.12",
                "entrypoint": "provider.py",
                "lock_file": "uv.lock",
            },
            "compatible_niches": [compatible],
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
def db(tmp_path):
    engine = create_sqlite_engine(tmp_path / "registry.db")
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    with Session() as session:
        session.add_all(
            [
                User(id="admin", username="admin"),
                Niche(id="demo", version="1.0.0"),
                Channel(id="c1", name="Demo", niche_id="demo", niche_version="1.0.0"),
                Plugin(id="demo-provider", kind="general"),
            ]
        )
        session.commit()
        yield session
    engine.dispose()


def add_version(db, digest: str, compatible: object = "*") -> None:
    db.add(
        PluginVersion(
            plugin_id="demo-provider",
            version="1.0.0",
            package_sha256=digest,
            manifest_json=executable_manifest(compatible),
        )
    )
    db.commit()


def test_executable_cannot_enable_without_sha_bound_trust(db) -> None:
    digest = "a" * 64
    add_version(db, digest)
    registry = PluginRegistry(db)
    with pytest.raises(RegistryError, match="trust"):
        registry.platform_enable("demo-provider", "1.0.0", digest)
    registry.grant_trust("demo-provider", "1.0.0", digest, actor_id="admin", actor_is_admin=True)
    registry.platform_enable("demo-provider", "1.0.0", digest)


def test_non_admin_cannot_grant_trust(db) -> None:
    digest = "b" * 64
    add_version(db, digest)
    with pytest.raises(RegistryError, match="admin"):
        PluginRegistry(db).grant_trust(
            "demo-provider", "1.0.0", digest, actor_id="admin", actor_is_admin=False
        )


def test_incompatible_niche_plugin_cannot_be_assigned(db) -> None:
    digest = "c" * 64
    add_version(db, digest, {"id": "other-niche", "version": "^1.0"})
    registry = PluginRegistry(db)
    registry.grant_trust("demo-provider", "1.0.0", digest, actor_id="admin", actor_is_admin=True)
    with pytest.raises(RegistryError, match="incompatible"):
        registry.assign("c1", "demo-provider", "1.0.0", digest, enabled=True)


def test_different_hash_loses_trust(db) -> None:
    old_hash, new_hash = "d" * 64, "e" * 64
    add_version(db, old_hash)
    add_version(db, new_hash)
    registry = PluginRegistry(db)
    registry.grant_trust("demo-provider", "1.0.0", old_hash, actor_id="admin", actor_is_admin=True)
    assert registry.has_executable_trust(registry._version("demo-provider", "1.0.0", old_hash))
    assert not registry.has_executable_trust(registry._version("demo-provider", "1.0.0", new_hash))


def test_effective_availability_requires_assignment_enabled(db) -> None:
    digest = "f" * 64
    add_version(db, digest)
    registry = PluginRegistry(db)
    registry.grant_trust("demo-provider", "1.0.0", digest, actor_id="admin", actor_is_admin=True)
    assert registry.effective_availability("c1", "demo-provider", "1.0.0", digest).reasons == (
        "not-assigned",
    )
    registry.assign("c1", "demo-provider", "1.0.0", digest, enabled=False)
    assert registry.effective_availability("c1", "demo-provider", "1.0.0", digest).reasons == (
        "channel-disabled",
    )
    registry.assign("c1", "demo-provider", "1.0.0", digest, enabled=True)
    assert registry.effective_availability("c1", "demo-provider", "1.0.0", digest).available
