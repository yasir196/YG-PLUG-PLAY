"""Authenticated Channels, Projects and Briefs API."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database.models import Channel, Project
from core.workspace.service import WorkspaceService


class ChannelCreate(BaseModel):
    name: str
    niche_id: str
    niche_version: str


class ProjectCreate(BaseModel):
    title: str


class BriefCreate(BaseModel):
    data: dict[str, Any]


def build_workspace_router(
    session_dependency: Any, auth_dependency: Any, csrf_dependency: Any
) -> APIRouter:
    router = APIRouter(prefix="/api")

    def service(session: Annotated[Session, Depends(session_dependency)]) -> WorkspaceService:
        return WorkspaceService(session)

    @router.post("/channels", status_code=201, dependencies=[Depends(csrf_dependency)])
    def create_channel(
        body: ChannelCreate, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            channel = svc.create_channel(body.name, body.niche_id, body.niche_version)
            svc.session.commit()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return channel_dict(channel)

    @router.get("/channels", dependencies=[Depends(auth_dependency)])
    def list_channels(svc: Annotated[WorkspaceService, Depends(service)]) -> list[dict[str, Any]]:
        return [channel_dict(item) for item in svc.list_channels()]

    @router.get("/channels/{channel_id}", dependencies=[Depends(auth_dependency)])
    def open_channel(
        channel_id: str, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            return channel_dict(svc.open_channel(channel_id))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post(
        "/channels/{channel_id}/projects", status_code=201, dependencies=[Depends(csrf_dependency)]
    )
    def create_project(
        channel_id: str, body: ProjectCreate, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            project = svc.create_project(channel_id, body.title)
            svc.session.commit()
            return project_dict(project)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/channels/{channel_id}/projects", dependencies=[Depends(auth_dependency)])
    def list_projects(
        channel_id: str, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> list[dict[str, Any]]:
        return [project_dict(item) for item in svc.list_projects(channel_id)]

    @router.get("/projects/{project_id}", dependencies=[Depends(auth_dependency)])
    def open_project(
        project_id: str, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            return project_dict(svc.open_project(project_id))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.put("/projects/{project_id}/brief", dependencies=[Depends(csrf_dependency)])
    def save_brief(
        project_id: str, body: BriefCreate, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            brief = svc.save_brief(project_id, body.data)
            svc.session.commit()
            return {
                "id": brief.id,
                "generation": brief.generation,
                "data": json.loads(brief.data_json),
            }
        except ValidationError as exc:
            raise HTTPException(422, exc.message) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/projects/{project_id}/brief", dependencies=[Depends(auth_dependency)])
    def open_brief(
        project_id: str, svc: Annotated[WorkspaceService, Depends(service)]
    ) -> dict[str, Any]:
        try:
            brief = svc.open_brief(project_id)
            return {
                "id": brief.id,
                "generation": brief.generation,
                "data": json.loads(brief.data_json),
            }
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    return router


def channel_dict(item: Channel) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "niche_id": item.niche_id,
        "niche_version": item.niche_version,
    }


def project_dict(item: Project) -> dict[str, Any]:
    return {
        "id": item.id,
        "channel_id": item.channel_id,
        "title": item.title,
        "status": item.status,
    }
