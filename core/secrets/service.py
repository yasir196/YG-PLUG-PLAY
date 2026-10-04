"""Encrypted secret storage with Channel -> Platform fallback."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import EncryptedSecret
from core.secrets.crypto import SecretCipher


class SecretNotFound(KeyError):
    pass


class SecretService:
    def __init__(self, session: Session, cipher: SecretCipher) -> None:
        self.session = session
        self.cipher = cipher

    @staticmethod
    def _aad(name: str, channel_id: str | None) -> bytes:
        return f"yg-secret-v1:{channel_id or 'platform'}:{name}".encode()

    def set(self, name: str, plaintext: str, *, channel_id: str | None = None) -> EncryptedSecret:
        row = self.session.scalar(
            select(EncryptedSecret).where(
                EncryptedSecret.name == name,
                EncryptedSecret.channel_id == channel_id,
            )
        )
        ciphertext = self.cipher.encrypt(plaintext, aad=self._aad(name, channel_id))
        if row is None:
            row = EncryptedSecret(
                id=uuid.uuid4().hex,
                channel_id=channel_id,
                name=name,
                ciphertext=ciphertext,
            )
            self.session.add(row)
        else:
            row.ciphertext = ciphertext
        self.session.flush()
        return row

    def resolve(self, name: str, *, channel_id: str | None = None) -> str:
        if channel_id is not None:
            row = self.session.scalar(
                select(EncryptedSecret).where(
                    EncryptedSecret.name == name,
                    EncryptedSecret.channel_id == channel_id,
                )
            )
            if row is not None:
                return self.cipher.decrypt(row.ciphertext, aad=self._aad(name, channel_id))
        row = self.session.scalar(
            select(EncryptedSecret).where(
                EncryptedSecret.name == name,
                EncryptedSecret.channel_id.is_(None),
            )
        )
        if row is None:
            raise SecretNotFound(name)
        return self.cipher.decrypt(row.ciphertext, aad=self._aad(name, None))
