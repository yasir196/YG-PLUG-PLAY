from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tools.yg.cli import app, pack_package, validate_package

runner = CliRunner()
PACKAGES = [
    Path("niches/demo"),
    Path("plugins/demo-text-provider"),
    Path("plugins/demo-prompts"),
]


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_demo_package_validates(package: Path) -> None:
    manifest = validate_package(package)
    assert manifest.id


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_demo_package_packs_with_sha256(package: Path, tmp_path: Path) -> None:
    archive, digest = pack_package(package, tmp_path)
    assert archive.name.endswith("-1.0.0.zip")
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as packed:
        assert "plugin.json" in packed.namelist()


def test_cli_validate_demo_package() -> None:
    result = runner.invoke(app, ["plugin", "validate", "plugins/demo-prompts"])
    assert result.exit_code == 0
    assert "VALID: demo-prompts 1.0.0" in result.stdout


def test_cli_pack_demo_package(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["plugin", "pack", "plugins/demo-text-provider", "--dist", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "demo-text-provider-1.0.0.zip" in result.stdout
    assert "sha256:" in result.stdout
