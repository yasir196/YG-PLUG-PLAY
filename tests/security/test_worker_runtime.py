from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.plugin_runtime import WorkerCrashed, WorkerIdentity, WorkerProcess, WorkerTimeout, worker_environment


def test_worker_environment_is_allowlisted_and_has_no_core_secrets() -> None:
    source = {
        "SYSTEMROOT": "C:/Windows",
        "PATH": "C:/Python",
        "YG_DATA_ROOT": "C:/secret/db",
        "YG_MASTER_KEY": "master-secret",
        "DATABASE_URL": "sqlite:///core.db",
        "OPENAI_API_KEY": "unrelated-secret",
    }
    env = worker_environment(WorkerIdentity("demo", "1.0.0", "channel-1"), source)
    assert env["YG_PLUGIN_ID"] == "demo"
    assert env["YG_PLUGIN_VERSION"] == "1.0.0"
    assert env["YG_CHANNEL_ID"] == "channel-1"
    for forbidden in ("YG_DATA_ROOT", "YG_MASTER_KEY", "DATABASE_URL", "OPENAI_API_KEY"):
        assert forbidden not in env


def script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "worker.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_json_rpc_identity_worker_survives_normal_call(tmp_path: Path) -> None:
    path = script(tmp_path, "import json,sys\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':r['params']}),flush=True)\n")
    worker = WorkerProcess([sys.executable, str(path)], WorkerIdentity("p", "1.0.0", "c"), cwd=tmp_path)
    try:
        assert worker.call("echo", {"ok": True}) == {"ok": True}
    finally:
        worker.close()


def test_worker_crash_does_not_crash_core(tmp_path: Path) -> None:
    path = script(tmp_path, "raise SystemExit(7)\n")
    worker = WorkerProcess([sys.executable, str(path)], WorkerIdentity("p", "1.0.0", "c"), cwd=tmp_path)
    with pytest.raises(WorkerCrashed):
        worker.call("boom", {})
    assert 2 + 2 == 4
    worker.close()


def test_worker_timeout_is_enforced(tmp_path: Path) -> None:
    path = script(tmp_path, "import time\ntime.sleep(5)\n")
    worker = WorkerProcess([sys.executable, str(path)], WorkerIdentity("p", "1.0.0", "c"), cwd=tmp_path, timeout=0.05)
    with pytest.raises(WorkerTimeout):
        worker.call("slow", {})
    assert worker.process is None


def test_idle_shutdown(tmp_path: Path) -> None:
    path = script(tmp_path, "import time\ntime.sleep(5)\n")
    worker = WorkerProcess([sys.executable, str(path)], WorkerIdentity("p", "1.0.0", "c"), cwd=tmp_path, idle_timeout=0.01)
    worker.start()
    assert worker.shutdown_if_idle(worker._last_used + 1)
    assert worker.process is None
