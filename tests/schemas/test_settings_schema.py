from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

SCHEMA = json.loads(Path("schemas/settings.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.mark.parametrize(
    "document",
    [
        {
            "version": 1,
            "fields": [
                {
                    "key": "model",
                    "label": "Model",
                    "type": "select",
                    "default": "default-model",
                    "allowed_scopes": ["channel"],
                    "platform_fallback": True,
                    "options": [
                        {"value": "default-model", "label": "Default model"},
                        {"value": "strong-model", "label": "Strong model"},
                    ],
                },
                {
                    "key": "temperature",
                    "type": "number",
                    "default": 0.7,
                    "allowed_scopes": ["channel", "project", "run"],
                },
                {
                    "key": "streaming",
                    "type": "bool",
                    "default": True,
                    "allowed_scopes": ["platform", "channel"],
                },
            ],
        },
        {
            "fields": [
                {
                    "key": "api-key",
                    "label": "API key",
                    "type": "secret",
                    "required": True,
                    "allowed_scopes": ["channel"],
                },
                {
                    "key": "voice",
                    "type": "select",
                    "allowed_scopes": ["channel"],
                    "options_source": {
                        "capability": "voice-list",
                        "path": "voices",
                        "value_field": "id",
                        "label_field": "name",
                    },
                },
                {
                    "key": "formats",
                    "type": "multiselect",
                    "default": ["mp3"],
                    "allowed_scopes": ["channel"],
                    "options": [
                        {"value": "mp3", "label": "MP3"},
                        {"value": "wav", "label": "WAV"},
                    ],
                },
                {
                    "key": "style.instructions",
                    "type": "string",
                    "default": "",
                    "allowed_scopes": ["channel", "project"],
                },
            ]
        },
    ],
)
def test_v5_settings_examples_validate(document: dict[str, Any]) -> None:
    VALIDATOR.validate(document)


@pytest.mark.parametrize("default", ["plaintext-key", 123, True, ["secret"]])
def test_secret_field_with_default_fails(default: Any) -> None:
    document = {
        "fields": [
            {
                "key": "api-key",
                "type": "secret",
                "default": default,
                "allowed_scopes": ["channel"],
            }
        ]
    }
    assert list(VALIDATOR.iter_errors(document))


def test_select_requires_exactly_one_options_source() -> None:
    field = {
        "key": "model",
        "type": "select",
        "allowed_scopes": ["channel"],
        "options": [{"value": "a", "label": "A"}],
        "options_source": {"capability": "model-list"},
    }
    assert list(VALIDATOR.iter_errors({"fields": [field]}))
