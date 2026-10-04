from __future__ import annotations
import json
from pathlib import Path
import pytest
from core.database import create_sqlite_engine,session_factory
from core.database.models import Base,Channel,Niche,Project,ProjectBrief,User,Workflow,WorkflowRun,WorkflowVersion,ApprovalDecision
from core.workflow import DurableWorkflowEngine
from core.workflow.approvals import ApprovalAccessError,ApprovalService

WF={"id":"a","version":1,"start":"write","nodes":[{"id":"write","type":"capability","capability":"demo/write","inputs":{"b":{"from":"$run.project-brief"}},"outputs":{"script":{"contract":"script","version":"^1"}},"next":"review"},{"id":"review","type":"human-approval","approval":{"roles":["editor"],"artifact":{"from":"write.script"},"actions":{"approve":"done","request-revision":"write","edit":"$self"}}},{"id":"done","type":"end","status":"success"}]}

def test_roles_admin_revision_and_edit_diff(tmp_path:Path):
 e=create_sqlite_engine(tmp_path/"db");Base.metadata.create_all(e);f=session_factory(e)
 with f() as s:
  s.add_all([Niche(id="n",version="1"),Channel(id="c",name="C",niche_id="n",niche_version="1"),Project(id="p",channel_id="c",title="P"),ProjectBrief(id="b",project_id="p",generation=1,data_json="{}"),User(id="admin",username="admin"),Workflow(id="w",name="W")]);s.flush()
  wv=WorkflowVersion(workflow_id="w",version=1,definition_json=json.dumps(WF));s.add(wv);s.flush();s.add(WorkflowRun(id="r",project_id="p",workflow_version_id=wv.id,status="running",current_node_id="write"));s.commit()
  eng=DurableWorkflowEngine(s,tmp_path/"art",lambda c,i:{"script":"draft"});eng.resume("r");svc=ApprovalService(s,eng);qid=svc.list({"editor"})[0]["id"]
  with pytest.raises(ApprovalAccessError):svc.view(qid,{"viewer"})
  assert svc.view(qid,set(),True)["artifact"]=="draft"
  with pytest.raises(Exception,match="comment"):svc.act(qid,"request-revision","admin",{"editor"})
  assert svc.act(qid,"edit","admin",set(),True,edited_data="edited")=="waiting-approval"
  d=s.query(ApprovalDecision).order_by(ApprovalDecision.id.desc()).first();assert json.loads(d.diff_json)["format"]=="unified"
 e.dispose()
