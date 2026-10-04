"""Windows-first mutable data-root configuration.

Mutable application state must live outside the source/install tree.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT_ENV = "YG_DATA_ROOT"
APP_DIR_NAME = "YG-PLUG-PLAY"

DATA_SUBDIRECTORIES = (
    "db",
    "packages",
    "packages/plugins",
    "packages/niches",
    "artifacts",
    "plugin-data",
    "prompts",
    "runtime",
    "runtime/envs",
    "runtime/scratch",
    "wheelhouse",
    "exports",
    "backups",
    "logs",
)

_CLOUD_MARKERS = {
    "onedrive": "OneDrive",
    "dropbox": "Dropbox",
    "google drive": "Google Drive",
    "googledrive": "Google Drive",
}


class DataRootError(ValueError):
    """Raised when the configured data root violates a hard safety rule."""


@dataclass(frozen=True, slots=True)
class DataRootLayout:
    """Resolved mutable application directories."""

    root: Path

    def path(self, relative: str) -> Path:
        return self.root / Path(relative)

    @property
    def db(self) -> Path:
        return self.root / "db"

    @property
    def packages(self) -> Path:
        return self.root / "packages"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def plugin_data(self) -> Path:
        return self.root / "plugin-data"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def prompts(self) -> Path:
        return self.root / "prompts"

    @property
    def wheelhouse(self) -> Path:
        return self.root / "wheelhouse"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"


def default_data_root(*, environ: Mapping[str, str] | None = None) -> Path:
    """Return the canonical Windows local-app-data root.

    LOCALAPPDATA is required rather than silently falling back into the repository.
    Tests and non-Windows development can supply it explicitly.
    """

    env = os.environ if environ is None else environ
    local_app_data = env.get("LOCALAPPDATA")
    if not local_app_data:
        raise DataRootError("LOCALAPPDATA is not set; configure YG_DATA_ROOT explicitly.")
    return Path(local_app_data).expanduser() / APP_DIR_NAME


def resolve_data_root(
    override: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve explicit override, environment override, or Windows default."""

    env = os.environ if environ is None else environ
    configured = override if override is not None else env.get(DATA_ROOT_ENV)
    root = Path(configured).expanduser() if configured else default_data_root(environ=env)
    return root.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def reject_inside_install(data_root: Path, install_root: Path) -> None:
    """Reject mutable data nested anywhere under the source/install directory."""

    root = data_root.resolve(strict=False)
    install = install_root.resolve(strict=False)
    if root == install or _is_relative_to(root, install):
        raise DataRootError(
            f"Data root must be outside the repository/install directory: {install}"
        )


def cloud_sync_provider(path: Path) -> str | None:
    """Return a recognized cloud-sync provider when path is inside its folder."""

    for part in path.resolve(strict=False).parts:
        provider = _CLOUD_MARKERS.get(part.casefold())
        if provider is not None:
            return provider
    return None


def initialize_data_root(
    *,
    install_root: Path,
    override: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> DataRootLayout:
    """Resolve, validate, warn, and create the mutable directory layout."""

    root = resolve_data_root(override, environ=environ)
    reject_inside_install(root, install_root)

    provider = cloud_sync_provider(root)
    if provider is not None:
        warnings.warn(
            f"YG-PLUG-PLAY data root is inside {provider}; SQLite/runtime data should "
            "not be cloud-synced.",
            RuntimeWarning,
            stacklevel=2,
        )

    root.mkdir(parents=True, exist_ok=True)
    for relative in DATA_SUBDIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)

    return DataRootLayout(root=root)
