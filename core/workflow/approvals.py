"""Approval queue service with role enforcement and immutable edits."""

from __future__ import annotations
import difflib, json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.database.models import ApprovalDecision,ApprovalQueue,ArtifactGeneration,RunSnapshot
from core.workflow.engine import DurableWorkflowEngine,WorkflowRuntimeError

class ApprovalAccessError(PermissionError): pass

class ApprovalService:
 def __init__(self,session:Session,engine:DurableWorkflowEngine): self.session,self.engine=session,engine
 def list(self,actor_roles:set[str],is_admin:bool=False):
  rows=list(self.session.scalars(select(ApprovalQueue).where(ApprovalQueue.status=="waiting")))
  return [self._view(q,actor_roles,is_admin,include_artifact=False) for q in rows if self._allowed(q,actor_roles,is_admin)]
 def view(self,queue_id:int,actor_roles:set[str],is_admin:bool=False):
  q=self._queue(queue_id);self._require(q,actor_roles,is_admin);return self._view(q,actor_roles,is_admin,True)
 def act(self,queue_id:int,action:str,actor_id:str,actor_roles:set[str],is_admin:bool=False,comment:str|None=None,edited_data=None):
  q=self._queue(queue_id);self._require(q,actor_roles,is_admin)
  node=self._node(q)
  aliases={"request-revision":"request-revision","reject":"reject","approve":"approve","edit":"edit"}
  requested=aliases.get(action,action)
  if requested not in node["approval"]["actions"]: raise WorkflowRuntimeError("approval action not allowed")
  if requested=="request-revision" and not comment: raise WorkflowRuntimeError("revision comment required")
  diff=None
  if requested=="edit":
   if edited_data is None: raise WorkflowRuntimeError("edit requires data")
   old=self._artifact(q)
   diff="".join(difflib.unified_diff(json.dumps(old,ensure_ascii=False,indent=2).splitlines(True),json.dumps(edited_data,ensure_ascii=False,indent=2).splitlines(True),fromfile="before",tofile="after"))
  status=self.engine.decide(q.run_id,q.node_id,requested,actor_id,feedback=comment,edited_data=edited_data)
  decision=self.session.scalar(select(ApprovalDecision).where(ApprovalDecision.approval_queue_id==queue_id).order_by(ApprovalDecision.id.desc()))
  if decision is not None and diff is not None: decision.diff_json=json.dumps({"format":"unified","diff":diff},ensure_ascii=False);self.session.commit()
  return status
 def _queue(self,i):
  q=self.session.get(ApprovalQueue,i)
  if q is None: raise WorkflowRuntimeError("approval not found")
  return q
 def _node(self,q):
  snap=self.session.get(RunSnapshot,q.run_id)
  if snap is None: raise WorkflowRuntimeError("run snapshot missing")
  return next(n for n in json.loads(snap.snapshot_json)["workflow"]["nodes"] if n["id"]==q.node_id)
 def _allowed(self,q,roles,is_admin): return is_admin or bool(set(self._node(q)["approval"]["roles"]) & roles)
 def _require(self,q,roles,is_admin):
  if not self._allowed(q,roles,is_admin): raise ApprovalAccessError("approval role required")
 def _artifact(self,q):
  if q.artifact_generation_id is None:return None
  g=self.session.get(ArtifactGeneration,q.artifact_generation_id)
  return json.loads(Path(g.content_path).read_text(encoding="utf-8"))
 def _view(self,q,roles,is_admin,include_artifact):
  node=self._node(q)
  out={"id":q.id,"run_id":q.run_id,"node_id":q.node_id,"status":q.status,"roles":node["approval"]["roles"],"actions":list(node["approval"]["actions"])}
  if include_artifact:out["artifact"]=self._artifact(q)
  return out
