"""Channel, project and project-brief application service."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.audit import AuditEvent, AuditService
from core.database.models import Channel, Niche, PluginVersion, Project, ProjectBrief
from core.plugin_registry.providers import latest_package
from core.plugin_registry.registry import PluginRegistry, RegistryError
from core.workspace.defaults import materialize_demo_defaults

ROOT = Path(__file__).resolve().parents[2]
BRIEF_SCHEMA = json.loads(
    (ROOT / "contracts/standard/schemas/project.brief.schema.json").read_text(encoding="utf-8")
)

# Config-only packages a new Channel of a niche requires (Cycle C-delta).
# Assignment pins version only; identity is the current package (E15).
REQUIRED_CHANNEL_PACKAGES: dict[str, tuple[tuple[str, str], ...]] = {
    "demo": (("demo-prompts", "1.0.0"),),
}


class ChannelCreationError(ValueError):
    """Channel creation rejected: required installed state is missing or invalid."""


class WorkspaceService:
    def __init__(
        self, session: Session, actor: str = "admin", correlation_id: str | None = None
    ) -> None:
        self.session = session
        self.actor = actor
        self.correlation_id = correlation_id
        self.audit = AuditService(session)

    def create_channel(self, name: str, niche_id: str, niche_version: str) -> Channel:
        # Validate before adding anything: Channel creation consumes installed
        # state and never invents Niche rows or package identities.
        required = self._installed_channel_packages(niche_id, niche_version)
        channel = Channel(
            id=uuid.uuid4().hex,
            name=name,
            niche_id=niche_id,
            niche_version=niche_version,
        )
        self.session.add(channel)
        self.session.flush()
        if niche_id == "demo":
            materialize_demo_defaults(self.session, channel.id, ROOT)
        registry = PluginRegistry(self.session)
        for item in required:
            try:
                registry.assign(
                    channel.id, item.plugin_id, item.version, item.package_sha256, enabled=True
                )
            except RegistryError as exc:
                raise ChannelCreationError(str(exc)) from exc
        self.audit.record(
            AuditEvent(
                self.actor,
                "channel.create",
                "channel",
                channel.id,
                correlation_id=self.correlation_id,
            )
        )
        return channel

    def _installed_channel_packages(
        self, niche_id: str, niche_version: str
    ) -> list[PluginVersion]:
        niche = self.session.get(Niche, niche_id)
        if niche is None:
            raise ChannelCreationError(f"niche {niche_id} is not registered")
        if niche.version != niche_version:
            raise ChannelCreationError("requested niche pin is not installed")
        if latest_package(self.session, niche_id, niche_version) is None:
            raise ChannelCreationError(f"niche package {niche_id}@{niche_version} is not installed")
        required: list[PluginVersion] = []
        for plugin_id, version in REQUIRED_CHANNEL_PACKAGES.get(niche_id, ()):
            item = latest_package(self.session, plugin_id, version)
            if item is None:
                raise ChannelCreationError(f"required package {plugin_id}@{version} is not installed")
            required.append(item)
        return required

    def list_channels(self) -> list[Channel]:
        return list(self.session.scalars(select(Channel).order_by(Channel.created_at)))

    def open_channel(self, channel_id: str) -> Channel:
        channel = self.session.get(Channel, channel_id)
        if channel is None:
            raise ValueError("channel not found")
        return channel

    def create_project(self, channel_id: str, title: str) -> Project:
        self.open_channel(channel_id)
        project = Project(id=uuid.uuid4().hex, channel_id=channel_id, title=title)
        self.session.add(project)
        self.session.flush()
        self.audit.record(
            AuditEvent(
                self.actor,
                "project.create",
                "project",
                project.id,
                correlation_id=self.correlation_id,
            )
        )
        return project

    def list_projects(self, channel_id: str) -> list[Project]:
        self.open_channel(channel_id)
        return list(
            self.session.scalars(
                select(Project).where(Channel.id == channel_id).order_by(Project.created_at)
            )
        )

    def open_project(self, project_id: str) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError("project not found")
        return project

    def save_brief(self, project_id: str, data: dict[str, Any]) -> ProjectBrief:
        self.open_project(project_id)
        Draft202012Validator(BRIEF_SCHEMA).validate(data)
        latest = self.session.scalar(
            select(ProjectBrief.generation)
            .where(ProjectBrief.project_id == project_id)
            .order_by(ProjectBrief.generation.desc())
            .limit(1)
        )
        brief = ProjectBrief(
            id=uuid.uuid4().hex,
            project_id=project_id,
            generation=(latest or 0) + 1,
            contract_version="1.0.0",
            data_json=json.dumps(data, ensure_ascii=False, sort_keys=True),
        )
        self.session.add(brief)
        self.session.flush()
        self.audit.record(
            AuditEvent(
                self.actor,
                "project-brief.write",
                "project-brief",
                brief.id,
                correlation_id=self.correlation_id,
            )
        )
        return brief

    def open_brief(self, project_id: str) -> ProjectBrief:
        brief = self.session.scalar(
            select(ProjectBrief)
            .where(ProjectBrief.project_id == project_id)
            .order_by(ProjectBrief.generation.desc())
            .limit(1)
        )
        if brief is None:
            raise ValueError("project brief not found")
        return brief
