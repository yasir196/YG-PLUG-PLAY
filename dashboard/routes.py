"""Minimal server-rendered dashboard for the Phase-1a demo flow."""
from __future__ import annotations
import html,json
from fastapi import APIRouter,Depends,Form
from fastapi.responses import HTMLResponse,RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.database.models import Channel,ChannelPluginAssignment,ChannelRoute,PluginVersion,Project,ProjectBrief,WorkflowRun,ApprovalQueue

def page(title,body):
 nav='<nav><a href="/dashboard/channels">Channels</a> · <a href="/dashboard/approvals">Approvals</a></nav>'
 return HTMLResponse(f'<!doctype html><html><head><title>{html.escape(title)}</title><script src="https://unpkg.com/htmx.org@2.0.4"></script></head><body>{nav}<h1>{html.escape(title)}</h1>{body}</body></html>')

def build_dashboard_router(session_dependency,auth_dependency,csrf_dependency):
 r=APIRouter(prefix="/dashboard")
 @r.get("/login",response_class=HTMLResponse)
 def login():return page("Login",'<form method="post" action="/auth/login"><input name="password" type="password"><button>Login</button></form>')
 @r.get("/channels",dependencies=[Depends(auth_dependency)])
 def channels(s:Session=Depends(session_dependency)):
  rows=s.scalars(select(Channel)).all();body=''.join(f'<p><a href="/dashboard/channels/{x.id}">{html.escape(x.name)}</a></p>' for x in rows)
  return page("Channels",body)
 @r.get("/channels/{cid}",dependencies=[Depends(auth_dependency)])
 def channel(cid:str,s:Session=Depends(session_dependency)):
  c=s.get(Channel,cid);links=f'<p>Niche: {html.escape(c.niche_id or "")}</p><p><a href="/dashboard/channels/{cid}/plugins">Plugins</a> · <a href="/dashboard/channels/{cid}/routing">Routing</a> · <a href="/dashboard/channels/{cid}/projects">Projects</a></p>'
  return page(c.name,links)
 @r.get("/channels/{cid}/plugins",dependencies=[Depends(auth_dependency)])
 def plugins(cid:str,s:Session=Depends(session_dependency)):
  rows=s.scalars(select(PluginVersion)).all();assign={a.plugin_id:a for a in s.scalars(select(ChannelPluginAssignment).where(ChannelPluginAssignment.channel_id==cid))}
  body=''.join(f'<section><b>{html.escape(p.plugin_id)} {html.escape(p.version)}</b> — {"enabled" if assign.get(p.plugin_id) and assign[p.plugin_id].enabled else "disabled"}<p><a href="/dashboard/channels/{cid}/plugins/{p.plugin_id}/settings">Settings</a></p></section>' for p in rows)
  return page("Plugins",body)
 @r.get("/channels/{cid}/plugins/{pid}/settings",dependencies=[Depends(auth_dependency)])
 def settings(cid:str,pid:str,s:Session=Depends(session_dependency)):
  pv=s.scalar(select(PluginVersion).where(PluginVersion.plugin_id==pid).order_by(PluginVersion.id.desc()));m=json.loads(pv.manifest_json);path=m.get("settings_schema","")
  return page("Plugin settings",f'<p>Schema: {html.escape(str(path))}</p><form hx-post="/dashboard/channels/{cid}/plugins/{pid}/settings"><div id="schema-fields">Settings are rendered from the installed plugin settings schema.</div><button>Save</button></form>')
 @r.get("/channels/{cid}/routing",dependencies=[Depends(auth_dependency)])
 def routing(cid:str,s:Session=Depends(session_dependency)):
  rows=s.scalars(select(ChannelRoute).where(ChannelRoute.channel_id==cid)).all();return page("Routing",''.join(f'<p>{html.escape(x.capability)} / {html.escape(x.purpose or x.variant or "default")} → {html.escape(x.primary_plugin_id)} {html.escape(x.options_json)}</p>' for x in rows))
 @r.get("/channels/{cid}/projects",dependencies=[Depends(auth_dependency)])
 def projects(cid:str,s:Session=Depends(session_dependency)):
  rows=s.scalars(select(Project).where(Project.channel_id==cid)).all();return page("Projects",''.join(f'<p><a href="/dashboard/projects/{x.id}">{html.escape(x.title)}</a></p>' for x in rows))
 @r.get("/projects/{pid}",dependencies=[Depends(auth_dependency)])
 def project(pid:str,s:Session=Depends(session_dependency)):
  p=s.get(Project,pid);b=s.scalar(select(ProjectBrief).where(ProjectBrief.project_id==pid).order_by(ProjectBrief.generation.desc()));runs=s.scalars(select(WorkflowRun).where(WorkflowRun.project_id==pid)).all()
  return page(p.title,f'<h2>Brief</h2><pre>{html.escape(b.data_json if b else "{}")}</pre>'+''.join(f'<p><a href="/dashboard/runs/{x.id}">Run {x.id}</a> — {x.status}</p>' for x in runs))
 @r.get("/runs/{rid}",dependencies=[Depends(auth_dependency)])
 def run(rid:str,s:Session=Depends(session_dependency)):
  x=s.get(WorkflowRun,rid);return page("Run",f'<p id="status">{html.escape(x.status)}</p><div id="progress"></div><script>const es=new EventSource("/api/runs/{rid}/progress");es.addEventListener("progress",e=>document.getElementById("progress").textContent=e.data);</script>')
 @r.get("/approvals",dependencies=[Depends(auth_dependency)])
 def approvals(s:Session=Depends(session_dependency)):
  rows=s.scalars(select(ApprovalQueue).where(ApprovalQueue.status=="waiting")).all();return page("Approvals",''.join(f'<p><a href="/dashboard/approvals/{x.id}">Run {x.run_id} / {x.node_id}</a></p>' for x in rows))
 @r.get("/approvals/{qid}",dependencies=[Depends(auth_dependency)])
 def approval(qid:int,s:Session=Depends(session_dependency)):
  q=s.get(ApprovalQueue,qid);return page("Approval",f'<p>Run {html.escape(q.run_id)} / {html.escape(q.node_id)}</p><form hx-post="/api/approvals/{qid}/actions"><button name="action" value="approve">Approve</button><button name="action" value="reject">Reject</button><textarea name="comment"></textarea><button name="action" value="request-revision">Request revision</button></form>')
 return r
