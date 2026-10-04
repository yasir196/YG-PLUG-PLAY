from __future__ import annotations

import json

import pytest

from core.audit import AuditEvent, AuditService
from core.database import create_sqlite_engine, session_factory
from core.database.models import AuditLog, Base


def test_audit_records_required_privileged_action_fields(tmp_path) -> None:
    engine = create_sqlite_engine(tmp_path / "audit.db")
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    with Session.begin() as session:
        row = AuditService(session).record(
            AuditEvent(
                actor="admin",
                action="channel.create",
                target_type="channel",
                target_id="channel-1",
                package_hash="a" * 64,
                result="success",
                correlation_id="corr-1",
            )
        )
        details = json.loads(row.details_json)
        assert details == {
            "correlation_id": "corr-1",
            "package_hash": "a" * 64,
            "result": "success",
        }
    engine.dispose()


def test_audit_log_rejects_update_and_delete(tmp_path) -> None:
    engine = create_sqlite_engine(tmp_path / "append-only.db")
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    with Session.begin() as session:
        row = AuditService(session).record(
            AuditEvent("admin", "project.create", "project", "p1")
        )
    with Session() as session:
        persisted = session.get(AuditLog, row.id)
        assert persisted is not None
        persisted.action = "tampered"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
        persisted = session.get(AuditLog, row.id)
        assert persisted is not None
        session.delete(persisted)
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
    engine.dispose()
