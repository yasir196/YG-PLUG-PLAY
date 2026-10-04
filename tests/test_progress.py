from __future__ import annotations

import json

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Job
from core.plugin_runtime.permissions import ExecutionContext, RPCPermissionLayer
from core.progress import ProgressService


def test_progress_rpc_persists_and_fans_out(tmp_path):
    e = create_sqlite_engine(tmp_path / "db")
    Base.metadata.create_all(e)
    f = session_factory(e)
    with f() as s:
        s.add(Job(id="j", kind="demo", status="running"))
        s.commit()
        svc = ProgressService(s, min_interval=0)
        q = svc.subscribe("j")
        ctx = ExecutionContext.create(
            plugin_id="p", plugin_version="1", channel_id="c", package_sha256="a" * 64
        )
        RPCPermissionLayer(svc.rpc_handlers()).dispatch(
            ctx, "job.progress", {"job_id": "j", "progress": 42, "message": "working"}
        )
        assert q.get_nowait()["progress"] == 42
        assert json.loads(s.get(Job, "j").progress_json)["message"] == "working"
    e.dispose()
