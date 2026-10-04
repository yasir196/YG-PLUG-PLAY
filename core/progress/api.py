"""Server-Sent Events for run/job progress."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from core.progress.service import ProgressService


def build_progress_router(
    progress: ProgressService, auth_dependency: Callable[..., Any]
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/jobs/{job_id}/progress", dependencies=[Depends(auth_dependency)])
    def stream(job_id: str) -> StreamingResponse:
        subscriber = progress.subscribe(job_id)

        def events() -> Iterator[str]:
            try:
                yield "event: ready\ndata: {}\n\n"
                while True:
                    item = subscriber.get(timeout=30)
                    yield (
                        "event: progress\ndata: " + json.dumps(item, separators=(",", ":")) + "\n\n"
                    )
            except Exception:
                yield ": keepalive\n\n"
            finally:
                progress.unsubscribe(job_id, subscriber)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
