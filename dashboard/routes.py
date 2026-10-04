"""Server-rendered Jinja2 + HTMX dashboard for the Phase-1a demo flow."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.auth.app import SESSION_COOKIE
from core.auth.service import AuthService, SessionRecord
from core.database.models import (
    ApprovalQueue,
    Channel,
    ChannelPluginAssignment,
    ChannelRoute,
    PluginVersion,
    Project,
    ProjectBrief,
    WorkflowRun,
)
from core.workspace.service import WorkspaceService

TEMPLATES = Jinja2Templates(directory=Path(__file__).with_name("templates"))


async def _form(request: Request) -> dict[str, str]:
    raw = (await request.body()).decode("utf-8")
    return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}


def build_dashboard_router(session_dependency: Any, auth_service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/dashboard")

    def current_session(
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> SessionRecord:
        try:
            return auth_service.require_session(session_token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def context(request: Request, session: SessionRecord | None = None, **values: Any) -> dict[str, Any]:
        return {"request": request, "session": session, **values}

    def require_csrf(form: dict[str, str], session: SessionRecord) -> None:
        supplied = form.get("_csrf", "")
        if not supplied or not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(status_code=403, detail="invalid CSRF token")

    @router.get("", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/dashboard/channels", status_code=303)

    @router.get("/login", response_class=HTMLResponse)
    def login(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "login.html",
            context(request, setup_required=auth_service.setup_required),
        )

    @router.post("/setup")
    async def setup(request: Request) -> RedirectResponse:
        form = await _form(request)
        try:
            auth_service.setup_admin(form.get("password", ""))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse("/dashboard/login", status_code=303)

    @router.post("/login")
    async def login_submit(request: Request) -> RedirectResponse:
        form = await _form(request)
        try:
            token, _csrf = auth_service.authenticate(form.get("password", ""))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        response = RedirectResponse("/dashboard/channels", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, secure=False, samesite="strict", path="/"
        )
        return response

    @router.post("/logout")
    async def logout(
        request: Request,
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        session: Annotated[SessionRecord, Depends(current_session)] = None,
    ) -> RedirectResponse:
        form = await _form(request)
        require_csrf(form, session)
        auth_service.logout(session_token)
        response = RedirectResponse("/dashboard/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @router.get("/channels", response_class=HTMLResponse)
    def channels(
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        rows = db.scalars(select(Channel).order_by(Channel.created_at)).all()
        return TEMPLATES.TemplateResponse(
            request, "channels.html", context(request, session, channels=rows)
        )

    @router.post("/channels")
    async def create_channel(
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> RedirectResponse:
        form = await _form(request)
        require_csrf(form, session)
        service = WorkspaceService(db)
        try:
            channel = service.create_channel(
                form.get("name", ""), form.get("niche_id", ""), form.get("niche_version", "")
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RedirectResponse(f"/dashboard/channels/{channel.id}", status_code=303)

    @router.get("/channels/{cid}", response_class=HTMLResponse)
    def channel(
        cid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        item = db.get(Channel, cid)
        if item is None:
            raise HTTPException(status_code=404, detail="channel not found")
        project_count = len(
            db.scalars(select(Project).where(Project.channel_id == cid)).all()
        )
        return TEMPLATES.TemplateResponse(
            request,
            "channel.html",
            context(request, session, channel=item, project_count=project_count),
        )

    @router.get("/channels/{cid}/plugins", response_class=HTMLResponse)
    def plugins(
        cid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        if db.get(Channel, cid) is None:
            raise HTTPException(status_code=404, detail="channel not found")
        rows = db.scalars(select(PluginVersion).order_by(PluginVersion.plugin_id)).all()
        assignments = {
            item.plugin_id: item
            for item in db.scalars(
                select(ChannelPluginAssignment).where(ChannelPluginAssignment.channel_id == cid)
            )
        }
        return TEMPLATES.TemplateResponse(
            request,
            "plugins.html",
            context(request, session, channel_id=cid, plugins=rows, assignments=assignments),
        )

    @router.get("/channels/{cid}/routing", response_class=HTMLResponse)
    def routing(
        cid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        rows = db.scalars(
            select(ChannelRoute).where(ChannelRoute.channel_id == cid).order_by(ChannelRoute.id)
        ).all()
        return TEMPLATES.TemplateResponse(
            request, "routing.html", context(request, session, channel_id=cid, routes=rows)
        )

    @router.get("/channels/{cid}/projects", response_class=HTMLResponse)
    def projects(
        cid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        service = WorkspaceService(db)
        try:
            rows = service.list_projects(cid)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return TEMPLATES.TemplateResponse(
            request, "projects.html", context(request, session, channel_id=cid, projects=rows)
        )

    @router.post("/channels/{cid}/projects")
    async def create_project(
        cid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> RedirectResponse:
        form = await _form(request)
        require_csrf(form, session)
        service = WorkspaceService(db)
        try:
            project = service.create_project(cid, form.get("title", ""))
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RedirectResponse(f"/dashboard/projects/{project.id}", status_code=303)

    @router.get("/projects/{pid}", response_class=HTMLResponse)
    def project(
        pid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        item = db.get(Project, pid)
        if item is None:
            raise HTTPException(status_code=404, detail="project not found")
        brief = db.scalar(
            select(ProjectBrief)
            .where(ProjectBrief.project_id == pid)
            .order_by(ProjectBrief.generation.desc())
        )
        runs = db.scalars(
            select(WorkflowRun).where(WorkflowRun.project_id == pid).order_by(WorkflowRun.created_at)
        ).all()
        brief_data = json.loads(brief.data_json) if brief else {}
        return TEMPLATES.TemplateResponse(
            request,
            "project.html",
            context(request, session, project=item, brief=brief, brief_data=brief_data, runs=runs),
        )

    @router.post("/projects/{pid}/brief")
    async def save_brief(
        pid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> RedirectResponse:
        form = await _form(request)
        require_csrf(form, session)
        metadata_text = form.get("metadata", "{}")
        try:
            metadata = json.loads(metadata_text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="metadata must be valid JSON") from exc
        data = {
            "title": form.get("title", ""),
            "topic": form.get("topic", ""),
            "goal": form.get("goal", ""),
            "language": form.get("language", ""),
            "metadata": metadata,
        }
        try:
            WorkspaceService(db).save_brief(pid, data)
            db.commit()
        except ValidationError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=exc.message) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RedirectResponse(f"/dashboard/projects/{pid}", status_code=303)

    @router.get("/runs/{rid}", response_class=HTMLResponse)
    def run(
        rid: str,
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        item = db.get(WorkflowRun, rid)
        if item is None:
            raise HTTPException(status_code=404, detail="run not found")
        return TEMPLATES.TemplateResponse(
            request, "run.html", context(request, session, run=item)
        )

    @router.get("/approvals", response_class=HTMLResponse)
    def approvals(
        request: Request,
        session: Annotated[SessionRecord, Depends(current_session)],
        db: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        rows = db.scalars(
            select(ApprovalQueue)
            .where(ApprovalQueue.status == "waiting")
            .order_by(ApprovalQueue.id)
        ).all()
        return TEMPLATES.TemplateResponse(
            request, "approvals.html", context(request, session, approvals=rows)
        )

    return router
