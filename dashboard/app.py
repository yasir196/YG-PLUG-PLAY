"""Composable loopback dashboard application for the Phase-1a browser flow."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from core.auth.app import ALLOWED_HOSTS, LOOPBACK_ORIGINS
from core.auth.service import AuthService
from core.config import initialize_data_root
from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, User
from dashboard.routes import build_dashboard_router

ROOT = Path(__file__).resolve().parents[1]


def create_dashboard_app(
    *,
    data_root: Path | None = None,
    auth: AuthService | None = None,
) -> FastAPI:
    layout = initialize_data_root(install_root=ROOT, override=data_root)
    engine = create_sqlite_engine(layout.db / "core.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    auth_service = auth or AuthService()

    with factory() as session:
        if session.get(User, "admin") is None:
            session.add(User(id="admin", username="admin"))
            session.commit()

    app = FastAPI(title="YG-PLUG-PLAY")
    app.state.auth = auth_service
    app.state.db_engine = engine
    app.state.data_root = layout
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOOPBACK_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    def db_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.include_router(build_dashboard_router(db_session, auth_service))
    return app


app = create_dashboard_app()
