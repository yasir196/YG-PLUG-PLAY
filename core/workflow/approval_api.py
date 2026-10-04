"""HTTP approval queue endpoints."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from core.workflow.approvals import ApprovalAccessError,ApprovalService

class ApprovalAction(BaseModel):
 action:str
 comment:str|None=None
 edited_data:Any=None

def build_approval_router(service_dependency,auth_dependency,csrf_dependency)->APIRouter:
 r=APIRouter(prefix="/api/approvals")
 def roles(): return {"admin"},True
 @r.get("",dependencies=[Depends(auth_dependency)])
 def listing(svc:ApprovalService=Depends(service_dependency)):
  rs,admin=roles();return svc.list(rs,admin)
 @r.get("/{queue_id}",dependencies=[Depends(auth_dependency)])
 def view(queue_id:int,svc:ApprovalService=Depends(service_dependency)):
  try:rs,admin=roles();return svc.view(queue_id,rs,admin)
  except ApprovalAccessError as e:raise HTTPException(403,str(e)) from e
 @r.post("/{queue_id}/actions",dependencies=[Depends(csrf_dependency)])
 def act(queue_id:int,body:ApprovalAction,svc:ApprovalService=Depends(service_dependency)):
  try:rs,admin=roles();return {"status":svc.act(queue_id,body.action,"admin",rs,admin,body.comment,body.edited_data)}
  except ApprovalAccessError as e:raise HTTPException(403,str(e)) from e
 return r
