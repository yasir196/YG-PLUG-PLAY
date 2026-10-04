from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from core.database import create_sqlite_engine, session_factory
from core.database.models import (
    ApprovalQueue,
    Artifact,
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

WF = {
    "id": "demo",
    "version": 1,
    "start": "write",
    "nodes": [
        {
            "id": "write",
            "type": "capability",
            "capability": "demo/writing",
            "inputs": {"brief": {"from": "$run.project-brief"}},
            "outputs": {"script": {"contract": "script", "version": "^1"}},
            "next": "manual",
        },
        {
            "id": "manual",
            "type": "human-approval",
            "approval": {
                "roles": ["editor"],
                "artifact": {"from": "write.script"},
                "actions": {
                    "publish-ok": {"kind": "approve", "next": "final"},
                    "approve": {"kind": "approve", "next": "final"},
                    "edit": {"kind": "edit", "next": "$self"},
                },
            },
        },
        {
            "id": "final",
            "type": "human-approval",
            "approval": {
                "roles": ["publisher"],
                "artifact": {"approved": "script", "among": ["manual.approved"]},
                "actions": {"final-approve": {"kind": "approve", "next": "done"}},
            },
        },
        {"id": "done", "type": "end", "status": "success"},
    ],
}


def setup(db, workflow=None):
    e = create_sqlite_engine(db)
    Base.metadata.create_all(e)
    f = session_factory(e)
    with f() as s:
        s.add_all(
            [
                Niche(id="demo", version="1.0.0"),
                User(id="admin", username="admin"),
                Workflow(id="demo", name="Demo"),
            ]
        )
        s.flush()
        s.add(Channel(id="c", name="C", niche_id="demo", niche_version="1.0.0"))
        s.flush()
        s.add(Project(id="p", channel_id="c", title="P"))
        s.flush()
        w = WorkflowVersion(workflow_id="demo", version=1, definition_json=json.dumps(workflow or WF))
        s.add(w)
        s.flush()
        s.add_all(
            [
                ProjectBrief(
                    id="b", project_id="p", generation=1, data_json=json.dumps({"topic": "x"})
                ),
                WorkflowRun(
                    id="r",
                    project_id="p",
                    workflow_version_id=w.id,
                    status="running",
                    current_node_id="write",
                ),
            ]
        )
        s.commit()
    return e, f


def runner(cap, inputs):
    return {"script": "draft script"}


def test_restart_mid_run_and_waiting_approval_resume(tmp_path: Path):
    e, f = setup(tmp_path / "w.db")
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a", runner)
        assert eng.resume("r") == "waiting-approval"
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a", runner)
        assert eng.resume("r") == "waiting-approval"
        assert eng.decide("r", "manual", "publish-ok", "admin") == "waiting-approval"
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a", runner)
        assert eng.resume("r") == "waiting-approval"
        assert eng.decide("r", "final", "final-approve", "admin") == "success"
    e.dispose()


def test_edit_creates_generation_and_reenters_approval(tmp_path: Path):
    e, f = setup(tmp_path / "e.db")
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a", runner)
        eng.resume("r")
        assert (
            eng.decide("r", "manual", "edit", "admin", feedback="fix", edited_data="edited script")
            == "waiting-approval"
        )
        assert eng.decide("r", "manual", "approve", "admin") == "waiting-approval"
    e.dispose()


def test_invalid_action_has_no_side_effects(tmp_path: Path):
    e, f = setup(tmp_path / "invalid.db")
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-invalid", runner)
        assert eng.resume("r") == "waiting-approval"
        before = s.query(ArtifactGeneration).join(Artifact).filter(Artifact.run_id == "r", Artifact.logical_name == "manual.decision").count()
        with pytest.raises(Exception, match="approval action not allowed"):
            eng.decide("r", "manual", "nonsense", "admin")
        after = s.query(ArtifactGeneration).join(Artifact).filter(Artifact.run_id == "r", Artifact.logical_name == "manual.decision").count()
        queue = s.query(ApprovalQueue).filter_by(run_id="r", node_id="manual").one()
        run = s.get(WorkflowRun, "r")
        assert before == after == 0
        assert queue.status == "waiting"
        assert run is not None and run.status == "waiting-approval"
    e.dispose()


def test_action_name_approve_with_reject_kind_does_not_publish_approved(tmp_path: Path):
    workflow = deepcopy(WF)
    workflow["nodes"][1]["approval"]["actions"]["approve"] = {
        "kind": "reject",
        "next": "rejected",
    }
    workflow["nodes"].append({"id": "rejected", "type": "end", "status": "rejected"})
    e, f = setup(tmp_path / "reject-kind.db", workflow)
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-reject", runner)
        assert eng.resume("r") == "waiting-approval"
        assert eng.decide("r", "manual", "approve", "admin") == "rejected"
        approved = s.query(Artifact).filter_by(run_id="r", logical_name="manual.approved").one_or_none()
        assert approved is None
    e.dispose()
