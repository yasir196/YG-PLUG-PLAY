from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(".")
PLUGIN_SCHEMA = json.loads((ROOT / "schemas/plugin.schema.json").read_text(encoding="utf-8"))
WORKFLOW_SCHEMA = json.loads((ROOT / "schemas/workflow.schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path",
    [
        "niches/demo/plugin.json",
        "plugins/demo-text-provider/plugin.json",
        "plugins/demo-prompts/plugin.json",
    ],
)
def test_demo_manifests_validate(path: str) -> None:
    document = json.loads((ROOT / path).read_text(encoding="utf-8"))
    Draft202012Validator(PLUGIN_SCHEMA).validate(document)


def test_demo_default_workflow_validates() -> None:
    document = json.loads(
        (ROOT / "niches/demo/workflows/default.workflow.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(WORKFLOW_SCHEMA).validate(document)


def test_demo_routing_has_purpose_specific_text_routes() -> None:
    document = json.loads(
        (ROOT / "niches/demo/routing/default.routes.json").read_text(encoding="utf-8")
    )
    purposes = {route["purpose"] for route in document["routes"]}
    assert {"demo-writing", "demo-review"} <= purposes


def test_demo_provider_is_deterministic() -> None:
    path = ROOT / "plugins/demo-text-provider/provider.py"
    spec = importlib.util.spec_from_file_location("demo_text_provider", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request: dict[str, Any] = {"messages": [{"role": "user", "content": "hello"}]}
    assert module.generate(request) == module.generate(request)


def test_config_only_demo_prompts_has_no_python_entrypoint() -> None:
    manifest = json.loads(
        (ROOT / "plugins/demo-prompts/plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["runtime"] == {"kind": "config-only"}
    assert not list((ROOT / "plugins/demo-prompts").rglob("*.py"))
