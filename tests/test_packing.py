"""Core packing contract: deterministic ZIP identity shared with the installer."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.plugin_registry.installer import ZipInstaller
from tools.yg.cli import pack_package as cli_pack_package

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "plugin.schema.json"
PACKAGES = [
    ROOT / "niches" / "demo",
    ROOT / "plugins" / "demo-prompts",
    ROOT / "plugins" / "demo-text-provider",
]


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_core_pack_matches_cli_pack(package: Path, tmp_path: Path) -> None:
    from core.plugin_registry.packing import pack_package

    core_archive, core_digest = pack_package(package, tmp_path / "core", schema_path=SCHEMA)
    cli_archive, cli_digest = cli_pack_package(package, tmp_path / "cli")
    assert core_archive.name == cli_archive.name
    assert core_digest == cli_digest
    assert core_digest == hashlib.sha256(core_archive.read_bytes()).hexdigest()


def test_core_pack_requires_dist_dir() -> None:
    from core.plugin_registry.packing import pack_package

    with pytest.raises(TypeError):
        pack_package(PACKAGES[1], schema_path=SCHEMA)


def test_core_validate_uses_given_schema(tmp_path: Path) -> None:
    from core.plugin_registry.packing import PackageError, validate_package

    strict = tmp_path / "strict.schema.json"
    strict.write_text('{"type": "object", "required": ["never-present"]}', encoding="utf-8")
    with pytest.raises(PackageError, match="validation failed"):
        validate_package(PACKAGES[1], schema_path=strict)


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_installer_identity_equals_pack_digest(package: Path, tmp_path: Path) -> None:
    from core.plugin_registry.packing import pack_package

    archive, digest = pack_package(package, tmp_path / "dist", schema_path=SCHEMA)
    installed = ZipInstaller(tmp_path / "packages", SCHEMA).install(archive)
    assert installed.sha256 == digest
    assert installed.path.name == digest
    assert installed.path.is_relative_to((tmp_path / "packages").resolve())
