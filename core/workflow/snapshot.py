"""Immutable run-start configuration snapshots."""

from __future__ import annotations
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.database.models import ChannelRoute, PluginSetting, Project, RunSnapshot, WorkflowRun, WorkflowVersion

def freeze_run_snapshot(session: Session, run_id: str) -> dict:
    existing=session.get(RunSnapshot,run_id)
    if existing:return json.loads(existing.snapshot_json)
    run=session.get(WorkflowRun,run_id)
    if run is None:raise ValueError("run not found")
    project=session.get(Project,run.project_id)
    workflow=session.get(WorkflowVersion,run.workflow_version_id)
    routes=list(session.scalars(select(ChannelRoute).where(ChannelRoute.channel_id==project.channel_id)))
    settings=list(session.scalars(select(PluginSetting).where(PluginSetting.scope=="channel",PluginSetting.scope_id==project.channel_id)))
    payload={"workflow":json.loads(workflow.definition_json),"channel_id":project.channel_id,
      "routes":[{"capability":r.capability,"purpose":r.purpose,"variant":r.variant,"plugin_id":r.primary_plugin_id,"options":json.loads(r.options_json or "{}")} for r in routes],
      "settings":[{"plugin_id":s.plugin_id,"key":s.key,"value":json.loads(s.value_json),"schema_version":s.settings_schema_version} for s in settings]}
    session.add(RunSnapshot(run_id=run_id,snapshot_json=json.dumps(payload,sort_keys=True)));session.flush();return payload
