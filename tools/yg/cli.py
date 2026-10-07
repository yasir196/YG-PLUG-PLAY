"""YG package validation and deterministic packing CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from core.plugin_registry import packing
from core.plugin_registry.manifest import PluginManifest

app = typer.Typer(help="YG-PLUG-PLAY developer tools.")
plugin_app = typer.Typer(help="Validate and pack plugin/niche packages.")
channel_app = typer.Typer(help="Manage Channels.")
project_app = typer.Typer(help="Manage Projects and Briefs.")
app.add_typer(plugin_app, name="plugin")
app.add_typer(channel_app, name="channel")
app.add_typer(project_app, name="project")

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SCHEMA = ROOT / "schemas" / "plugin.schema.json"
PackageError = packing.PackageError


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


def _workspace_service():
    from core.config import initialize_data_root
    from core.database import create_sqlite_engine, session_factory
    from core.workspace import WorkspaceService

    layout = initialize_data_root()
    engine = create_sqlite_engine(layout.root / "db" / "core.db")
    return engine, session_factory(engine), WorkspaceService


@channel_app.command("create")
def channel_create(name: str, niche: str, niche_version: str = "1.0.0") -> None:
    engine, factory, service_type = _workspace_service()
    with factory.begin() as session:
        item = service_type(session).create_channel(name, niche, niche_version)
        typer.echo(item.id)
    engine.dispose()


@channel_app.command("list")
def channel_list() -> None:
    engine, factory, service_type = _workspace_service()
    with factory() as session:
        for item in service_type(session).list_channels():
            typer.echo(f"{item.id}\t{item.name}\t{item.niche_id}@{item.niche_version}")
    engine.dispose()


@channel_app.command("open")
def channel_open(channel_id: str) -> None:
    engine, factory, service_type = _workspace_service()
    with factory() as session:
        item = service_type(session).open_channel(channel_id)
        typer.echo(json.dumps({"id": item.id, "name": item.name, "niche": item.niche_id}))
    engine.dispose()


@project_app.command("create")
def project_create(channel_id: str, title: str) -> None:
    engine, factory, service_type = _workspace_service()
    with factory.begin() as session:
        typer.echo(service_type(session).create_project(channel_id, title).id)
    engine.dispose()


@project_app.command("list")
def project_list(channel_id: str) -> None:
    engine, factory, service_type = _workspace_service()
    with factory() as session:
        for item in service_type(session).list_projects(channel_id):
            typer.echo(f"{item.id}\t{item.title}")
    engine.dispose()


@project_app.command("open")
def project_open(project_id: str) -> None:
    engine, factory, service_type = _workspace_service()
    with factory() as session:
        item = service_type(session).open_project(project_id)
        typer.echo(json.dumps({"id": item.id, "title": item.title, "channel_id": item.channel_id}))
    engine.dispose()


@project_app.command("brief")
def project_brief(project_id: str, brief_file: Path) -> None:
    engine, factory, service_type = _workspace_service()
    data = json.loads(brief_file.read_text(encoding="utf-8"))
    with factory.begin() as session:
        brief = service_type(session).save_brief(project_id, data)
        typer.echo(f"{brief.id}\tgeneration={brief.generation}")
    engine.dispose()


if __name__ == "__main__":
    app()
