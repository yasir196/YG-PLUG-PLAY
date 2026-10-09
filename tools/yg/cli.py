"""YG package validation and deterministic packing CLI."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from core.plugin_registry import packing
from core.plugin_registry.manifest import PluginManifest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from core.config import DataRootLayout

PackageError = packing.PackageError

app = typer.Typer(help="YG-PLUG-PLAY developer tools.")
plugin_app = typer.Typer(help="Validate and pack plugin/niche packages.")
channel_app = typer.Typer(help="Manage Channels.")
project_app = typer.Typer(help="Manage Projects and Briefs.")
demo_app = typer.Typer(help="Bundled demo packages (checkout mode).")
app.add_typer(plugin_app, name="plugin")
app.add_typer(channel_app, name="channel")
app.add_typer(project_app, name="project")
app.add_typer(demo_app, name="demo")

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SCHEMA = ROOT / "schemas" / "plugin.schema.json"


def validate_package(package_dir: Path) -> PluginManifest:
    """Validate manifest, referenced resources, and config-only invariants."""

    return packing.validate_package(package_dir, schema_path=PLUGIN_SCHEMA)


def pack_package(package_dir: Path, dist_dir: Path | None = None) -> tuple[Path, str]:
    """Validate and create a reproducible ZIP, returning path and SHA-256."""

    output_dir = dist_dir or ROOT / "dist"
    return packing.pack_package(package_dir, output_dir, schema_path=PLUGIN_SCHEMA)


@plugin_app.command("validate")
def plugin_validate(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False, resolve_path=True)],
) -> None:
    """Validate a plugin or niche package."""

    try:
        manifest = validate_package(package_dir)
    except (PackageError, json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"VALID: {manifest.id} {manifest.version}")


@plugin_app.command("pack")
def plugin_pack(
    package_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False, resolve_path=True)],
    dist_dir: Annotated[Path | None, typer.Option("--dist")] = None,
) -> None:
    """Validate and pack a plugin or niche package."""

    try:
        destination, digest = pack_package(package_dir, dist_dir)
    except (PackageError, json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(destination))
    typer.echo(f"sha256:{digest}")


def _fail(exc: Exception) -> NoReturn:
    typer.echo(f"ERROR: {exc}", err=True)
    raise typer.Exit(code=1) from exc


@contextmanager
def _workspace(*, write: bool = False) -> Iterator[tuple[DataRootLayout, Session]]:
    """Open the data root DB; ValueError -> rollback, `ERROR: ...`, exit 1."""

    from core.config import initialize_data_root
    from core.database import create_sqlite_engine, session_factory
    from core.database.models import Base

    try:
        layout = initialize_data_root(install_root=ROOT)
    except ValueError as exc:
        _fail(exc)
    engine = create_sqlite_engine(layout.db / "core.db")
    try:
        Base.metadata.create_all(engine)
        factory = session_factory(engine)
        opener = factory.begin if write else factory
        with opener() as session:
            yield layout, session
    except ValueError as exc:
        _fail(exc)
    finally:
        engine.dispose()


@demo_app.command("bootstrap")
def demo_bootstrap() -> None:
    """Install bundled demo packages into the data root (idempotent, checkout mode)."""

    from core.workspace.bootstrap import install_bundled_demo_packages

    with _workspace(write=True) as (layout, session):
        installed = install_bundled_demo_packages(session, layout, source_root=ROOT)
    for item in installed:
        typer.echo(f"{item.manifest.id} {item.manifest.version} sha256:{item.sha256}")


@channel_app.command("create")
def channel_create(name: str, niche: str, niche_version: str = "1.0.0") -> None:
    from core.workspace import WorkspaceService

    with _workspace(write=True) as (_layout, session):
        channel_id = WorkspaceService(session).create_channel(name, niche, niche_version).id
    typer.echo(channel_id)


@channel_app.command("list")
def channel_list() -> None:
    from core.workspace import WorkspaceService

    with _workspace() as (_layout, session):
        for item in WorkspaceService(session).list_channels():
            typer.echo(f"{item.id}\t{item.name}\t{item.niche_id}@{item.niche_version}")


@channel_app.command("open")
def channel_open(channel_id: str) -> None:
    from core.workspace import WorkspaceService

    with _workspace() as (_layout, session):
        item = WorkspaceService(session).open_channel(channel_id)
        typer.echo(json.dumps({"id": item.id, "name": item.name, "niche": item.niche_id}))


@project_app.command("create")
def project_create(channel_id: str, title: str) -> None:
    from core.workspace import WorkspaceService

    with _workspace(write=True) as (_layout, session):
        project_id = WorkspaceService(session).create_project(channel_id, title).id
    typer.echo(project_id)


@project_app.command("list")
def project_list(channel_id: str) -> None:
    from core.workspace import WorkspaceService

    with _workspace() as (_layout, session):
        for item in WorkspaceService(session).list_projects(channel_id):
            typer.echo(f"{item.id}\t{item.title}")


@project_app.command("open")
def project_open(project_id: str) -> None:
    from core.workspace import WorkspaceService

    with _workspace() as (_layout, session):
        item = WorkspaceService(session).open_project(project_id)
        typer.echo(json.dumps({"id": item.id, "title": item.title, "channel_id": item.channel_id}))


@project_app.command("brief")
def project_brief(project_id: str, brief_file: Path) -> None:
    from core.workspace import WorkspaceService

    data = json.loads(brief_file.read_text(encoding="utf-8"))
    with _workspace(write=True) as (_layout, session):
        brief = WorkspaceService(session).save_brief(project_id, data)
        line = f"{brief.id}\tgeneration={brief.generation}"
    typer.echo(line)


if __name__ == "__main__":
    app()
