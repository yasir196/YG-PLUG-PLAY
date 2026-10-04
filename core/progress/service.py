"""Coalesced job progress persistence and in-process fanout."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from queue import Queue
from typing import Any

from sqlalchemy.orm import Session

from core.database.models import Job
from core.plugin_runtime.permissions import ExecutionContext


class ProgressService:
    def __init__(self, session: Session, min_interval: float = 0.25) -> None:
        self.session = session
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self._subs: dict[str, list[Queue[dict[str, Any]]]] = defaultdict(list)

    def report(
        self, context: ExecutionContext, params: dict[str, Any]
    ) -> dict[str, bool]:
        job_id = str(params["job_id"])
        job = self.session.get(Job, job_id)
        if job is None:
            raise ValueError("job not found")
        payload = {
            "job_id": job_id,
            "run_id": job.run_id,
            "progress": params.get("progress"),
            "message": params.get("message"),
            "plugin_id": context.plugin_id,
            "channel_id": context.channel_id,
        }
        self._pending[job_id] = payload
        for subscriber in tuple(self._subs[job_id]):
            subscriber.put(payload)
        now = time.monotonic()
        if now - self._last.get(job_id, 0) >= self.min_interval:
            self.flush(job_id)
            self._last[job_id] = now
        return {"accepted": True}

    def flush(self, job_id: str) -> None:
        payload = self._pending.pop(job_id, None)
        if payload is None:
            return
        job = self.session.get(Job, job_id)
        if job is None:
            raise ValueError("job not found")
        job.progress_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.session.commit()

    def subscribe(self, job_id: str) -> Queue[dict[str, Any]]:
        subscriber: Queue[dict[str, Any]] = Queue()
        self._subs[job_id].append(subscriber)
        return subscriber

    def unsubscribe(self, job_id: str, subscriber: Queue[dict[str, Any]]) -> None:
        self._subs[job_id].remove(subscriber)

    def rpc_handlers(
        self,
    ) -> dict[str, Callable[[ExecutionContext, dict[str, Any]], Any]]:
        return {"job.progress": self.report}
