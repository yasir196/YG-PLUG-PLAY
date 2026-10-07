from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registries import RegistryConflict, RuntimeRegistries

ROOT = Path(__file__).resolve().parents[1]
NICHE = ROOT / "niches" / "demo"
PROMPTS = ROOT / "plugins" / "demo-prompts"


def _raw(package: Path) -> dict:
    return json.loads((package / "plugin.json").read_text(encoding="utf-8"))


def _manifest(package: Path) -> PluginManifest:
    return PluginManifest.model_validate(_raw(package))


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "registry.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_demo_writing_has_single_declaring_package() -> None:
    declaring = [
        _raw(package)["id"]
        for package in (NICHE, PROMPTS)
        if any(p["capability"] == "demo/writing" for p in _raw(package)["provides"])
    ]
    assert declaring == ["demo-prompts"]


def test_delegated_plugin_before_niche_owner_is_rejected(session: Session) -> None:
    registries = RuntimeRegistries(session, ROOT / "schemas")
    with pytest.raises(RegistryConflict, match="namespace demo has no owner"):
        registries.populate(_manifest(PROMPTS), PROMPTS)
