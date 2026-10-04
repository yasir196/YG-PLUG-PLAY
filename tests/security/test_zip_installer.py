from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core.plugin_registry.installer import InstallError, ZipInstaller

SCHEMA = Path("schemas/plugin.schema.json")


def manifest(entrypoint: str = "marker.py") -> dict:
    return {
        "id": "marker-plugin",
        "name": "Marker Plugin",
        "type": "general",
        "version": "1.0.0",
        "plugin_api": "v0",
        "minimum_core": "0.0.1",
        "runtime": {
            "kind": "python-subprocess",
            "python": ">=3.12",
            "entrypoint": entrypoint,
            "lock_file": "uv.lock",
        },
        "requested_trust": "trusted",
        "compatible_niches": ["*"],
        "permissions": [],
        "provides": [
            {
                "capability": "text-generation",
                "executor": "rpc",
                "input": {"contract": "text-generation.request", "version": "^1.0"},
                "output": {"contract": "text-generation.result", "version": "^1.0"},
            }
        ],
    }


def make_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_validation_never_imports_plugin_marker_file(tmp_path: Path) -> None:
    marker = tmp_path / "IMPORTED.txt"
    code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    package = make_zip(
        tmp_path / "marker.zip",
        {
            "plugin.json": json.dumps(manifest()),
            "marker.py": code,
            "uv.lock": "version = 1\n",
        },
    )
    installed = ZipInstaller(tmp_path / "packages", SCHEMA).install(package)
    assert installed.enabled is False
    assert installed.path.is_dir()
    assert not marker.exists()


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "C:/absolute.txt"])
def test_unsafe_zip_paths_are_rejected(tmp_path: Path, name: str) -> None:
    package = make_zip(tmp_path / "unsafe.zip", {name: "bad", "plugin.json": "{}"})
    with pytest.raises(InstallError):
        ZipInstaller(tmp_path / "packages", SCHEMA).install(package)


def test_manifest_is_validated_before_immutable_storage(tmp_path: Path) -> None:
    package = make_zip(tmp_path / "bad.zip", {"plugin.json": "{}"})
    with pytest.raises(InstallError, match="manifest invalid"):
        ZipInstaller(tmp_path / "packages", SCHEMA).install(package)
    assert not list((tmp_path / "packages").rglob("plugin.json"))
