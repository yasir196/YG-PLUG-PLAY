"""Minimal sandboxed prompt executor for prompt-driven capabilities."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from jinja2.sandbox import SandboxedEnvironment
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from core.database.models import Contract
from core.routing import PurposeRouter


class PromptExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class PromptResult:
    data: Any
    provider: str
    model: str | None
    prompt_sha256: str
    rule_hashes: tuple[str, ...]


class PromptExecutor:
    def __init__(self, session: Session, router: PurposeRouter) -> None:
        self.session = session
        self.router = router
        self.env = SandboxedEnvironment(autoescape=False)
        self.env.filters.clear()
        self.env.globals.clear()
        self.env.filters.update({"lower": str.lower, "upper": str.upper, "trim": str.strip})

    def execute(
        self,
        *,
        channel_id: str,
        capability: Any,
        plugin_root: Path,
        niche_root: Path | None,
        channel_prompt: Path | None,
        context: dict[str, Any],
        provider_root: Path,
        explicit_options: dict[str, Any] | None = None,
    ) -> PromptResult:
        prompt_path = self._prompt_path(capability.prompt, plugin_root, niche_root, channel_prompt)
        prompt_text = prompt_path.read_text(encoding="utf-8")
        rule_hashes: list[str] = []
        prompt_context: list[str] = []
        validators: list[dict[str, Any]] = []
        for rule in capability.rules or []:
            path = self._resource(rule.path, plugin_root, niche_root)
            raw = path.read_text(encoding="utf-8")
            rule_hashes.append(self._hash(raw))
            if rule.type == "prompt-context":
                prompt_context.append(raw)
            else:
                validators.append(json.loads(raw))
        rendered = self.env.from_string(prompt_text).render(**context)
        if prompt_context:
            rendered += "\n\nRULE CONTEXT:\n" + "\n\n".join(prompt_context)
        prompt_hash = self._hash(rendered)
        route = self.router.resolve(
            channel_id=channel_id,
            capability=capability.uses.capability,
            purpose=capability.uses.purpose,
            required_features=(
                capability.requirements.model_dump(exclude_none=True)
                if capability.requirements
                else {}
            ),
            explicit_options=explicit_options,
        )
        request = {"messages": [{"role": "user", "content": rendered}], **route.options}
        response = self._call_demo_provider(provider_root, request)
        data: Any = response.get("structured") or response.get("content")
        self._validate_rules(data, validators)
        self._validate_contract(capability.output.contract, data)
        return PromptResult(data, route.plugin_id, route.model, prompt_hash, tuple(rule_hashes))

    @staticmethod
    def _prompt_path(
        relative: str, plugin_root: Path, niche_root: Path | None, override: Path | None
    ) -> Path:
        if override is not None and override.is_file():
            return override
        if niche_root is not None:
            candidate = niche_root / relative
            if candidate.is_file():
                return candidate
        candidate = plugin_root / relative
        if candidate.is_file():
            return candidate
        raise PromptExecutionError("prompt resource not found")

    @staticmethod
    def _resource(relative: str, plugin_root: Path, niche_root: Path | None) -> Path:
        for root in (niche_root, plugin_root):
            if root is not None:
                candidate = (root / relative).resolve()
                if candidate.is_relative_to(root.resolve()) and candidate.is_file():
                    return candidate
        raise PromptExecutionError(f"rule resource not found: {relative}")

    def _validate_contract(self, contract_id: str, data: Any) -> None:
        contract = self.session.get(Contract, contract_id)
        if contract is not None:
            Draft202012Validator(json.loads(contract.schema_json)).validate(data)

    @staticmethod
    def _validate_rules(data: Any, validators: list[dict[str, Any]]) -> None:
        for rule in validators:
            kind = rule.get("kind")
            if kind == "json-schema":
                Draft202012Validator(rule["schema"]).validate(data)
            elif kind == "required-fields":
                if not isinstance(data, dict):
                    raise PromptExecutionError("required-fields validator needs object output")
                missing = [key for key in rule["fields"] if key not in data]
                if missing:
                    raise PromptExecutionError("missing required fields: " + ",".join(missing))
            elif kind == "word-count":
                count = len(str(data).split())
                if count < rule.get("min", 0) or count > rule.get("max", 2**31):
                    raise PromptExecutionError("word-count validator failed")

    @staticmethod
    def _call_demo_provider(provider_root: Path, request: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.run(
            ["python", str(provider_root / "provider.py")],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        )
        value = json.loads(process.stdout)
        if not isinstance(value, dict):
            raise PromptExecutionError("provider response must be a JSON object")
        return cast(dict[str, Any], value)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
