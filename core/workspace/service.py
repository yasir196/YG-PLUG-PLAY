"""Channel, project and project-brief application service."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Channel, Niche, Project, ProjectBrief

ROOT = Path(__file__).resolve().parents[2]
BRIEF_SCHEMA = json.loads(
    (ROOT / "contracts/standard/schemas/project.brief.schema.json").read_text(encoding="utf-8")
)


class WorkspaceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_channel(self, name: str, niche_id: str, niche_version: str) -> Channel:
        niche = self.session.get(Niche, niche_id)
        if niche is None:
            niche = Niche(id=niche_id, version=niche_version)
            self.session.add(niche)
        elif niche.version != niche_version:
            raise ValueError("requested niche pin is not installed")
        channel = Channel(
            id=uuid.uuid4().hex,
            name=name,
            niche_id=niche_id,
            niche_version=niche_version,
        )
        self.session.add(channel)
        self.session.flush()
        return channel

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
        return project

    def list_projects(self, channel_id: str) -> list[Project]:
        self.open_channel(channel_id)
        return list(
            self.session.scalars(
                select(Project).where(Project.channel_id == channel_id).order_by(Project.created_at)
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
