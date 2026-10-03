"""Typed model for plugin.schema.json.

Pydantic validation mirrors the manifest's structural constraints. Core semantic
validation remains authoritative for namespace ownership, grants, and collisions.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PLUGIN_ID = r"^(?!(?:core|system|project|channel|yg)$)(?!yg-)[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
KEBAB_ID = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
CAPABILITY_ID = r"^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
CONTRACT_ID = (
    r"^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?"
    r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*$"
)
EVENT_ID = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$"
SEMVER = r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"

PluginId = Annotated[str, Field(pattern=PLUGIN_ID)]
KebabId = Annotated[str, Field(pattern=KEBAB_ID)]
CapabilityId = Annotated[str, Field(pattern=CAPABILITY_ID)]
ContractId = Annotated[str, Field(pattern=CONTRACT_ID)]
EventId = Annotated[str, Field(pattern=EVENT_ID)]
SemVer = Annotated[str, Field(pattern=SEMVER)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PythonRuntime(StrictModel):
    kind: Literal["python-subprocess"]
    python: str
    entrypoint: str
    lock_file: str


class ConfigOnlyRuntime(StrictModel):
    kind: Literal["config-only"]


Runtime = PythonRuntime | ConfigOnlyRuntime


class NicheCompatibility(StrictModel):
    id: KebabId
    version: str


Permission = Literal[
    "artifact.read",
    "artifact.write",
    "plugin-data.read",
    "plugin-data.write",
    "provider.jobs",
    "events.emit",
    "events.listen",
    "settings.read",
    "network.http",
    "network.sse",
    "network.websocket",
    "credential.raw",
]


class CredentialInject(StrictModel):
    type: Literal["header", "query"]
    name: str


class Credential(StrictModel):
    name: KebabId
    mode: Literal["proxy", "raw"]
    inject: CredentialInject
    allowed_domains: list[str]


class ContractRef(StrictModel):
    contract: ContractId
    version: str


class Rule(StrictModel):
    type: Literal["prompt-context", "validator"]
    path: str


class Uses(StrictModel):
    capability: CapabilityId
    purpose: CapabilityId


class FeatureSet(StrictModel):
    supports_json_schema: bool | None = None
    supports_image_input: bool | None = None
    supports_web_search: bool | None = None
    supports_streaming: bool | None = None
    supports_token_count: bool | None = None
    supports_websocket: bool | None = None
    max_context_tokens: int | None = Field(default=None, ge=1)


class ProvidedCapability(StrictModel):
    capability: CapabilityId
    variant: KebabId | None = None
    input: ContractRef
    output: ContractRef
    executor: Literal["rpc", "prompt"] | None = None
    prompt: str | None = None
    rules: list[Rule] = Field(default_factory=list)
    uses: Uses | None = None
    requirements: FeatureSet | None = None
    features: FeatureSet | None = None

    @model_validator(mode="after")
    def prompt_fields_are_complete(self) -> "ProvidedCapability":
        if self.executor == "prompt" and (not self.prompt or self.uses is None):
            raise ValueError("prompt executor requires prompt and uses")
        return self


class Events(StrictModel):
    emits: list[EventId] = Field(default_factory=list)
    listens: list[EventId] = Field(default_factory=list)


class PluginManifest(StrictModel):
    id: PluginId
    name: str
    type: Literal["general", "niche"]
    version: SemVer
    plugin_api: Literal["v0"]
    minimum_core: SemVer
    runtime: Runtime = Field(discriminator="kind")
    requested_trust: Literal["trusted", "restricted", "untrusted"] = "untrusted"
    compatible_niches: list[str | NicheCompatibility]
    permissions: list[Permission]
    credentials: list[Credential] = Field(default_factory=list)
    provides: list[ProvidedCapability]
    events: Events | None = None
    settings_schema: str | None = None
    namespace_delegations_requested: list[KebabId] = Field(default_factory=list)

    @model_validator(mode="after")
    def niche_manifest_cannot_use_wildcard(self) -> "PluginManifest":
        if self.type == "niche" and "*" in self.compatible_niches:
            raise ValueError("niche plugins cannot declare wildcard compatible_niches")
        return self

    @model_validator(mode="after")
    def validate_compatibility_strings(self) -> "PluginManifest":
        for item in self.compatible_niches:
            if isinstance(item, str) and item != "*":
                raise ValueError("compatible_niches strings may only be '*'")
        return self

    @model_validator(mode="after")
    def validate_relative_paths(self) -> "PluginManifest":
        paths: list[str] = []
        if isinstance(self.runtime, PythonRuntime):
            paths.extend([self.runtime.entrypoint, self.runtime.lock_file])
        if self.settings_schema:
            paths.append(self.settings_schema)
        for provided in self.provides:
            if provided.prompt:
                paths.append(provided.prompt)
            paths.extend(rule.path for rule in provided.rules)
        if any(_unsafe_relative_path(path) for path in paths):
            raise ValueError("manifest resource paths must be safe relative paths")
        return self


def _unsafe_relative_path(path: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:", path)
        or path.startswith(("/", "\\"))
        or ".." in re.split(r"[/\\]", path)
    )
