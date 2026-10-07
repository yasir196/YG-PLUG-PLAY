"""Deterministic plugin/niche package validation and packing."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from core.plugin_registry.manifest import PluginManifest, PythonRuntime

IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", "dist", ".venv"}


class PackageError(ValueError):
    """Package validation failed."""


def _manifest_path(package_dir: Path) -> Path:
    path = package_dir / "plugin.json"
    if not path.is_file():
        raise PackageError(f"missing manifest: {path}")
    return path


def validate_package(package_dir: Path, *, schema_path: Path) -> PluginManifest:
    """Validate manifest, referenced resources, and config-only invariants."""

    package_dir = package_dir.resolve()
    raw = json.loads(_manifest_path(package_dir).read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise PackageError(f"plugin.schema.json validation failed: {detail}")

    manifest = PluginManifest.model_validate(raw)
    referenced: list[str] = []
    if manifest.settings_schema:
        referenced.append(manifest.settings_schema)
    if isinstance(manifest.runtime, PythonRuntime):
        referenced.extend([manifest.runtime.entrypoint, manifest.runtime.lock_file])
    for provided in manifest.provides:
        if provided.prompt:
            referenced.append(provided.prompt)
        referenced.extend(rule.path for rule in provided.rules)

    for relative in referenced:
        target = (package_dir / relative).resolve()
        if not target.is_relative_to(package_dir) or not target.is_file():
            raise PackageError(f"missing or unsafe referenced resource: {relative}")

    if manifest.runtime.kind == "config-only" and any(package_dir.rglob("*.py")):
        raise PackageError("config-only package must not contain Python files")
    return manifest


def _package_files(package_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in package_dir.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_PARTS for part in path.relative_to(package_dir).parts)
    )


def pack_package(package_dir: Path, dist_dir: Path, *, schema_path: Path) -> tuple[Path, str]:
    """Validate and create a reproducible ZIP, returning path and SHA-256."""

    package_dir = package_dir.resolve()
    manifest = validate_package(package_dir, schema_path=schema_path)
    output_dir = dist_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{manifest.id}-{manifest.version}.zip"

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in _package_files(package_dir):
            relative = source.relative_to(package_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return destination, digest
