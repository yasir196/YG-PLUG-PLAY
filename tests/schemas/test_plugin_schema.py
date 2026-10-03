from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from core.plugin_registry.manifest import PluginManifest

SCHEMA = json.loads(Path("schemas/plugin.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def assert_both_valid(manifest: dict[str, Any]) -> None:
    VALIDATOR.validate(manifest)
    PluginManifest.model_validate(manifest)


def elevenlabs_manifest() -> dict[str, Any]:
    return {
        "id": "elevenlabs",
        "name": "ElevenLabs",
        "type": "general",
        "version": "1.0.0",
        "plugin_api": "v0",
        "minimum_core": "0.0.1",
        "runtime": {
            "kind": "python-subprocess",
            "python": "3.12",
            "entrypoint": "plugin/main.py",
            "lock_file": "uv.lock",
        },
        "requested_trust": "trusted",
        "compatible_niches": ["*"],
        "permissions": ["artifact.read", "artifact.write", "provider.jobs"],
        "credentials": [
            {
                "name": "api-key",
                "mode": "proxy",
                "inject": {"type": "header", "name": "xi-api-key"},
                "allowed_domains": ["api.elevenlabs.io"],
            }
        ],
        "provides": [
            {
                "capability": "voice-generation",
                "input": {"contract": "voice.request", "version": "^1.0"},
                "output": {"contract": "audio.asset", "version": "^1.0"},
                "executor": "rpc",
            }
        ],
        "events": {"emits": ["elevenlabs.voice-completed"]},
        "settings_schema": "settings.schema.json",
    }


def prompt_only_manifest() -> dict[str, Any]:
    return {
        "id": "senior-health-prompts",
        "name": "Senior Health Prompts",
        "type": "niche",
        "version": "1.0.0",
        "plugin_api": "v0",
        "minimum_core": "0.0.1",
        "runtime": {"kind": "config-only"},
        "requested_trust": "untrusted",
        "compatible_niches": [{"id": "senior-health", "version": "^1.0"}],
        "permissions": [],
        "provides": [
            {
                "capability": "senior-health/medical-review",
                "executor": "prompt",
                "prompt": "prompts/medical-review.md",
                "rules": [
                    {"type": "prompt-context", "path": "rules/medical-context.md"},
                    {"type": "validator", "path": "rules/medical-output.json"},
                ],
                "uses": {
                    "capability": "text-generation",
                    "purpose": "senior-health/medical-review",
                },
                "requirements": {"supports_json_schema": True},
                "input": {"contract": "script", "version": "^1.0"},
                "output": {
                    "contract": "senior-health/medical-review",
                    "version": "^1.0",
                },
            }
        ],
    }


@pytest.mark.parametrize("factory", [elevenlabs_manifest, prompt_only_manifest])
def test_v5_examples_validate(factory: Any) -> None:
    assert_both_valid(factory())


def test_niche_plugin_wildcard_fails() -> None:
    manifest = prompt_only_manifest()
    manifest["compatible_niches"] = ["*"]
    assert list(VALIDATOR.iter_errors(manifest))
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest)


def test_config_only_entrypoint_fails() -> None:
    manifest = prompt_only_manifest()
    manifest["runtime"]["entrypoint"] = "plugin/main.py"
    assert list(VALIDATOR.iter_errors(manifest))
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest)


def test_unknown_permission_fails() -> None:
    manifest = elevenlabs_manifest()
    manifest["permissions"] = ["core.database"]
    assert list(VALIDATOR.iter_errors(manifest))
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest)


def test_provider_feature_flags_validate() -> None:
    manifest = deepcopy(elevenlabs_manifest())
    manifest["provides"][0]["features"] = {
        "supports_streaming": True,
        "supports_token_count": True,
        "max_context_tokens": 200000,
    }
    assert_both_valid(manifest)
