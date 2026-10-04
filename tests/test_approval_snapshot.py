from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

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
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowVersion,
)
from core.workflow import ApprovalValidationError, DurableWorkflowEngine
from core.workflow.snapshot import freeze_run_snapshot

WF = {
    "id": "approval-snapshot",
    "version": 1,
    "start": "manual",
    "nodes": [
        {
            "id": "manual",
            "type": "human-approval",
            "approval": {
                "roles": ["editor"],
                "actions": {
                    "approve": {
                        "kind": "approve",
                        "next": "media-planning",
                        "requires_comment": False,
                    }
                },
            },
        },
        {
            "id": "media-planning",
            "type": "capability",
            "capability": "demo/media-planning",
            "inputs": {},
            "outputs": {},
            "next": "done",
        },
        {"id": "done", "type": "end", "status": "success"},
        {"id": "end-rejected", "type": "end", "status": "rejected"},
    ],
}


def setup_run(path: Path):
    engine = create_sqlite_engine(path)
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        session.add_all([Niche(id="n", version="1"), Workflow(id="w", name="W")])
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
                current_node_id="manual",
            )
        )
        session.commit()
    return engine, factory


def mutate_live(session, mutator):
    run = session.get(WorkflowRun, "r")
    version = session.get(WorkflowVersion, run.workflow_version_id)
    definition = json.loads(version.definition_json)
    mutator(definition["nodes"][0]["approval"]["actions"])
    version.definition_json = json.dumps(definition)
    session.commit()


def runner(capability, inputs):
    return {}


def test_freeze_run_snapshot_is_idempotent_after_live_workflow_change(tmp_path: Path):
    engine, factory = setup_run(tmp_path / "freeze.db")
    with factory() as session:
        first = freeze_run_snapshot(session, "r")
        session.commit()
        row = session.get(RunSnapshot, "r")
        original_json = row.snapshot_json
        mutate_live(session, lambda actions: actions["approve"].update(next="end-rejected"))
        second = freeze_run_snapshot(session, "r")
        session.commit()
        assert second == first
        assert session.get(RunSnapshot, "r").snapshot_json == original_json
    engine.dispose()


def test_decide_uses_frozen_next_not_live_next(tmp_path: Path):
    engine, factory = setup_run(tmp_path / "next.db")
    with factory() as session:
        workflow = DurableWorkflowEngine(session, tmp_path / "art-next", runner)
        assert workflow.resume("r") == "waiting-approval"
        mutate_live(session, lambda actions: actions["approve"].update(next="end-rejected"))
        assert workflow.decide("r", "manual", "approve", "admin") == "success"
        assert session.query(WorkflowNodeRun).filter_by(node_id="media-planning").count() == 1
        run = session.get(WorkflowRun, "r")
        assert run.status != "rejected"
        assert session.query(ApprovalDecision).one().action == "approve"
    engine.dispose()


def test_decide_allows_action_removed_from_live_workflow(tmp_path: Path):
    engine, factory = setup_run(tmp_path / "removed.db")
    with factory() as session:
        workflow = DurableWorkflowEngine(session, tmp_path / "art-removed", runner)
        assert workflow.resume("r") == "waiting-approval"
        mutate_live(session, lambda actions: actions.pop("approve"))
        assert workflow.decide("r", "manual", "approve", "admin") == "success"
        assert session.query(ApprovalDecision).one().action == "approve"
    engine.dispose()


def test_decide_rejects_action_added_only_to_live_workflow_without_side_effects(tmp_path: Path):
    engine, factory = setup_run(tmp_path / "added.db")
    with factory() as session:
        workflow = DurableWorkflowEngine(session, tmp_path / "art-added", runner)
        assert workflow.resume("r") == "waiting-approval"
        queue = session.query(ApprovalQueue).filter_by(run_id="r", node_id="manual").one()
        before_generations = session.query(ArtifactGeneration).count()
        before_status = session.get(WorkflowRun, "r").status
        before_node = session.get(WorkflowRun, "r").current_node_id
        mutate_live(
            session,
            lambda actions: actions.update(
                {"ship": {"kind": "approve", "next": "done", "requires_comment": False}}
            ),
        )
        with pytest.raises(ApprovalValidationError, match="approval action not allowed"):
            workflow.decide("r", "manual", "ship", "admin")
        session.refresh(queue)
        run = session.get(WorkflowRun, "r")
        assert queue.status == "waiting"
        assert session.query(ApprovalDecision).count() == 0
        assert session.query(ArtifactGeneration).count() == before_generations
        assert run.status == before_status
        assert run.current_node_id == before_node
    engine.dispose()


def test_decide_uses_frozen_requires_comment(tmp_path: Path):
    engine, factory = setup_run(tmp_path / "comment.db")
    with factory() as session:
        workflow = DurableWorkflowEngine(session, tmp_path / "art-comment", runner)
        assert workflow.resume("r") == "waiting-approval"
        mutate_live(session, lambda actions: actions["approve"].update(requires_comment=True))
        assert workflow.decide("r", "manual", "approve", "admin", feedback=None) == "success"
        assert session.query(ApprovalDecision).one().action == "approve"
    engine.dispose()
