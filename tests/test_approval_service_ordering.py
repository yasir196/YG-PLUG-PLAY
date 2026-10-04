from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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
    User,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from core.workflow import DurableWorkflowEngine
from core.workflow.approvals import ApprovalAccessError, ApprovalService

WF = {
    "id": "approval-service-ordering",
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
                "actions": {"approve": {"kind": "approve", "next": "done"}},
            },
        },
        {"id": "done", "type": "end", "status": "success"},
    ],
}


def setup_run(tmp_path: Path) -> tuple[Any, Session, ApprovalService, int]:
    db = create_sqlite_engine(tmp_path / "approval-service-ordering.db")
    Base.metadata.create_all(db)
    session = session_factory(db)()
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
    version = WorkflowVersion(workflow_id="w", version=1, definition_json=json.dumps(WF))
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
        select(ApprovalQueue).where(ApprovalQueue.run_id == "r", ApprovalQueue.node_id == "review")
    )
    assert queue is not None
    return db, session, ApprovalService(session, workflow), queue.id


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


def test_decided_queue_checks_role_before_status_without_mutation(tmp_path: Path):
    db, session, service, queue_id = setup_run(tmp_path)
    try:
        assert service.act(queue_id, "approve", "admin", {"admin"}, is_admin=True) == "success"
        before = mutation_state(session, queue_id)

        with pytest.raises(ApprovalAccessError):
            service.act(queue_id, "approve", "viewer", {"viewer"}, is_admin=False)

        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()


def test_waiting_queue_rejects_missing_role_without_mutation(tmp_path: Path):
    db, session, service, queue_id = setup_run(tmp_path)
    try:
        before = mutation_state(session, queue_id)

        with pytest.raises(ApprovalAccessError):
            service.act(queue_id, "approve", "viewer", {"viewer"}, is_admin=False)

        assert_no_mutation(session, queue_id, before)
    finally:
        session.close()
        db.dispose()
