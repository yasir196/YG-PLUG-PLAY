from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import create_sqlite_engine, session_factory
from core.database.models import (
    ApprovalDecision,
    Base,
    Channel,
    Niche,
    Project,
    ProjectBrief,
    User,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from core.workflow import DurableWorkflowEngine
from core.workflow.approval_api import build_approval_router
from core.workflow.approvals import ApprovalAccessError, ApprovalService

WF = {
    "id": "a",
    "version": 1,
    "start": "write",
    "nodes": [
        {
            "id": "write",
            "type": "capability",
            "capability": "demo/write",
            "inputs": {"b": {"from": "$run.project-brief"}},
            "outputs": {"script": {"contract": "script", "version": "^1"}},
            "next": "review",
        },
        {
            "id": "review",
            "type": "human-approval",
            "approval": {
                "roles": ["editor"],
                "artifact": {"from": "write.script"},
                "actions": {
                    "approve": {"kind": "approve", "next": "done"},
                    "request-revision": {"kind": "request-revision", "next": "write"},
                    "edit": {"kind": "edit", "next": "$self"},
                },
            },
        },
        {"id": "done", "type": "end", "status": "success"},
    ],
}


def test_roles_admin_revision_and_edit_diff(tmp_path: Path):
    e = create_sqlite_engine(tmp_path / "db")
    Base.metadata.create_all(e)
    f = session_factory(e)
    with f() as s:
        s.add_all(
            [
                Niche(id="n", version="1"),
                User(id="admin", username="admin"),
                Workflow(id="w", name="W"),
            ]
        )
        s.flush()
        s.add(Channel(id="c", name="C", niche_id="n", niche_version="1"))
        s.flush()
        s.add(Project(id="p", channel_id="c", title="P"))
        s.flush()
        s.add(ProjectBrief(id="b", project_id="p", generation=1, data_json="{}"))
        s.flush()
        wv = WorkflowVersion(workflow_id="w", version=1, definition_json=json.dumps(WF))
        s.add(wv)
        s.flush()
        s.add(
            WorkflowRun(
                id="r",
                project_id="p",
                workflow_version_id=wv.id,
                status="running",
                current_node_id="write",
            )
        )
        s.commit()
        eng = DurableWorkflowEngine(s, tmp_path / "art", lambda c, i: {"script": "draft"})
        eng.resume("r")
        svc = ApprovalService(s, eng)
        qid = svc.list({"editor"})[0]["id"]
        with pytest.raises(ApprovalAccessError):
            svc.view(qid, {"viewer"})
        assert svc.view(qid, set(), True)["artifact"] == "draft"
        with pytest.raises(Exception, match="comment"):
            svc.act(qid, "request-revision", "admin", {"editor"})
        assert (
            svc.act(qid, "edit", "admin", set(), True, edited_data="edited") == "waiting-approval"
        )
        d = s.query(ApprovalDecision).order_by(ApprovalDecision.id.desc()).first()
        assert json.loads(d.diff_json)["format"] == "unified"
    e.dispose()


def test_invalid_action_api_returns_422(tmp_path: Path):
    e = create_sqlite_engine(tmp_path / "api.db")
    Base.metadata.create_all(e)
    f = session_factory(e)
    with f() as s:
        s.add_all(
            [
                Niche(id="n", version="1"),
                User(id="admin", username="admin"),
                Workflow(id="w", name="W"),
            ]
        )
        s.flush()
        s.add(Channel(id="c", name="C", niche_id="n", niche_version="1"))
        s.flush()
        s.add(Project(id="p", channel_id="c", title="P"))
        s.flush()
        s.add(ProjectBrief(id="b", project_id="p", generation=1, data_json="{}"))
        wv = WorkflowVersion(workflow_id="w", version=1, definition_json=json.dumps(WF))
        s.add(wv)
        s.flush()
        s.add(
            WorkflowRun(
                id="r",
                project_id="p",
                workflow_version_id=wv.id,
                status="running",
                current_node_id="write",
            )
        )
        s.commit()
        eng = DurableWorkflowEngine(s, tmp_path / "api-art", lambda c, i: {"script": "draft"})
        eng.resume("r")
        svc = ApprovalService(s, eng)
        qid = svc.list({"editor"})[0]["id"]
        app = FastAPI()
        app.include_router(build_approval_router(lambda: svc, lambda: True, lambda: True))
        response = TestClient(app).post(
            f"/api/approvals/{qid}/actions", json={"action": "nonsense"}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "approval action not allowed"
    e.dispose()
