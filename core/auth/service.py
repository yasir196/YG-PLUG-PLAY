"""Argon2id credentials and expiring server-side sessions."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

SESSION_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    csrf_token: str
    expires_at: datetime


class AuthService:
    def __init__(self, ttl: timedelta = SESSION_TTL) -> None:
        self._hasher = PasswordHasher()
        self._password_hash: str | None = None
        self._sessions: dict[str, SessionRecord] = {}
        self._ttl = ttl

    @property
    def setup_required(self) -> bool:
        return self._password_hash is None

    def setup_admin(self, password: str) -> None:
        if not self.setup_required:
            raise ValueError("admin already configured")
        if len(password) < 12:
            raise ValueError("password must be at least 12 characters")
        self._password_hash = self._hasher.hash(password)

    def authenticate(self, password: str, now: datetime | None = None) -> tuple[str, str]:
        if self._password_hash is None:
            raise ValueError("admin setup required")
        try:
            self._hasher.verify(self._password_hash, password)
        except VerifyMismatchError as exc:
            raise ValueError("invalid credentials") from exc
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        instant = now or datetime.now(UTC)
        self._sessions[self._digest(token)] = SessionRecord(
            token_hash=self._digest(token), csrf_token=csrf, expires_at=instant + self._ttl
        )
        return token, csrf

    def require_session(self, token: str | None, now: datetime | None = None) -> SessionRecord:
        if not token:
            raise ValueError("authentication required")
        digest = self._digest(token)
        record = self._sessions.get(digest)
        instant = now or datetime.now(UTC)
        if record is None or record.expires_at <= instant:
            self._sessions.pop(digest, None)
            raise ValueError("session expired or invalid")
        return record

    def logout(self, token: str | None) -> None:
        if token:
            self._sessions.pop(self._digest(token), None)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
