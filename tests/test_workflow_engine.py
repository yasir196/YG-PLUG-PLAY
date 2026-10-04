from __future__ import annotations
import json
from pathlib import Path
from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Niche, Project, ProjectBrief, User, Workflow, WorkflowRun, WorkflowVersion
from core.workflow import DurableWorkflowEngine

WF={"id":"demo","version":1,"start":"write","nodes":[
{"id":"write","type":"capability","capability":"demo/writing","inputs":{"brief":{"from":"$run.project-brief"}},"outputs":{"script":{"contract":"script","version":"^1"}},"next":"manual"},
{"id":"manual","type":"human-approval","approval":{"roles":["editor"],"artifact":{"from":"write.script"},"actions":{"approve":"final","edit":"$self"}}},
{"id":"final","type":"human-approval","approval":{"roles":["publisher"],"artifact":{"approved":"script","among":["manual.approved"]},"actions":{"final-approve":"done"}}},
{"id":"done","type":"end","status":"success"}]}

def setup(db):
 e=create_sqlite_engine(db);Base.metadata.create_all(e);f=session_factory(e)
 with f() as s:
  s.add_all([Niche(id="demo",version="1.0.0"),Channel(id="c",name="C",niche_id="demo",niche_version="1.0.0"),Project(id="p",channel_id="c",title="P"),User(id="admin",username="admin"),Workflow(id="demo",name="Demo")]);s.flush()
  w=WorkflowVersion(workflow_id="demo",version=1,definition_json=json.dumps(WF));s.add(w);s.flush()
  s.add_all([ProjectBrief(id="b",project_id="p",generation=1,data_json=json.dumps({"topic":"x"})),WorkflowRun(id="r",project_id="p",workflow_version_id=w.id,status="running",current_node_id="write")]);s.commit()
 return e,f

def runner(cap,inputs): return {"script":"draft script"}

def test_restart_mid_run_and_waiting_approval_resume(tmp_path:Path):
 e,f=setup(tmp_path/"w.db")
 with f() as s:
  eng=DurableWorkflowEngine(s,tmp_path/"a",runner);assert eng.resume("r")=="waiting-approval"
 with f() as s:
  eng=DurableWorkflowEngine(s,tmp_path/"a",runner);assert eng.resume("r")=="waiting-approval"
  assert eng.decide("r","manual","approve","admin")=="waiting-approval"
 with f() as s:
  eng=DurableWorkflowEngine(s,tmp_path/"a",runner);assert eng.resume("r")=="waiting-approval"
  assert eng.decide("r","final","final-approve","admin")=="success"
 e.dispose()

def test_edit_creates_generation_and_reenters_approval(tmp_path:Path):
 e,f=setup(tmp_path/"e.db")
 with f() as s:
  eng=DurableWorkflowEngine(s,tmp_path/"a",runner);eng.resume("r")
  assert eng.decide("r","manual","edit","admin",feedback="fix",edited_data="edited script")=="waiting-approval"
  assert eng.decide("r","manual","approve","admin")=="waiting-approval"
 e.dispose()
