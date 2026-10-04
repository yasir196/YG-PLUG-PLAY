"""Minimal server-rendered dashboard for the Phase-1a demo flow."""

from __future__ import annotations

import html
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

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


def page(title: str, body: str) -> HTMLResponse:
    nav = (
        '<nav><a href="/dashboard/channels">Channels</a> · '
        '<a href="/dashboard/approvals">Approvals</a></nav>'
    )
    return HTMLResponse(
        f"<!doctype html><html><head><title>{html.escape(title)}</title>"
        '<script src="https://unpkg.com/htmx.org@2.0.4"></script></head>'
        f"<body>{nav}<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def build_dashboard_router(
    session_dependency: Any, auth_dependency: Any, csrf_dependency: Any
) -> APIRouter:
    router = APIRouter(prefix="/dashboard")

    @router.get("/login", response_class=HTMLResponse)
    def login() -> HTMLResponse:
        return page(
            "Login",
            '<form method="post" action="/auth/login">'
            '<input name="password" type="password"><button>Login</button></form>',
        )

    @router.get("/channels", dependencies=[Depends(auth_dependency)])
    def channels(s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        rows = s.scalars(select(Channel)).all()
        body = "".join(
            f'<p><a href="/dashboard/channels/{item.id}">{html.escape(item.name)}</a></p>'
            for item in rows
        )
        return page("Channels", body)

    @router.get("/channels/{cid}", dependencies=[Depends(auth_dependency)])
    def channel(cid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        item = s.get(Channel, cid)
        links = (
            f'<p>Niche: {html.escape(item.niche_id or "")}</p>'
            f'<p><a href="/dashboard/channels/{cid}/plugins">Plugins</a> · '
            f'<a href="/dashboard/channels/{cid}/routing">Routing</a> · '
            f'<a href="/dashboard/channels/{cid}/projects">Projects</a></p>'
        )
        return page(item.name, links)

    @router.get("/channels/{cid}/plugins", dependencies=[Depends(auth_dependency)])
    def plugins(cid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        rows = s.scalars(select(PluginVersion)).all()
        assignments = {
            item.plugin_id: item
            for item in s.scalars(
                select(ChannelPluginAssignment).where(ChannelPluginAssignment.channel_id == cid)
            )
        }
        body = "".join(
            f"<section><b>{html.escape(item.plugin_id)} {html.escape(item.version)}</b> — "
            f'{"enabled" if assignments.get(item.plugin_id) and assignments[item.plugin_id].enabled else "disabled"}'
            f'<p><a href="/dashboard/channels/{cid}/plugins/{item.plugin_id}/settings">'
            "Settings</a></p></section>"
            for item in rows
        )
        return page("Plugins", body)

    @router.get(
        "/channels/{cid}/plugins/{pid}/settings",
        dependencies=[Depends(auth_dependency)],
    )
    def settings(
        cid: str,
        pid: str,
        s: Annotated[Session, Depends(session_dependency)],
    ) -> HTMLResponse:
        plugin_version = s.scalar(
            select(PluginVersion)
            .where(PluginVersion.plugin_id == pid)
            .order_by(PluginVersion.id.desc())
        )
        manifest = json.loads(plugin_version.manifest_json)
        path = manifest.get("settings_schema", "")
        return page(
            "Plugin settings",
            f"<p>Schema: {html.escape(str(path))}</p>"
            f'<form hx-post="/dashboard/channels/{cid}/plugins/{pid}/settings">'
            '<div id="schema-fields">'
            "Settings are rendered from the installed plugin settings schema."
            "</div><button>Save</button></form>",
        )

    @router.get("/channels/{cid}/routing", dependencies=[Depends(auth_dependency)])
    def routing(cid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        rows = s.scalars(select(ChannelRoute).where(ChannelRoute.channel_id == cid)).all()
        return page(
            "Routing",
            "".join(
                f"<p>{html.escape(item.capability)} / "
                f'{html.escape(item.purpose or item.variant or "default")} → '
                f"{html.escape(item.primary_plugin_id)} {html.escape(item.options_json)}</p>"
                for item in rows
            ),
        )

    @router.get("/channels/{cid}/projects", dependencies=[Depends(auth_dependency)])
    def projects(cid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        rows = s.scalars(select(Project).where(Project.channel_id == cid)).all()
        return page(
            "Projects",
            "".join(
                f'<p><a href="/dashboard/projects/{item.id}">{html.escape(item.title)}</a></p>'
                for item in rows
            ),
        )

    @router.get("/projects/{pid}", dependencies=[Depends(auth_dependency)])
    def project(pid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        item = s.get(Project, pid)
        brief = s.scalar(
            select(ProjectBrief)
            .where(ProjectBrief.project_id == pid)
            .order_by(ProjectBrief.generation.desc())
        )
        runs = s.scalars(select(WorkflowRun).where(WorkflowRun.project_id == pid)).all()
        return page(
            item.title,
            f'<h2>Brief</h2><pre>{html.escape(brief.data_json if brief else "{}")}</pre>'
            + "".join(
                f'<p><a href="/dashboard/runs/{run.id}">Run {run.id}</a> — {run.status}</p>'
                for run in runs
            ),
        )

    @router.get("/runs/{rid}", dependencies=[Depends(auth_dependency)])
    def run(rid: str, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        item = s.get(WorkflowRun, rid)
        return page(
            "Run",
            f'<p id="status">{html.escape(item.status)}</p><div id="progress"></div>'
            f'<script>const es=new EventSource("/api/runs/{rid}/progress");'
            'es.addEventListener("progress",e=>'
            'document.getElementById("progress").textContent=e.data);</script>',
        )

    @router.get("/approvals", dependencies=[Depends(auth_dependency)])
    def approvals(s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        rows = s.scalars(select(ApprovalQueue).where(ApprovalQueue.status == "waiting")).all()
        return page(
            "Approvals",
            "".join(
                f'<p><a href="/dashboard/approvals/{item.id}">'
                f"Run {item.run_id} / {item.node_id}</a></p>"
                for item in rows
            ),
        )

    @router.get("/approvals/{qid}", dependencies=[Depends(auth_dependency)])
    def approval(qid: int, s: Annotated[Session, Depends(session_dependency)]) -> HTMLResponse:
        item = s.get(ApprovalQueue, qid)
        return page(
            "Approval",
            f"<p>Run {html.escape(item.run_id)} / {html.escape(item.node_id)}</p>"
            f'<form hx-post="/api/approvals/{qid}/actions">'
            '<button name="action" value="approve">Approve</button>'
            '<button name="action" value="reject">Reject</button>'
            '<textarea name="comment"></textarea>'
            '<button name="action" value="request-revision">Request revision</button></form>',
        )

    return router
