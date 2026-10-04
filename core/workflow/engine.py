"""Small durable Phase-1a workflow engine."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.workflow.execution import CapabilityExecution
from core.workflow.snapshot import freeze_run_snapshot

from core.database.models import (
    ApprovalDecision, ApprovalQueue, Artifact, ArtifactGeneration, Project,
    ProjectBrief, WorkflowNodeRun, WorkflowRun, WorkflowVersion,
)

CapabilityRunner = Callable[[str, dict[str, Any]], dict[str, Any] | CapabilityExecution]


class WorkflowRuntimeError(RuntimeError):
    pass


class DurableWorkflowEngine:
    def __init__(self, session: Session, artifact_root: Path, runner: CapabilityRunner) -> None:
        self.session, self.artifact_root, self.runner = session, artifact_root, runner
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def resume(self, run_id: str) -> str:
        run = self.session.get(WorkflowRun, run_id)
        if run is None: raise WorkflowRuntimeError("run not found")
        snapshot = freeze_run_snapshot(self.session, run_id)
        definition = snapshot["workflow"]
        nodes = {n["id"]: n for n in definition["nodes"]}
        if run.current_node_id is None: run.current_node_id = definition["start"]
        while run.status not in {"success","failed","rejected","cancelled","waiting-approval"}:
            node = nodes[run.current_node_id]
            if node["type"] == "capability": self._capability(run,node)
            elif node["type"] == "condition": self._condition(run,node)
            elif node["type"] == "human-approval": self._approval_wait(run,node)
            elif node["type"] == "end":
                run.status=node["status"]; run.current_node_id=None
            else: raise WorkflowRuntimeError("unsupported Phase-1a node")
            self.session.commit()
        return run.status

    def _capability(self, run: WorkflowRun, node: dict[str, Any]) -> None:
        attempt=(self.session.scalar(select(func.max(WorkflowNodeRun.attempt)).where(WorkflowNodeRun.run_id==run.id,WorkflowNodeRun.node_id==node["id"])) or 0)+1
        nr=WorkflowNodeRun(run_id=run.id,node_id=node["id"],attempt=attempt,status="running"); self.session.add(nr); self.session.flush()
        inputs={k:self._select(run.id,s) for k,s in node.get("inputs",{}).items()}
        nr.input_hashes_json=json.dumps({k:self._value_hash(v) for k,v in inputs.items()},sort_keys=True)
        raw=self.runner(node["capability"],inputs)
        execution=raw if isinstance(raw,CapabilityExecution) else CapabilityExecution(outputs=raw)
        nr.provider_plugin_id=execution.provider_plugin_id
        nr.model=execution.model
        nr.options_json=json.dumps(execution.options or {},sort_keys=True)
        nr.usage_json=json.dumps(execution.usage or {},sort_keys=True)
        output_hashes={}
        for name,spec in node.get("outputs",{}).items():
            if name in execution.outputs:
                g=self._publish(run.id,node["id"],name,spec["contract"],execution.outputs[name],"core")
                output_hashes[name]=g.sha256
        nr.output_hashes_json=json.dumps(output_hashes,sort_keys=True)
        nr.status="success"; run.current_node_id=self._next(node,attempt)

    def _next(self, node: dict[str, Any], attempt: int) -> str | None:
        loop=node.get("loop_control")
        if node.get("next") == "$self":
            if loop and attempt >= loop["max_attempts"]:
                exhausted = loop["on_exhausted"]
                if not isinstance(exhausted, str):
                    raise WorkflowRuntimeError("loop on_exhausted target must be a string")
                return exhausted
            node_id = node["id"]
            if not isinstance(node_id, str):
                raise WorkflowRuntimeError("node id must be a string")
            return node_id
        next_id = node.get("next")
        if next_id is not None and not isinstance(next_id, str):
            raise WorkflowRuntimeError("next target must be a string")
        return next_id

    def _condition(self, run: WorkflowRun, node: dict[str, Any]) -> None:
        data={k:self._select(run.id,s) for k,s in node["inputs"].items()}
        run.current_node_id=node["true_next"] if self._logic(node["expression"],data) else node["false_next"]

    def _approval_wait(self, run: WorkflowRun, node: dict[str, Any]) -> None:
        existing=self.session.scalar(select(ApprovalQueue).where(ApprovalQueue.run_id==run.id,ApprovalQueue.node_id==node["id"],ApprovalQueue.status=="waiting"))
        if existing is None:
            target=self._select(run.id,node["approval"]["artifact"]) if node["approval"].get("artifact") else None
            gen_id=self._selected_generation_id(run.id,node["approval"]["artifact"]) if node["approval"].get("artifact") else None
            self.session.add(ApprovalQueue(run_id=run.id,node_id=node["id"],artifact_generation_id=gen_id,status="waiting"))
        run.status="waiting-approval"

    def decide(self, run_id: str, node_id: str, action: str, actor_id: str, feedback: str | None = None, edited_data: Any = None) -> str:
        run=self.session.get(WorkflowRun,run_id)
        if run is None: raise WorkflowRuntimeError("run not found")
        wf=self.session.get(WorkflowVersion,run.workflow_version_id)
        if wf is None: raise WorkflowRuntimeError("workflow version not found")
        node=next(n for n in json.loads(wf.definition_json)["nodes"] if n["id"]==node_id)
        q=self.session.scalar(select(ApprovalQueue).where(ApprovalQueue.run_id==run_id,ApprovalQueue.node_id==node_id,ApprovalQueue.status=="waiting"))
        if q is None: raise WorkflowRuntimeError("approval not waiting")
        target=self.session.get(ArtifactGeneration,q.artifact_generation_id) if q.artifact_generation_id else None
        if action=="edit":
            if target is None or edited_data is None: raise WorkflowRuntimeError("edit requires target and data")
            target=self._edit_generation(target,edited_data,actor_id); q.artifact_generation_id=target.id
        decision={"action":action,"actor":actor_id,"target_artifact":target.artifact_id if target else None,"target_generation":target.generation if target else None,"timestamp":datetime.now(timezone.utc).isoformat(),"feedback":feedback}
        self._publish(run_id,node_id,"decision","approval.decision",decision,actor_id)
        self.session.add(ApprovalDecision(approval_queue_id=q.id,action=action,actor_id=actor_id,target_artifact_id=decision["target_artifact"],target_generation=decision["target_generation"],feedback=feedback))
        if action in {"approve","approved","final-approve"} and target:
            artifact=self.session.get(Artifact,target.artifact_id)
            if artifact is None: raise WorkflowRuntimeError("approval artifact not found")
            data=self._read(target)
            self._publish(run_id,node_id,"approved",artifact.contract_id,data,actor_id)
        q.status="decided"; run.status="running"; run.current_node_id=node["approval"]["actions"][action]
        if run.current_node_id=="$self": run.current_node_id=node_id
        self.session.commit(); return self.resume(run_id)

    def _select(self, run_id: str, s: dict[str, Any]) -> Any:
        if "from" in s:
            ref=s["from"]
            if ref=="$run.project-brief":
                run=self.session.get(WorkflowRun,run_id)
                if run is None: raise WorkflowRuntimeError("run not found")
                brief=self.session.scalar(select(ProjectBrief).where(ProjectBrief.project_id==run.project_id).order_by(ProjectBrief.generation.desc()))
                if brief is None: raise WorkflowRuntimeError("project brief not found")
                return json.loads(brief.data_json)
            node,name=ref.split(".",1); return self._latest(run_id,node,name)
        contract=s.get("latest") or s.get("approved")
        among=s.get("among",[])
        candidates=[]
        for ref in among:
            node,name=ref.split(".",1); g=self._generation(run_id,node,name,contract)
            if g:candidates.append(g)
        if not candidates and s.get("optional"): return None
        if not candidates: raise WorkflowRuntimeError("selector unresolved")
        return self._with_meta(max(candidates,key=lambda g:g.id))

    def _selected_generation_id(self, run_id: str, s: dict[str, Any]) -> int | None:
        if "from" in s:
            ref=s["from"]
            if ref.startswith("$run."): return None
            node,name=ref.split(".",1); g=self._generation(run_id,node,name,None)
            return g.id if g else None
        contract=s.get("latest") or s.get("approved")
        candidates=[]
        for ref in s.get("among",[]):
            node,name=ref.split(".",1); g=self._generation(run_id,node,name,contract)
            if g:candidates.append(g)
        return max(candidates,key=lambda g:g.id).id if candidates else None

    def _latest(self, run_id: str, node: str, name: str) -> Any:
        g=self._generation(run_id,node,name,None)
        if not g: raise WorkflowRuntimeError("selector unresolved")
        return self._with_meta(g)

    def _generation(self, run_id: str, node: str, name: str, contract: str | None) -> ArtifactGeneration | None:
        q=select(ArtifactGeneration).join(Artifact).where(Artifact.run_id==run_id,Artifact.logical_name==f"{node}.{name}")
        if contract:q=q.where(Artifact.contract_id==contract)
        return self.session.scalar(q.order_by(ArtifactGeneration.id.desc()))

    def _publish(self, run_id: str, node: str, name: str, contract: str, data: Any, actor: str) -> ArtifactGeneration:
        logical=f"{node}.{name}"; art=self.session.scalar(select(Artifact).where(Artifact.run_id==run_id,Artifact.logical_name==logical))
        if not art: art=Artifact(id=uuid.uuid4().hex,run_id=run_id,contract_id=contract,logical_name=logical); self.session.add(art); self.session.flush()
        generation=(self.session.scalar(select(func.max(ArtifactGeneration.generation)).where(ArtifactGeneration.artifact_id==art.id)) or 0)+1
        raw=json.dumps(data,ensure_ascii=False,sort_keys=True).encode(); digest=hashlib.sha256(raw).hexdigest(); path=self.artifact_root/digest; path.write_bytes(raw)
        g=ArtifactGeneration(artifact_id=art.id,generation=generation,actor=actor,content_path=str(path),sha256=digest,metadata_json="{}"); self.session.add(g); self.session.flush(); return g

    def _edit_generation(self, g: ArtifactGeneration, data: Any, actor: str) -> ArtifactGeneration:
        art=self.session.get(Artifact,g.artifact_id)
        if art is None: raise WorkflowRuntimeError("artifact not found")
        node,name=art.logical_name.split(".",1)
        return self._publish(art.run_id,node,name,art.contract_id,data,actor)

    def _read(self, g: ArtifactGeneration) -> Any: return json.loads(Path(g.content_path).read_text(encoding="utf-8"))
    def _with_meta(self, g: ArtifactGeneration) -> Any:
        data=self._read(g)
        return ({**data,"_generation_id":g.id} if isinstance(data,dict) else data)

    @staticmethod
    def _value_hash(value: Any) -> str:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _logic(self, expr: Any, data: dict[str, Any]) -> Any:
        if not isinstance(expr,dict): return expr
        op,args=next(iter(expr.items())); args=args if isinstance(args,list) else [args]
        vals=[self._logic(a,data) for a in args]
        if op == "var":
            cur: Any = data
            for part in str(args[0]).split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            return cur
        if op=="==": return vals[0]==vals[1]
        if op=="!=": return vals[0]!=vals[1]
        if op=="and": return all(vals)
        if op=="or": return any(vals)
        if op=="!": return not vals[0]
        raise WorkflowRuntimeError(f"unsupported JSONLogic operator: {op}")
