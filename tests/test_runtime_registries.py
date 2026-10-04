from __future__ import annotations

from pathlib import Path

import pytest

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Capability, NamespaceRegistry
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registries import RegistryConflict, RuntimeRegistries


def manifest(plugin_id: str, *, niche: str | None = None, delegation: bool = False):
    raw = {
        "id": plugin_id,
        "name": plugin_id,
        "type": "general",
        "version": "1.0.0",
        "plugin_api": "v0",
        "minimum_core": "0.0.1",
        "runtime": {"kind": "config-only"},
        "compatible_niches": ["*"] if niche is None else [{"id": niche, "version": "^1.0"}],
        "permissions": [],
        "provides": [
            {
                "capability": f"{niche or plugin_id}/generate",
                "input": {"contract": "project.brief", "version": "^1.0"},
                "output": {"contract": "script", "version": "^1.0"},
            }
        ],
    }
    if delegation and niche:
        raw["namespace_delegations_requested"] = [niche]
    return PluginManifest.model_validate(raw)


@pytest.fixture
def db(tmp_path):
    engine = create_sqlite_engine(tmp_path / "registry.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        yield session, tmp_path
    engine.dispose()


def test_install_population_registers_namespace_and_capability(db) -> None:
    session, tmp = db
    RuntimeRegistries(session, Path("schemas")).populate(manifest("writer"), tmp)
    assert session.get(NamespaceRegistry, "writer").owner_id == "writer"
    assert session.get(Capability, "writer/generate") is not None


def test_conflicting_namespace_registration_is_rejected(db) -> None:
    session, tmp = db
    session.add(NamespaceRegistry(namespace="writer", owner_type="general", owner_id="other"))
    session.flush()
    with pytest.raises(RegistryConflict, match="already owned"):
        RuntimeRegistries(session, Path("schemas")).populate(manifest("writer"), tmp)


def test_niche_namespace_delegation_keeps_niche_owner(db) -> None:
    session, tmp = db
    session.add(
        NamespaceRegistry(namespace="senior-health", owner_type="niche", owner_id="senior-health")
    )
    session.flush()
    plugin = manifest("reviewer", niche="senior-health", delegation=True)
    RuntimeRegistries(session, Path("schemas")).populate(plugin, tmp)
    assert session.get(NamespaceRegistry, "senior-health").owner_id == "senior-health"
    assert session.get(Capability, "senior-health/generate") is not None


def test_niche_namespace_without_delegation_is_rejected(db) -> None:
    session, tmp = db
    session.add(
        NamespaceRegistry(namespace="senior-health", owner_type="niche", owner_id="senior-health")
    )
    session.flush()
    with pytest.raises(RegistryConflict, match="no authority"):
        RuntimeRegistries(session, Path("schemas")).populate(
            manifest("reviewer", niche="senior-health", delegation=False), tmp
        )
