"""Run-level SSE progress stream."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from queue import Empty
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Job
from core.progress.service import ProgressService


def build_run_progress_router(
    progress: ProgressService,
    session_dependency: Callable[..., Session],
    auth_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/runs/{run_id}/progress", dependencies=[Depends(auth_dependency)])
    def stream(
        run_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> StreamingResponse:
        jobs = list(session.scalars(select(Job).where(Job.run_id == run_id)))

        def events() -> Iterator[str]:
            subscriptions = [(job.id, progress.subscribe(job.id)) for job in jobs]
            try:
                yield ("event: ready\ndata: " + json.dumps({"run_id": run_id}) + "\n\n")
                while True:
                    sent = False
                    for job_id, subscriber in subscriptions:
                        try:
                            item = subscriber.get(timeout=0.25)
                            payload = {"job_id": job_id, **item}
                            yield (
                                "event: progress\ndata: "
                                + json.dumps(payload, separators=(",", ":"))
                                + "\n\n"
                            )
                            sent = True
                        except Empty:
                            pass
                    if not sent:
                        yield ": keepalive\n\n"
            finally:
                for job_id, subscriber in subscriptions:
                    progress.unsubscribe(job_id, subscriber)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return router
