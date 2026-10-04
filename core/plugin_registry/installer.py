"""Static ZIP installer: validates bytes without importing package code."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from core.database.models import Plugin, PluginVersion
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registries import RuntimeRegistries

MAX_FILES = 500
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024


class InstallError(ValueError):
    pass


@dataclass(frozen=True)
class InstalledPackage:
    manifest: PluginManifest
    sha256: str
    path: Path
    enabled: bool = False


class ZipInstaller:
    def __init__(self, packages_root: Path, schema_path: Path, session: Session | None = None) -> None:
        self.packages_root = packages_root.resolve()
        self.schema_path = schema_path.resolve()
        self.session = session

    def install(self, archive_path: Path) -> InstalledPackage:
        archive_path = archive_path.resolve()
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="yg-stage-") as temp:
            stage = Path(temp)
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                self._validate_members(infos)
                for info in infos:
                    if info.is_dir():
                        continue
                    target = stage / PurePosixPath(info.filename)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
            manifest = self._validate_manifest(stage)
            kind = "niches" if manifest.type == "niche" else "plugins"
            destination = self.packages_root / kind / manifest.id / manifest.version / digest
            if destination.exists():
                self._persist(manifest, digest)
                if self.session is not None:
                    RuntimeRegistries(self.session, self.schema_path.parent).populate(manifest, destination)
                return InstalledPackage(manifest, digest, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(stage, destination)
        self._persist(manifest, digest)
        if self.session is not None:
            RuntimeRegistries(self.session, self.schema_path.parent).populate(manifest, destination)
        return InstalledPackage(manifest, digest, destination)

    def _validate_members(self, infos: list[zipfile.ZipInfo]) -> None:
        files = [item for item in infos if not item.is_dir()]
        if len(files) > MAX_FILES:
            raise InstallError("package exceeds file-count limit")
        total = 0
        for item in files:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise InstallError(f"unsafe ZIP path: {item.filename}")
            if len(path.parts) > 0 and ":" in path.parts[0]:
                raise InstallError(f"absolute ZIP path rejected: {item.filename}")
            if item.file_size > MAX_FILE_BYTES:
                raise InstallError("package member exceeds size limit")
            total += item.file_size
            if total > MAX_TOTAL_BYTES:
                raise InstallError("package exceeds uncompressed size limit")

    def _validate_manifest(self, stage: Path) -> PluginManifest:
        manifest_path = stage / "plugin.json"
        if not manifest_path.is_file():
            raise InstallError("plugin.json missing")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(raw))
        if errors:
            raise InstallError(f"manifest invalid: {errors[0].message}")
        return PluginManifest.model_validate(raw)

    def _persist(self, manifest: PluginManifest, digest: str) -> None:
        if self.session is None:
            return
        plugin = self.session.get(Plugin, manifest.id)
        if plugin is None:
            self.session.add(Plugin(id=manifest.id, kind=manifest.type))
            self.session.flush()
        exists = (
            self.session.query(PluginVersion)
            .filter_by(plugin_id=manifest.id, version=manifest.version, package_sha256=digest)
            .first()
        )
        if exists is None:
            self.session.add(
                PluginVersion(
                    plugin_id=manifest.id,
                    version=manifest.version,
                    package_sha256=digest,
                    manifest_json=manifest.model_dump_json(),
                )
            )
            self.session.flush()
