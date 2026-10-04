"""Capability, contract and namespace registration with ownership enforcement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from core.database.models import Capability, Contract, NamespaceRegistry
from core.plugin_registry.manifest import PluginManifest


class RegistryConflict(ValueError):
    pass


class RuntimeRegistries:
    def __init__(self, session: Session, schemas_root: Path) -> None:
        self.session = session
        self.schemas_root = schemas_root

    def populate(self, manifest: PluginManifest, package_root: Path) -> None:
        self._claim_namespace(manifest)
        delegations = set(manifest.namespace_delegations_requested)
        for path in sorted((package_root / "contracts").glob("*.json")) if (package_root / "contracts").exists() else []:
            item = json.loads(path.read_text(encoding="utf-8"))
            self._validate("contract.schema.json", item)
            self._authorize_id(manifest, item["id"], delegations)
            self._register_contract(item)
        for path in sorted((package_root / "capabilities").glob("*.json")) if (package_root / "capabilities").exists() else []:
            item = json.loads(path.read_text(encoding="utf-8"))
            self._validate("capability.schema.json", item)
            self._authorize_id(manifest, item["id"], delegations)
            self._register_capability(item)
        # Manifest-provided capabilities are registrations too.
        for provided in manifest.provides:
            self._authorize_id(manifest, provided.capability, delegations)
            item = {
                "id": provided.capability,
                "version": manifest.version,
                "input": provided.input.model_dump(by_alias=True),
                "output": provided.output.model_dump(by_alias=True),
            }
            self._register_capability(item)

    def _claim_namespace(self, manifest: PluginManifest) -> None:
        existing = self.session.get(NamespaceRegistry, manifest.id)
        if existing is not None and (existing.owner_id != manifest.id or existing.owner_type != manifest.type):
            raise RegistryConflict(f"namespace {manifest.id} already owned")
        if existing is None:
            self.session.add(
                NamespaceRegistry(
                    namespace=manifest.id,
                    owner_type=manifest.type,
                    owner_id=manifest.id,
                )
            )
            self.session.flush()

    def _authorize_id(
        self, manifest: PluginManifest, identity: str, requested: set[str]
    ) -> None:
        namespace = identity.split("/", 1)[0] if "/" in identity else None
        if namespace is None:
            return
        owner = self.session.get(NamespaceRegistry, namespace)
        if owner is None:
            raise RegistryConflict(f"namespace {namespace} has no owner")
        if owner.owner_id == manifest.id:
            return
        # Errata E1: a compatible niche package may register in that niche's
        # namespace; a general plugin needs explicit delegation request and
        # compatibility with the owning niche. Ownership never changes.
        compatible = any(
            getattr(item, "id", None) == namespace for item in manifest.compatible_niches if item != "*"
        )
        if manifest.type == "niche" and compatible and owner.owner_type == "niche":
            return
        if namespace in requested and compatible and owner.owner_type == "niche":
            return
        raise RegistryConflict(f"{manifest.id} has no authority for namespace {namespace}")

    def _register_capability(self, item: dict[str, Any]) -> None:
        existing = self.session.get(Capability, item["id"])
        payload = json.dumps(item, sort_keys=True)
        if existing is not None:
            if existing.version != item["version"] or existing.schema_json != payload:
                raise RegistryConflict(f"capability conflict: {item['id']}")
            return
        self.session.add(Capability(id=item["id"], version=item["version"], schema_json=payload))
        self.session.flush()

    def _register_contract(self, item: dict[str, Any]) -> None:
        existing = self.session.get(Contract, item["id"])
        payload = json.dumps(item["schema"], sort_keys=True)
        if existing is not None:
            if existing.version != item["version"] or existing.schema_json != payload:
                raise RegistryConflict(f"contract conflict: {item['id']}")
            return
        self.session.add(Contract(id=item["id"], version=item["version"], schema_json=payload))
        self.session.flush()

    def _validate(self, schema_name: str, item: dict[str, Any]) -> None:
        schema = json.loads((self.schemas_root / schema_name).read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(item))
        if errors:
            raise RegistryConflict(f"{schema_name} validation failed: {errors[0].message}")
