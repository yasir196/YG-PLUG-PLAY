from __future__ import annotations

import json

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, ChannelRoute, Niche, Plugin, PluginVersion
from core.plugin_registry.registry import PluginRegistry
from core.routing import PurposeRouter


def provider_manifest() -> str:
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
                    "features": {"supports_json_schema": True, "max_context_tokens": 100000},
                }
            ],
        }
    )


def test_two_purposes_resolve_different_models_same_channel(tmp_path) -> None:
    engine = create_sqlite_engine(tmp_path / "routes.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        session.add_all(
            [
                Niche(id="demo", version="1.0.0"),
                Channel(id="c1", name="Channel", niche_id="demo", niche_version="1.0.0"),
                Plugin(id="provider", kind="general"),
                PluginVersion(
                    plugin_id="provider",
                    version="1.0.0",
                    package_sha256="a" * 64,
                    manifest_json=provider_manifest(),
                ),
            ]
        )
        session.flush()
        PluginRegistry(session).assign("c1", "provider", "1.0.0", "a" * 64, enabled=True)
        session.add_all(
            [
                ChannelRoute(
                    channel_id="c1",
                    capability="text-generation",
                    purpose="research",
                    primary_plugin_id="provider",
                    options_json=json.dumps({"model": "research-model", "temperature": 0.2}),
                ),
                ChannelRoute(
                    channel_id="c1",
                    capability="text-generation",
                    purpose="script",
                    primary_plugin_id="provider",
                    options_json=json.dumps({"model": "writing-model", "temperature": 0.7}),
                ),
            ]
        )
        session.flush()
        router = PurposeRouter(session)
        research = router.resolve(
            channel_id="c1",
            capability="text-generation",
            purpose="research",
            required_features={"supports_json_schema": True},
            input_contract="text-generation.request",
            output_contract="text-generation.result",
        )
        script = router.resolve(
            channel_id="c1", capability="text-generation", purpose="script"
        )
        assert research.model == "research-model"
        assert research.options["temperature"] == 0.2
        assert script.model == "writing-model"
        assert script.options["temperature"] == 0.7
    engine.dispose()
