from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Niche, Plugin, PluginVersion, User
from core.plugin_registry import providers
from core.plugin_registry.registry import PluginRegistry

SHA_1 = "1" * 64
SHA_2 = "2" * 64
SHA_3 = "3" * 64


def _provides(capability: str, purpose: str) -> dict[str, Any]:
    return {
        "capability": capability,
        "executor": "prompt",
        "prompt": "prompts/writing.md",
        "uses": {"capability": "text-generation", "purpose": purpose},
        "input": {"contract": "project.brief", "version": "^1.0"},
        "output": {"contract": "script", "version": "^1.0"},
    }


WRITING_NICHE = [_provides("demo/writing", "demo/writing")]
WRITING_PROMPTS = [_provides("demo/writing", "demo-writing")]
BRIEF_ONLY = [_provides("demo/brief-ready", "demo/brief-ready")]


def _manifest(
    plugin_id: str,
    kind: str,
    version: str,
    provides: list[dict[str, Any]],
    *,
    executable: bool = False,
) -> str:
    runtime: dict[str, Any] = {"kind": "config-only"}
    if executable:
        runtime = {
            "kind": "python-subprocess",
            "python": "3.12",
            "entrypoint": "provider.py",
            "lock_file": "uv.lock",
        }
    return json.dumps(
        {
            "id": plugin_id,
            "name": plugin_id,
            "type": kind,
            "version": version,
            "plugin_api": "v0",
            "minimum_core": "0.0.1",
            "runtime": runtime,
            "compatible_niches": [{"id": "demo", "version": "^1.0"}],
            "permissions": [],
            "provides": provides,
        }
    )


def _install(
    db: Session,
    plugin_id: str,
    kind: str,
    version: str,
    sha: str,
    provides: list[dict[str, Any]],
    *,
    executable: bool = False,
) -> None:
    if db.get(Plugin, plugin_id) is None:
        db.add(Plugin(id=plugin_id, kind=kind))
        db.flush()
    db.add(
        PluginVersion(
            plugin_id=plugin_id,
            version=version,
            package_sha256=sha,
            manifest_json=_manifest(plugin_id, kind, version, provides, executable=executable),
        )
    )
    db.flush()


def _assign(db: Session, plugin_id: str, sha: str, *, enabled: bool = True) -> None:
    PluginRegistry(db).assign("c1", plugin_id, "1.0.0", sha, enabled=enabled)


def _resolve(db: Session, capability: str = "demo/writing") -> Any:
    return providers.resolve_capability_provider(db, "c1", capability)


def _identity(resolved: Any) -> tuple[str, str, str]:
    return (resolved.plugin_id, resolved.version, resolved.package_sha256)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "providers.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as db:
        db.add_all([User(id="admin", username="admin"), Niche(id="demo", version="1.0.0")])
        db.flush()
        db.add(Channel(id="c1", name="C", niche_id="demo", niche_version="1.0.0"))
        db.commit()
        yield db
    engine.dispose()


def test_unknown_channel_fails_closed(session: Session) -> None:
    with pytest.raises(providers.ProviderResolutionError, match="^channel not found$"):
        providers.resolve_capability_provider(session, "missing", "demo/writing")


def test_no_candidate_provides_capability(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, BRIEF_ONLY)
    with pytest.raises(providers.ProviderResolutionError, match="^no capability provider$"):
        _resolve(session)


def test_niche_package_outside_channel_pin_is_not_candidate(session: Session) -> None:
    _install(session, "demo", "niche", "1.1.0", SHA_1, WRITING_NICHE)
    with pytest.raises(providers.ProviderResolutionError, match="^no capability provider$"):
        _resolve(session)


def test_pinned_niche_package_resolves(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, WRITING_NICHE)
    resolved = _resolve(session)
    assert _identity(resolved) == ("demo", "1.0.0", SHA_1)
    assert resolved.provided.capability == "demo/writing"
    assert resolved.provided.uses.purpose == "demo/writing"


def test_enabled_assignment_resolves(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, BRIEF_ONLY)
    _install(session, "demo-prompts", "general", "1.0.0", SHA_2, WRITING_PROMPTS)
    _assign(session, "demo-prompts", SHA_2)
    resolved = _resolve(session)
    assert _identity(resolved) == ("demo-prompts", "1.0.0", SHA_2)
    assert resolved.provided.uses.purpose == "demo-writing"


def test_niche_and_assignment_both_providing_is_ambiguous(session: Session) -> None:
    _install(session, "demo-prompts", "general", "1.0.0", SHA_2, WRITING_PROMPTS)
    _assign(session, "demo-prompts", SHA_2)
    _install(session, "demo", "niche", "1.0.0", SHA_1, WRITING_NICHE)
    expected = "^ambiguous capability provider: demo, demo-prompts$"
    with pytest.raises(providers.ProviderResolutionError, match=expected):
        _resolve(session)


def test_ambiguity_lists_sorted_ids_not_install_order(session: Session) -> None:
    for plugin_id, sha in (("zeta-prompts", SHA_2), ("alpha-prompts", SHA_3)):
        _install(session, plugin_id, "general", "1.0.0", sha, WRITING_PROMPTS)
        _assign(session, plugin_id, sha)
    expected = "^ambiguous capability provider: alpha-prompts, zeta-prompts$"
    with pytest.raises(providers.ProviderResolutionError, match=expected):
        _resolve(session)


def test_disabled_assignment_is_not_candidate(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, WRITING_NICHE)
    _install(session, "demo-prompts", "general", "1.0.0", SHA_2, WRITING_PROMPTS)
    _assign(session, "demo-prompts", SHA_2, enabled=False)
    assert _identity(_resolve(session)) == ("demo", "1.0.0", SHA_1)


def test_latest_same_version_package_is_the_candidate(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, BRIEF_ONLY)
    _install(session, "demo", "niche", "1.0.0", SHA_2, WRITING_NICHE)
    assert _identity(_resolve(session)) == ("demo", "1.0.0", SHA_2)


def test_trust_is_not_a_discovery_criterion(session: Session) -> None:
    _install(session, "exec-prompts", "general", "1.0.0", SHA_2, WRITING_PROMPTS, executable=True)
    registry = PluginRegistry(session)
    registry.grant_trust("exec-prompts", "1.0.0", SHA_2, actor_id="admin", actor_is_admin=True)
    _assign(session, "exec-prompts", SHA_2)
    registry.grant_trust(
        "exec-prompts",
        "1.0.0",
        SHA_2,
        actor_id="admin",
        actor_is_admin=True,
        trust_level="revoked",
    )
    assert _identity(_resolve(session)) == ("exec-prompts", "1.0.0", SHA_2)


def test_niche_also_assigned_counts_once(session: Session) -> None:
    _install(session, "demo", "niche", "1.0.0", SHA_1, WRITING_NICHE)
    _assign(session, "demo", SHA_1)
    assert _identity(_resolve(session)) == ("demo", "1.0.0", SHA_1)


def test_package_declaring_capability_twice_fails_closed(session: Session) -> None:
    twice = [_provides("demo/writing", "demo/writing"), _provides("demo/writing", "demo-writing")]
    _install(session, "demo", "niche", "1.0.0", SHA_1, twice)
    expected = "^ambiguous capability declaration: demo$"
    with pytest.raises(providers.ProviderResolutionError, match=expected):
        _resolve(session)
