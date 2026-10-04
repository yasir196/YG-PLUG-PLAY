from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import create_sqlite_engine, session_factory
from core.database.models import (
    ApprovalDecision,
    ApprovalQueue,
    ArtifactGeneration,
    Base,
    Channel,
    Niche,
    Project,
    ProjectBrief,
    RunSnapshot,
    User,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from core.workflow import ApprovalNotFoundError, ApprovalValidationError
from core.workflow import DurableWorkflowEngine
from core.workflow.approval_api import build_approval_router
from core.workflow.approvals import ApprovalService

WF = {
    "id": "edge",
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
                    "edit": {"kind": "edit", "next": "$self"},
                },
            },
        },
        {"id": "done", "type": "end", "status": "success"},
    ],
}


def setup_run(tmp_path: Path) -> tuple[Any, Session, DurableWorkflowEngine, int]:
    engine = create_sqlite_engine(tmp_path / "edge.db")
    Base.metadata.create_all(engine)
    session = session_factory(engine)()
    session.add_all(
        [
            Niche(id="n", version="1"),
            User(id="admin", username="admin"),
            Workflow(id="w", name="W"),
        ]
    )
    session.flush()
    session.add(Channel(id="c", name="C", niche_id="n", niche_version="1"))
    session.flush()
    session.add(Project(id="p", channel_id="c", title="P"))
    session.flush()
    session.add(ProjectBrief(id="b", project_id="p", generation=1, data_json="{}"))
    version = WorkflowVersion(
        workflow_id="w", version=1, definition_json=json.dumps(WF)
    )
    session.add(version)
    session.flush()
    session.add(
        WorkflowRun(
            id="r",
            project_id="p",
            workflow_version_id=version.id,
            status="running",
            current_node_id="write",
        )
    )
    session.commit()
    workflow = DurableWorkflowEngine(
        session, tmp_path / "artifacts", lambda c, i: {"script": "draft"}
    )
    assert workflow.resume("r") == "waiting-approval"
    queue = session.scalar(
        select(ApprovalQueue).where(
            ApprovalQueue.run_id == "r", ApprovalQueue.node_id == "review"
        )
    )
    assert queue is not None
    return engine, session, workflow, queue.id


def mutation_state(session: Session, queue_id: int) -> tuple[int, int, str, str | None, str]:
    run = session.get(WorkflowRun, "r")
    queue = session.get(ApprovalQueue, queue_id)
    assert run is not None
    assert queue is not None
    decisions = session.scalar(select(func.count()).select_from(ApprovalDecision)) or 0
    generations = session.scalar(select(func.count()).select_from(ArtifactGeneration)) or 0
    return decisions, generations, run.status, run.current_node_id, queue.status


def assert_no_mutation(
    session: Session,
    queue_id: int,
    before: tuple[int, int, str, str | None, str],
) -> None:
    session.expire_all()
    assert mutation_state(session, queue_id) == before


def api_client(service: ApprovalService) -> TestClient:
    app = FastAPI()
    app.include_router(build_approval_router(lambda: service, lambda: True, lambda: True))
    return TestClient(app, raise_server_exceptions=False)


def test_second_action_on_decided_queue_returns_409_without_mutation(tmp_path: Path):
    db, session, workflow, queue_id = setup_run(tmp_path)
    try:
        service = ApprovalService(session, workflow)
        client = api_client(service)
        first = client.post(
            f"/api/approvals/{queue_id}/actions", json={"action": "approve"}
        )
        assert first.status_code == 200
        before = mutation_state(session, queue_id)

        second = client.post(
            f"/api/approvals/{queue_id}/actions", json={"action": "approve"}
        )

        assert second.status_code == 409
        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()


def test_engine_edit_without_data_is_validation_error_without_mutation(tmp_path: Path):
    db, session, workflow, queue_id = setup_run(tmp_path)
    try:
        before = mutation_state(session, queue_id)
        with pytest.raises(ApprovalValidationError):
            workflow.decide("r", "review", "edit", "admin")
        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()


def test_get_missing_approval_returns_404_without_mutation(tmp_path: Path):
    db, session, workflow, queue_id = setup_run(tmp_path)
    try:
        service = ApprovalService(session, workflow)
        client = api_client(service)
        before = mutation_state(session, queue_id)

        response = client.get("/api/approvals/999999")

        assert response.status_code == 404
        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()


def test_missing_snapshot_node_is_not_found_without_mutation(tmp_path: Path):
    db, session, workflow, queue_id = setup_run(tmp_path)
    try:
        snapshot = session.get(RunSnapshot, "r")
        assert snapshot is not None
        payload = json.loads(snapshot.snapshot_json)
        payload["workflow"]["nodes"] = [
            node for node in payload["workflow"]["nodes"] if node["id"] != "review"
        ]
        snapshot.snapshot_json = json.dumps(payload)
        session.commit()
        before = mutation_state(session, queue_id)

        with pytest.raises(ApprovalNotFoundError):
            workflow.decide("r", "review", "approve", "admin")
        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()
