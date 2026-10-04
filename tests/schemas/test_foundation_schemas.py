from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator


def validator(name: str) -> Draft202012Validator:
    schema = json.loads(Path(f"schemas/{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    ("schema_name", "document"),
    [
        (
            "capability",
            {
                "id": "text-generation",
                "version": "1.0.0",
                "input": {"contract": "text-generation.request", "version": "^1.0"},
                "output": {"contract": "text-generation.result", "version": "^1.0"},
                "features": {
                    "supports_json_schema": True,
                    "supports_streaming": True,
                    "max_context_tokens": 200000,
                },
            },
        ),
        (
            "capability",
            {
                "id": "senior-health/medical-review",
                "version": "1.0.0",
                "input": {"contract": "script", "version": "^1.0"},
                "output": {
                    "contract": "senior-health/medical-review",
                    "version": "^1.0",
                },
                "requirements": {"supports_json_schema": True},
            },
        ),
        (
            "contract",
            {
                "id": "project.brief",
                "version": "1.0.0",
                "schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["title", "topic", "goal", "language", "metadata"],
                    "properties": {
                        "title": {"type": "string"},
                        "topic": {"type": "string"},
                        "goal": {"type": "string"},
                        "language": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                },
            },
        ),
        (
            "brief-form",
            {
                "version": 1,
                "title": "Senior Health Project Brief",
                "fields": [
                    {"key": "title", "type": "string", "label": "Title", "required": True},
                    {"key": "topic", "type": "text", "label": "Topic", "required": True},
                    {
                        "key": "target-audience",
                        "type": "select",
                        "label": "Target audience",
                        "default": "60-plus",
                        "options": [
                            {"value": "60-plus", "label": "60+"},
                            {"value": "caregiver", "label": "Caregiver"},
                        ],
                    },
                    {
                        "key": "metadata.tags",
                        "type": "multiselect",
                        "label": "Tags",
                        "default": [],
                        "options": [{"value": "mobility", "label": "Mobility"}],
                    },
                ],
            },
        ),
    ],
)
def test_valid_documents(schema_name: str, document: dict[str, Any]) -> None:
    validator(schema_name).validate(document)


@pytest.mark.parametrize(
    ("schema_name", "document"),
    [
        (
            "capability",
            {
                "id": "Text_Generation",
                "version": "1.0.0",
                "input": {"contract": "request", "version": "^1.0"},
                "output": {"contract": "result", "version": "^1.0"},
            },
        ),
        (
            "contract",
            {
                "id": "Project_Brief",
                "version": "1.0.0",
                "schema": {"type": "object"},
            },
        ),
        (
            "contract",
            {"id": "project.brief", "version": "one", "schema": {"type": "object"}},
        ),
        (
            "brief-form",
            {
                "version": 1,
                "fields": [{"key": "audience", "type": "select", "label": "Audience"}],
            },
        ),
        (
            "brief-form",
            {
                "version": 1,
                "fields": [
                    {
                        "key": "age",
                        "type": "number",
                        "label": "Age",
                        "default": "sixty",
                    }
                ],
            },
        ),
    ],
)
def test_invalid_documents(schema_name: str, document: dict[str, Any]) -> None:
    assert list(validator(schema_name).iter_errors(document))
