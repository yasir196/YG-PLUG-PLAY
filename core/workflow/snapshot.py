"""Immutable run-start configuration snapshots."""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import (
    ChannelRoute,
    PluginSetting,
    Project,
    RunSnapshot,
    WorkflowRun,
    WorkflowVersion,
)
from core.workflow.errors import ApprovalNotFoundError, WorkflowRuntimeError


def _json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("snapshot JSON payload must be an object")
    return cast(dict[str, Any], value)


def load_snapshot_node(session: Session, run_id: str, node_id: str) -> dict[str, Any]:
    snapshot = session.get(RunSnapshot, run_id)
    if snapshot is None:
        raise WorkflowRuntimeError("run snapshot missing")
    payload = _json_object(snapshot.snapshot_json)
    workflow = payload.get("workflow")
    if not isinstance(workflow, dict):
        raise WorkflowRuntimeError("run snapshot workflow missing")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise WorkflowRuntimeError("run snapshot nodes missing")
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == node_id:
            return cast(dict[str, Any], node)
    raise ApprovalNotFoundError("approval node missing from run snapshot")


def freeze_run_snapshot(session: Session, run_id: str) -> dict[str, Any]:
    existing = session.get(RunSnapshot, run_id)
    if existing is not None:
        return _json_object(existing.snapshot_json)

    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise ValueError("run not found")
    project = session.get(Project, run.project_id)
    if project is None:
        raise ValueError("run project not found")
    workflow = session.get(WorkflowVersion, run.workflow_version_id)
    if workflow is None:
        raise ValueError("run workflow version not found")

    routes = list(
        session.scalars(select(ChannelRoute).where(ChannelRoute.channel_id == project.channel_id))
    )
    settings = list(
        session.scalars(
            select(PluginSetting).where(
                PluginSetting.scope == "channel",
                PluginSetting.scope_id == project.channel_id,
            )
        )
    )
    payload: dict[str, Any] = {
        "workflow": _json_object(workflow.definition_json),
        "channel_id": project.channel_id,
        "routes": [
            {
                "route_id": route.id,
                "capability": route.capability,
                "purpose": route.purpose,
                "variant": route.variant,
                "plugin_id": route.primary_plugin_id,
                "options": _json_object(route.options_json or "{}"),
            }
            for route in routes
        ],
        "settings": [
            {
                "plugin_id": setting.plugin_id,
                "key": setting.key,
                "value": json.loads(setting.value_json),
                "schema_version": setting.settings_schema_version,
            }
            for setting in settings
        ],
    }
    session.add(RunSnapshot(run_id=run_id, snapshot_json=json.dumps(payload, sort_keys=True)))
    session.flush()
    return payload
