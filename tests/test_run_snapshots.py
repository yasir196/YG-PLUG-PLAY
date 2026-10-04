from __future__ import annotations
import json
from pathlib import Path
from core.database import create_sqlite_engine,session_factory
from core.database.models import Base,Channel,ChannelRoute,Niche,Plugin,Project,ProjectBrief,Workflow,WorkflowRun,WorkflowVersion,WorkflowNodeRun,RunSnapshot
from core.workflow import DurableWorkflowEngine
from core.workflow.execution import CapabilityExecution

WF={"id":"snap","version":1,"start":"one","nodes":[{"id":"one","type":"capability","capability":"demo/one","inputs":{"brief":{"from":"$run.project-brief"}},"outputs":{"x":{"contract":"script","version":"^1"}},"next":"done"},{"id":"done","type":"end","status":"success"}]}

def test_snapshot_is_frozen_and_node_run_records_actual_execution(tmp_path:Path):
 e=create_sqlite_engine(tmp_path/"db.sqlite");Base.metadata.create_all(e);f=session_factory(e)
 with f() as s:
  s.add_all([Niche(id="n",version="1"),Workflow(id="w",name="W"),Plugin(id="provider",kind="general")]);s.flush();s.add(Channel(id="c",name="C",niche_id="n",niche_version="1"));s.flush();s.add(Project(id="p",channel_id="c",title="P"));s.flush();s.add(ProjectBrief(id="b",project_id="p",generation=1,data_json='{"topic":"x"}'));s.flush()
  wv=WorkflowVersion(workflow_id="w",version=1,definition_json=json.dumps(WF));s.add(wv);s.flush()
  route=ChannelRoute(channel_id="c",capability="text-generation",purpose="x",primary_plugin_id="provider",options_json='{"model":"old-model"}');s.add(route)
  s.add(WorkflowRun(id="r",project_id="p",workflow_version_id=wv.id,status="running",current_node_id="one"));s.commit()
  # Freeze before routing is edited, as run-start does.
  from core.workflow.snapshot import freeze_run_snapshot
  snap=freeze_run_snapshot(s,"r");s.commit()
  route.options_json='{"model":"new-model"}';s.commit()
  def runner(cap,inputs):
   return CapabilityExecution({"x":"hello"},"provider","old-model",{"model":"old-model"},{"input_tokens":3,"output_tokens":1})
  assert DurableWorkflowEngine(s,tmp_path/"art",runner).resume("r")=="success"
  persisted=json.loads(s.get(RunSnapshot,"r").snapshot_json)
  assert persisted["routes"][0]["options"]["model"]=="old-model"
  nr=s.query(WorkflowNodeRun).one()
  assert nr.provider_plugin_id=="provider" and nr.model=="old-model"
  assert json.loads(nr.options_json)["model"]=="old-model"
  assert json.loads(nr.usage_json)["input_tokens"]==3
  assert len(json.loads(nr.input_hashes_json)["brief"])==64
  assert len(json.loads(nr.output_hashes_json)["x"])==64
 e.dispose()
