"""Loopback-only FastAPI shell with strict browser security."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import AuthService, SessionRecord

SESSION_COOKIE = "yg_session"
LOOPBACK_ORIGINS = ("http://127.0.0.1:8765",)
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]


class PasswordBody(BaseModel):
    password: str


def create_app(auth: AuthService | None = None) -> FastAPI:
    auth_service = auth or AuthService()
    app = FastAPI()
    app.state.auth = auth_service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOOPBACK_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    def current_session(
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> SessionRecord:
        try:
            return auth_service.require_session(session_token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def csrf_guard(
        session: Annotated[SessionRecord, Depends(current_session)],
        csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> SessionRecord:
        if csrf is None or not secrets.compare_digest(csrf, session.csrf_token):
            raise HTTPException(status_code=403, detail="invalid CSRF token")
        return session

    @app.get("/auth/status")
    def auth_status() -> dict[str, bool]:
        return {"setup_required": auth_service.setup_required}

    @app.post("/auth/setup", status_code=201)
    def setup(body: PasswordBody) -> dict[str, bool]:
        try:
            auth_service.setup_admin(body.password)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"configured": True}

    @app.post("/auth/login")
    def login(body: PasswordBody, response: Response) -> dict[str, str]:
        try:
            token, csrf = auth_service.authenticate(body.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )
        return {"csrf_token": csrf}

    @app.get("/api/me")
    def me(_: Annotated[SessionRecord, Depends(current_session)]) -> dict[str, str]:
        return {"role": "admin"}

    @app.post("/api/change")
    def change(_: Annotated[SessionRecord, Depends(csrf_guard)]) -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
