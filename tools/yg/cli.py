"""YG package validation and deterministic packing CLI."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Annotated

import typer
from jsonschema import Draft202012Validator

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
IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", "dist", ".venv"}


class PackageError(ValueError):
    """Package validation failed."""


def _manifest_path(package_dir: Path) -> Path:
    path = package_dir / "plugin.json"
    if not path.is_file():
        raise PackageError(f"missing manifest: {path}")
    return path


def validate_package(package_dir: Path) -> PluginManifest:
    """Validate manifest, referenced resources, and config-only invariants."""

    package_dir = package_dir.resolve()
    raw = json.loads(_manifest_path(package_dir).read_text(encoding="utf-8"))
    schema = json.loads(PLUGIN_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise PackageError(f"plugin.schema.json validation failed: {detail}")

    manifest = PluginManifest.model_validate(raw)
    referenced: list[str] = []
    if manifest.settings_schema:
        referenced.append(manifest.settings_schema)
    if manifest.runtime.kind == "python-subprocess":
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


def pack_package(package_dir: Path, dist_dir: Path | None = None) -> tuple[Path, str]:
    """Validate and create a reproducible ZIP, returning path and SHA-256."""

    package_dir = package_dir.resolve()
    manifest = validate_package(package_dir)
    output_dir = (dist_dir or ROOT / "dist").resolve()
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
