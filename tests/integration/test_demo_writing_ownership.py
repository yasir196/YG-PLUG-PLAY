from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Niche, Plugin, PluginVersion
from core.plugin_registry import providers
from core.plugin_registry.registry import PluginRegistry
from core.prompt_executor import PromptExecutor

ROOT = Path(__file__).resolve().parents[2]
NICHE = ROOT / "niches" / "demo"
PROMPTS = ROOT / "plugins" / "demo-prompts"
NICHE_SHA = "1" * 64
PROMPTS_SHA = "2" * 64


def _install(db: Session, package: Path, kind: str, sha: str) -> None:
    raw = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
    db.add(Plugin(id=raw["id"], kind=kind))
    db.flush()
    db.add(
        PluginVersion(
            plugin_id=raw["id"],
            version=raw["version"],
            package_sha256=sha,
            manifest_json=json.dumps(raw),
        )
    )
    db.flush()


def _identity(resolved: providers.CapabilityProvider) -> tuple[str, str, str]:
    return (resolved.plugin_id, resolved.version, resolved.package_sha256)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "ownership.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        db.add(Niche(id="demo", version="1.0.0"))
        db.flush()
        db.add(Channel(id="c1", name="C", niche_id="demo", niche_version="1.0.0"))
        db.flush()
        _install(db, NICHE, "niche", NICHE_SHA)
        _install(db, PROMPTS, "general", PROMPTS_SHA)
        PluginRegistry(db).assign("c1", "demo-prompts", "1.0.0", PROMPTS_SHA, enabled=True)
        db.commit()
        yield db
    engine.dispose()


def test_real_demo_writing_resolves_to_demo_prompts(session: Session) -> None:
    resolved = providers.resolve_capability_provider(session, "c1", "demo/writing")
    assert _identity(resolved) == ("demo-prompts", "1.0.0", PROMPTS_SHA)
    assert resolved.provided.uses.purpose == "demo-writing"


def test_real_demo_brief_ready_stays_with_niche(session: Session) -> None:
    resolved = providers.resolve_capability_provider(session, "c1", "demo/brief-ready")
    assert _identity(resolved) == ("demo", "1.0.0", NICHE_SHA)


def test_demo_writing_prompt_resolves_to_owning_plugin() -> None:
    resolved = PromptExecutor._prompt_path("prompts/writing.md", PROMPTS, NICHE, None)
    assert resolved.resolve() == (PROMPTS / "prompts" / "writing.md").resolve()
