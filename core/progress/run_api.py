"""Run-level SSE progress stream."""
from __future__ import annotations
import json
from queue import Empty
from fastapi import APIRouter,Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from core.database.models import Job

def build_run_progress_router(progress,session_dependency,auth_dependency):
 r=APIRouter(prefix="/api")
 @r.get("/runs/{run_id}/progress",dependencies=[Depends(auth_dependency)])
 def stream(run_id:str,session=Depends(session_dependency)):
  jobs=list(session.scalars(select(Job).where(Job.run_id==run_id)))
  def events():
   subscriptions=[(j.id,progress.subscribe(j.id)) for j in jobs]
   try:
    yield "event: ready\\ndata: "+json.dumps({"run_id":run_id})+"\\n\\n"
    while True:
     sent=False
     for job_id,q in subscriptions:
      try:item=q.get(timeout=.25);yield "event: progress\\ndata: "+json.dumps(item,separators=(",",":"))+"\\n\\n";sent=True
      except Empty:pass
     if not sent:yield ": keepalive\\n\\n"
   finally:
    for job_id,q in subscriptions:progress.unsubscribe(job_id,q)
  return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache"})
 return r
