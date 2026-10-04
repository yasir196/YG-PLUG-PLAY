"""HTTP approval queue endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.workflow.approvals import ApprovalAccessError, ApprovalService
from core.workflow.engine import WorkflowRuntimeError


class ApprovalAction(BaseModel):
    action: str
    comment: str | None = None
    edited_data: Any = None


def build_approval_router(
    service_dependency: Callable[..., ApprovalService],
    auth_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/api/approvals")

    def roles() -> tuple[set[str], bool]:
        return {"admin"}, True

    @router.get("", dependencies=[Depends(auth_dependency)])
    def listing(
        svc: Annotated[ApprovalService, Depends(service_dependency)],
    ) -> list[dict[str, Any]]:
        actor_roles, admin = roles()
        return svc.list(actor_roles, admin)

    @router.get("/{queue_id}", dependencies=[Depends(auth_dependency)])
    def view(
        queue_id: int, svc: Annotated[ApprovalService, Depends(service_dependency)]
    ) -> dict[str, Any]:
        try:
            actor_roles, admin = roles()
            return svc.view(queue_id, actor_roles, admin)
        except ApprovalAccessError as exc:
            raise HTTPException(403, str(exc)) from exc

    @router.post("/{queue_id}/actions", dependencies=[Depends(csrf_dependency)])
    def act(
        queue_id: int,
        body: ApprovalAction,
        svc: Annotated[ApprovalService, Depends(service_dependency)],
    ) -> dict[str, str]:
        try:
            actor_roles, admin = roles()
            return {
                "status": svc.act(
                    queue_id,
                    body.action,
                    "admin",
                    actor_roles,
                    admin,
                    body.comment,
                    body.edited_data,
                )
            }
        except ApprovalAccessError as exc:
            raise HTTPException(403, str(exc)) from exc
        except WorkflowRuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
