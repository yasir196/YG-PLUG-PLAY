from __future__ import annotations

from pathlib import Path

import pytest

from core.config import (
    DATA_ROOT_ENV,
    DataRootError,
    cloud_sync_provider,
    default_data_root,
    initialize_data_root,
    resolve_data_root,
)
from core.config.data_root import DATA_SUBDIRECTORIES


def test_default_path_uses_localappdata() -> None:
    env = {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}
    assert default_data_root(environ=env) == (Path(r"C:\Users\Test\AppData\Local") / "YG-PLUG-PLAY")


def test_override_takes_precedence_and_creates_subfolders(tmp_path: Path) -> None:
    install = tmp_path / "repo"
    install.mkdir()
    override = tmp_path / "state"

    layout = initialize_data_root(
        install_root=install,
        override=override,
        environ={"LOCALAPPDATA": str(tmp_path / "local")},
    )

    assert layout.root == override.resolve()
    for relative in DATA_SUBDIRECTORIES:
        assert (layout.root / relative).is_dir()


def test_environment_override_is_supported(tmp_path: Path) -> None:
    configured = tmp_path / "custom-data"
    env = {
        "LOCALAPPDATA": str(tmp_path / "local"),
        DATA_ROOT_ENV: str(configured),
    }
    assert resolve_data_root(environ=env) == configured.resolve()


@pytest.mark.parametrize(
    ("path", "provider"),
    [
        (Path(r"C:\Users\Test\OneDrive\YG-PLUG-PLAY"), "OneDrive"),
        (Path(r"C:\Users\Test\Dropbox\YG-PLUG-PLAY"), "Dropbox"),
        (Path(r"C:\Users\Test\Google Drive\YG-PLUG-PLAY"), "Google Drive"),
    ],
)
def test_cloud_sync_detection(path: Path, provider: str) -> None:
    assert cloud_sync_provider(path) == provider


def test_cloud_sync_path_warns(tmp_path: Path) -> None:
    install = tmp_path / "repo"
    install.mkdir()
    cloud_root = tmp_path / "OneDrive" / "YG-PLUG-PLAY"

    with pytest.warns(RuntimeWarning, match="OneDrive"):
        initialize_data_root(install_root=install, override=cloud_root)


def test_in_repo_data_root_is_rejected(tmp_path: Path) -> None:
    install = tmp_path / "repo"
    install.mkdir()

    with pytest.raises(DataRootError, match="outside"):
        initialize_data_root(install_root=install, override=install / "data")


def test_urdu_unicode_path_is_created(tmp_path: Path) -> None:
    install = tmp_path / "repo"
    install.mkdir()
    urdu_root = tmp_path / "میرا ڈیٹا" / "وائی جی"

    layout = initialize_data_root(install_root=install, override=urdu_root)

    assert layout.root == urdu_root.resolve()
    assert layout.artifacts.is_dir()
    assert layout.runtime.is_dir()
