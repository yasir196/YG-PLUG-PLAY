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
from core.routing.router import current_provider_package
from core.workflow.errors import ApprovalNotFoundError, WorkflowRuntimeError


def _json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("snapshot JSON payload must be an object")
    return cast(dict[str, Any], value)


def _provider_block(
    session: Session, channel_id: str, plugin_id: str, settings: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    item = current_provider_package(session, channel_id, plugin_id)
    if item is None:
        return None
    return {
        "version": item.version,
        "package_sha256": item.package_sha256,
        "settings": dict(settings.get(plugin_id, {})),
    }


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
    settings_by_plugin: dict[str, dict[str, Any]] = {}
    for setting in settings:
        values = settings_by_plugin.setdefault(setting.plugin_id, {})
        values[setting.key] = json.loads(setting.value_json)
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
                "provider": _provider_block(
                    session, project.channel_id, route.primary_plugin_id, settings_by_plugin
                ),
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
