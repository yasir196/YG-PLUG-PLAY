"""Explicit, idempotent installation of bundled demo packages (checkout mode)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from core.config.data_root import DataRootLayout
from core.database.models import Niche
from core.plugin_registry.installer import InstalledPackage, ZipInstaller
from core.plugin_registry.packing import pack_package

BUNDLED_DEMO_PACKAGES = (
    ("niches", "demo"),
    ("plugins", "demo-prompts"),
    ("plugins", "demo-text-provider"),
)


class BootstrapError(ValueError):
    pass


def install_bundled_demo_packages(
    session: Session, layout: DataRootLayout, *, source_root: Path
) -> list[InstalledPackage]:
    """Pack and install bundled demo packages in namespace-owner order.

    Installs package bytes and registry rows only: no trust grant and no Channel
    assignment. Re-running with identical sources is a no-op. Caller commits.
    """

    source_root = source_root.resolve()
    schema_path = source_root / "schemas" / "plugin.schema.json"
    installer = ZipInstaller(layout.packages, schema_path, session)
    scratch = layout.runtime / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    installed: list[InstalledPackage] = []
    with tempfile.TemporaryDirectory(prefix="yg-bootstrap-", dir=scratch) as temp:
        for kind, package_id in BUNDLED_DEMO_PACKAGES:
            package_dir = source_root / kind / package_id
            dist_dir = Path(temp) / package_id
            archive, _digest = pack_package(package_dir, dist_dir, schema_path=schema_path)
            item = installer.install(archive)
            if item.manifest.id != package_id:
                raise BootstrapError(f"bundled package id mismatch: {package_id}")
            if item.manifest.type == "niche":
                _pin_niche(session, item)
            installed.append(item)
    return installed


def _pin_niche(session: Session, item: InstalledPackage) -> None:
    niche = session.get(Niche, item.manifest.id)
    if niche is None:
        session.add(Niche(id=item.manifest.id, version=item.manifest.version))
        session.flush()
    elif niche.version != item.manifest.version:
        raise BootstrapError(f"niche {item.manifest.id} already pinned to {niche.version}")
