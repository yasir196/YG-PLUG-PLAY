from __future__ import annotations

import json
from pathlib import Path

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, ChannelRoute, Contract, Niche, Plugin, PluginVersion
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registry import PluginRegistry
from core.prompt_executor import PromptExecutor
from core.routing import PurposeRouter


def test_demo_writing_runs_end_to_end_through_demo_provider(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    engine = create_sqlite_engine(tmp_path / "prompt.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    provider_raw = json.loads((root / "plugins/demo-text-provider/plugin.json").read_text())
    niche_raw = json.loads((root / "niches/demo/plugin.json").read_text())
    provider = PluginManifest.model_validate(provider_raw)
    niche = PluginManifest.model_validate(niche_raw)
    with factory() as session:
        session.add_all([
            Niche(id="demo", version="1.0.0"),
            Channel(id="c1", name="Demo", niche_id="demo", niche_version="1.0.0"),
            Plugin(id=provider.id, kind="general"),
            PluginVersion(plugin_id=provider.id, version=provider.version, package_sha256="a"*64, manifest_json=json.dumps(provider_raw)),
            Contract(id="script", version="1.0.0", schema_json=json.dumps({"type": "string"})),
        ])
        session.flush()
        PluginRegistry(session).assign("c1", provider.id, provider.version, "a"*64, enabled=True)
        session.add(ChannelRoute(channel_id="c1", capability="text-generation", purpose="demo/writing", primary_plugin_id=provider.id, options_json=json.dumps({"model": "demo-deterministic"})))
        session.flush()
        writing = next(item for item in niche.provides if item.capability == "demo/writing")
        result = PromptExecutor(session, PurposeRouter(session)).execute(
            channel_id="c1", capability=writing, plugin_root=root/"niches/demo",
            niche_root=root/"niches/demo", channel_prompt=None, context={"topic": "healthy habits"},
            provider_root=root/"plugins/demo-text-provider",
        )
        assert result.provider == "demo-text-provider"
        assert result.model == "demo-deterministic"
        assert "deterministic generated text" in result.data
        assert len(result.prompt_sha256) == 64
        assert result.rule_hashes
    engine.dispose()
