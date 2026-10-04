"""Append-only privileged-action audit service."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.orm import Session

from core.database.models import AuditLog


@dataclass(frozen=True)
class AuditEvent:
    actor: str | None
    action: str
    target_type: str
    target_id: str | None
    package_hash: str | None = None
    result: str = "success"
    correlation_id: str | None = None


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, item: AuditEvent) -> AuditLog:
        correlation_id = item.correlation_id or uuid.uuid4().hex
        row = AuditLog(
            actor_id=item.actor,
            action=item.action,
            entity_type=item.target_type,
            entity_id=item.target_id,
            details_json=json.dumps(
                {
                    "package_hash": item.package_hash,
                    "result": item.result,
                    "correlation_id": correlation_id,
                },
                sort_keys=True,
            ),
        )
        self.session.add(row)
        self.session.flush()
        return row


@event.listens_for(AuditLog, "before_update")
def _reject_audit_update(*_: object) -> None:
    raise ValueError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete")
def _reject_audit_delete(*_: object) -> None:
    raise ValueError("audit_log is append-only")
