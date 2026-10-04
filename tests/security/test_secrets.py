from __future__ import annotations

import logging
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, EncryptedSecret, PluginSetting
from core.secrets import SecretCipher, SecretService


def test_channel_secret_overrides_platform_and_plaintext_never_persists_or_logs(
    tmp_path: Path, caplog
) -> None:
    engine = create_sqlite_engine(tmp_path / "secrets.db")
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    plaintext = "SUPER-SECRET-grep-marker-928374"
    cipher = SecretCipher(AESGCM.generate_key(bit_length=256))
    with Session.begin() as session:
        session.add(Channel(id="channel-1", name="Channel"))
        service = SecretService(session, cipher)
        service.set("provider-key", "platform-value")
        service.set("provider-key", plaintext, channel_id="channel-1")
        session.add(
            PluginSetting(
                plugin_id="dummy",
                scope="channel",
                scope_id="channel-1",
                key="safe-setting",
                value_json='{"mode":"safe"}',
            )
        )
    with Session() as session:
        service = SecretService(session, cipher)
        assert service.resolve("provider-key", channel_id="channel-1") == plaintext
        assert service.resolve("provider-key", channel_id="other-channel") == "platform-value"
        rows = list(session.scalars(select(EncryptedSecret)))
        settings = list(session.scalars(select(PluginSetting)))
        haystack = "\n".join(
            [*(row.ciphertext for row in rows), *(row.value_json for row in settings)]
        )
        assert plaintext not in haystack
    logging.getLogger("yg.test").info("secret operation completed")
    assert plaintext not in caplog.text
    engine.dispose()


def test_aes_gcm_ciphertext_does_not_contain_plaintext() -> None:
    plaintext = "NEVER-IN-DATABASE"
    cipher = SecretCipher(AESGCM.generate_key(bit_length=256))
    ciphertext = cipher.encrypt(plaintext, aad=b"scope")
    assert plaintext not in ciphertext
    assert cipher.decrypt(ciphertext, aad=b"scope") == plaintext
