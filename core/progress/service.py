"""Coalesced job progress persistence and in-process fanout."""
from __future__ import annotations
import json,time
from collections import defaultdict
from queue import Queue
from typing import Any
from sqlalchemy.orm import Session
from core.database.models import Job
from core.plugin_runtime.permissions import ExecutionContext

class ProgressService:
 def __init__(self,session:Session,min_interval:float=.25):
  self.session,self.min_interval=session,min_interval
  self._last:dict[str,float]={};self._pending:dict[str,dict[str,Any]]={};self._subs:dict[str,list[Queue]]=defaultdict(list)
 def report(self,context:ExecutionContext,params:dict[str,Any]):
  job_id=str(params["job_id"]);job=self.session.get(Job,job_id)
  if job is None:raise ValueError("job not found")
  payload={"job_id":job_id,"run_id":job.run_id,"progress":params.get("progress"),"message":params.get("message"),"plugin_id":context.plugin_id,"channel_id":context.channel_id}
  self._pending[job_id]=payload
  for q in tuple(self._subs[job_id]):q.put(payload)
  now=time.monotonic()
  if now-self._last.get(job_id,0)>=self.min_interval:self.flush(job_id);self._last[job_id]=now
  return {"accepted":True}
 def flush(self,job_id:str):
  payload=self._pending.pop(job_id,None)
  if payload is None:return
  job=self.session.get(Job,job_id);job.progress_json=json.dumps(payload,ensure_ascii=False,sort_keys=True);self.session.commit()
 def subscribe(self,job_id:str):
  q=Queue();self._subs[job_id].append(q);return q
 def unsubscribe(self,job_id:str,q):self._subs[job_id].remove(q)
 def rpc_handlers(self):return {"job.progress":self.report}
