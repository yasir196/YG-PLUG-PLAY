from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Capability
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registries import RegistryConflict, RuntimeRegistries

ROOT = Path(__file__).resolve().parents[1]
NICHE = ROOT / "niches" / "demo"
PROMPTS = ROOT / "plugins" / "demo-prompts"


def _raw(package: Path) -> dict:
    return json.loads((package / "plugin.json").read_text(encoding="utf-8"))


def _manifest(package: Path) -> PluginManifest:
    return PluginManifest.model_validate(_raw(package))


def _uses(package: Path, capability: str) -> dict:
    entry = next(p for p in _raw(package)["provides"] if p["capability"] == capability)
    return entry["uses"]


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "registry.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_duplicate_demo_writing_collapses_into_one_capability(session: Session) -> None:
    # Evidence: the two packages declare different execution for demo/writing.
    assert _uses(NICHE, "demo/writing")["purpose"] != _uses(PROMPTS, "demo/writing")["purpose"]

    registries = RuntimeRegistries(session, ROOT / "schemas")
    registries.populate(_manifest(NICHE), NICHE)
    registries.populate(_manifest(PROMPTS), PROMPTS)
    session.flush()

    rows = session.scalars(select(Capability).where(Capability.id == "demo/writing")).all()
    assert len(rows) == 1
    stored = json.loads(rows[0].schema_json)
    assert set(stored) == {"id", "version", "input", "output"}
    for execution_field in ("uses", "purpose", "rules", "prompt", "executor"):
        assert execution_field not in rows[0].schema_json


def test_delegated_plugin_before_niche_owner_is_rejected(session: Session) -> None:
    registries = RuntimeRegistries(session, ROOT / "schemas")
    with pytest.raises(RegistryConflict, match="namespace demo has no owner"):
        registries.populate(_manifest(PROMPTS), PROMPTS)
