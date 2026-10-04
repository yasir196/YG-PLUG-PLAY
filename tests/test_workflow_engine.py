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
from core.workflow import ApprovalNotFoundError, ApprovalValidationError, DurableWorkflowEngine

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
        w = WorkflowVersion(
            workflow_id="demo", version=1, definition_json=json.dumps(workflow or WF)
        )
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
        before = (
            s.query(ArtifactGeneration)
            .join(Artifact)
            .filter(Artifact.run_id == "r", Artifact.logical_name == "manual.decision")
            .count()
        )
        with pytest.raises(ApprovalValidationError, match="approval action not allowed"):
            eng.decide("r", "manual", "nonsense", "admin")
        after = (
            s.query(ArtifactGeneration)
            .join(Artifact)
            .filter(Artifact.run_id == "r", Artifact.logical_name == "manual.decision")
            .count()
        )
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
        approved = (
            s.query(Artifact).filter_by(run_id="r", logical_name="manual.approved").one_or_none()
        )
        assert approved is None
    e.dispose()


def test_requires_comment_rejects_missing_and_whitespace_before_mutation(tmp_path: Path):
    workflow = deepcopy(WF)
    workflow["nodes"][1]["approval"]["actions"]["revise"] = {
        "kind": "request-revision",
        "next": "write",
        "requires_comment": True,
    }
    e, f = setup(tmp_path / "comment-required.db", workflow)
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-comment", runner)
        assert eng.resume("r") == "waiting-approval"
        for feedback in (None, "   "):
            with pytest.raises(ApprovalValidationError, match="approval comment required"):
                eng.decide("r", "manual", "revise", "admin", feedback=feedback)
            decisions = (
                s.query(ArtifactGeneration)
                .join(Artifact)
                .filter(Artifact.run_id == "r", Artifact.logical_name == "manual.decision")
                .count()
            )
            queue = s.query(ApprovalQueue).filter_by(run_id="r", node_id="manual").one()
            run = s.get(WorkflowRun, "r")
            assert decisions == 0
            assert queue.status == "waiting"
            assert run is not None and run.status == "waiting-approval"
    e.dispose()


def test_request_revision_without_required_comment_can_retry(tmp_path: Path):
    workflow = deepcopy(WF)
    workflow["nodes"][1]["approval"]["actions"]["retry-failed"] = {
        "kind": "request-revision",
        "next": "write",
        "requires_comment": False,
    }
    e, f = setup(tmp_path / "retry-no-comment.db", workflow)
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-retry", runner)
        assert eng.resume("r") == "waiting-approval"
        assert eng.decide("r", "manual", "retry-failed", "admin") == "waiting-approval"
    e.dispose()


def test_missing_approval_node_is_typed_not_found(tmp_path: Path):
    e, f = setup(tmp_path / "missing-node.db")
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-missing-node", runner)
        assert eng.resume("r") == "waiting-approval"
        with pytest.raises(ApprovalNotFoundError, match="approval node not found"):
            eng.decide("r", "does-not-exist", "approve", "admin")
        queue = s.query(ApprovalQueue).filter_by(run_id="r", node_id="manual").one()
        assert queue.status == "waiting"
    e.dispose()


def test_edit_without_data_is_validation_error_before_mutation(tmp_path: Path):
    e, f = setup(tmp_path / "edit-without-data.db")
    with f() as s:
        eng = DurableWorkflowEngine(s, tmp_path / "a-edit-without-data", runner)
        assert eng.resume("r") == "waiting-approval"
        with pytest.raises(ApprovalValidationError, match="edit requires target and data"):
            eng.decide("r", "manual", "edit", "admin")
        queue = s.query(ApprovalQueue).filter_by(run_id="r", node_id="manual").one()
        run = s.get(WorkflowRun, "r")
        assert queue.status == "waiting"
        assert run is not None and run.status == "waiting-approval"
    e.dispose()
