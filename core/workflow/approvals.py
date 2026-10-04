"""Approval queue service with role enforcement and immutable edits."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import (
    ApprovalDecision,
    ApprovalQueue,
    ArtifactGeneration,
    RunSnapshot,
)
from core.workflow.engine import DurableWorkflowEngine, WorkflowRuntimeError


class ApprovalAccessError(PermissionError):
    pass


class ApprovalService:
    def __init__(self, session: Session, engine: DurableWorkflowEngine) -> None:
        self.session = session
        self.engine = engine

    def list(
        self, actor_roles: set[str], is_admin: bool = False
    ) -> list[dict[str, Any]]:
        rows = list(
            self.session.scalars(
                select(ApprovalQueue).where(ApprovalQueue.status == "waiting")
            )
        )
        return [
            self._view(queue, include_artifact=False)
            for queue in rows
            if self._allowed(queue, actor_roles, is_admin)
        ]

    def view(
        self, queue_id: int, actor_roles: set[str], is_admin: bool = False
    ) -> dict[str, Any]:
        queue = self._queue(queue_id)
        self._require(queue, actor_roles, is_admin)
        return self._view(queue, include_artifact=True)

    def act(
        self,
        queue_id: int,
        action: str,
        actor_id: str,
        actor_roles: set[str],
        is_admin: bool = False,
        comment: str | None = None,
        edited_data: Any = None,
    ) -> str:
        queue = self._queue(queue_id)
        self._require(queue, actor_roles, is_admin)
        node = self._node(queue)
        requested = action
        actions = node["approval"]["actions"]
        if requested not in actions:
            raise WorkflowRuntimeError("approval action not allowed")
        if requested == "request-revision" and not comment:
            raise WorkflowRuntimeError("revision comment required")

        diff: str | None = None
        if requested == "edit":
            if edited_data is None:
                raise WorkflowRuntimeError("edit requires data")
            old = self._artifact(queue)
            diff = "".join(
                difflib.unified_diff(
                    json.dumps(old, ensure_ascii=False, indent=2).splitlines(True),
                    json.dumps(edited_data, ensure_ascii=False, indent=2).splitlines(True),
                    fromfile="before",
                    tofile="after",
                )
            )

        status = self.engine.decide(
            queue.run_id,
            queue.node_id,
            requested,
            actor_id,
            feedback=comment,
            edited_data=edited_data,
        )
        decision = self.session.scalar(
            select(ApprovalDecision)
            .where(ApprovalDecision.approval_queue_id == queue_id)
            .order_by(ApprovalDecision.id.desc())
        )
        if decision is not None and diff is not None:
            decision.diff_json = json.dumps(
                {"format": "unified", "diff": diff}, ensure_ascii=False
            )
            self.session.commit()
        return status

    def _queue(self, queue_id: int) -> ApprovalQueue:
        queue = self.session.get(ApprovalQueue, queue_id)
        if queue is None:
            raise WorkflowRuntimeError("approval not found")
        return queue

    def _node(self, queue: ApprovalQueue) -> dict[str, Any]:
        snapshot = self.session.get(RunSnapshot, queue.run_id)
        if snapshot is None:
            raise WorkflowRuntimeError("run snapshot missing")
        payload = json.loads(snapshot.snapshot_json)
        if not isinstance(payload, dict):
            raise WorkflowRuntimeError("run snapshot must be an object")
        workflow = payload.get("workflow")
        if not isinstance(workflow, dict):
            raise WorkflowRuntimeError("run snapshot workflow missing")
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list):
            raise WorkflowRuntimeError("run snapshot nodes missing")
        for node in nodes:
            if isinstance(node, dict) and node.get("id") == queue.node_id:
                return cast(dict[str, Any], node)
        raise WorkflowRuntimeError("approval node missing from run snapshot")

    def _allowed(
        self, queue: ApprovalQueue, roles: set[str], is_admin: bool
    ) -> bool:
        if is_admin:
            return True
        node = self._node(queue)
        approval = node.get("approval")
        if not isinstance(approval, dict):
            raise WorkflowRuntimeError("approval node configuration missing")
        required_roles = approval.get("roles")
        if not isinstance(required_roles, list) or not all(
            isinstance(role, str) for role in required_roles
        ):
            raise WorkflowRuntimeError("approval roles are invalid")
        return bool(set(required_roles) & roles)

    def _require(
        self, queue: ApprovalQueue, roles: set[str], is_admin: bool
    ) -> None:
        if not self._allowed(queue, roles, is_admin):
            raise ApprovalAccessError("approval role required")

    def _artifact(self, queue: ApprovalQueue) -> Any:
        if queue.artifact_generation_id is None:
            return None
        generation = self.session.get(
            ArtifactGeneration, queue.artifact_generation_id
        )
        if generation is None:
            raise WorkflowRuntimeError("approval artifact generation not found")
        return json.loads(Path(generation.content_path).read_text(encoding="utf-8"))

    def _view(
        self, queue: ApprovalQueue, *, include_artifact: bool
    ) -> dict[str, Any]:
        node = self._node(queue)
        approval = node.get("approval")
        if not isinstance(approval, dict):
            raise WorkflowRuntimeError("approval node configuration missing")
        roles = approval.get("roles")
        actions = approval.get("actions")
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise WorkflowRuntimeError("approval roles are invalid")
        if not isinstance(actions, dict):
            raise WorkflowRuntimeError("approval actions are invalid")
        result: dict[str, Any] = {
            "id": queue.id,
            "run_id": queue.run_id,
            "node_id": queue.node_id,
            "status": queue.status,
            "roles": roles,
            "actions": list(actions),
        }
        if include_artifact:
            result["artifact"] = self._artifact(queue)
        return result
