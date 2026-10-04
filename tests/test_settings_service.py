from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jsonschema.exceptions import ValidationError

from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, Channel, Plugin, PluginSetting, Project
from core.secrets import SecretCipher, SecretService
from core.settings import SettingsError, SettingsService

DEFINITION = {
    "version": 3,
    "fields": [
        {
            "key": "temperature",
            "type": "number",
            "allowed_scopes": ["platform", "channel", "project"],
            "default": 0.2,
        },
        {
            "key": "api-key",
            "type": "secret",
            "allowed_scopes": ["platform", "channel"],
            "platform_fallback": True,
        },
    ],
}


@pytest.fixture
def setup(tmp_path):
    engine = create_sqlite_engine(tmp_path / "settings.db")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        session.add_all(
            [
                Plugin(id="demo-provider", kind="general"),
                Channel(id="c1", name="Channel"),
                Project(id="p1", channel_id="c1", title="Project"),
            ]
        )
        session.commit()
        cipher = SecretCipher(AESGCM.generate_key(bit_length=256))
        yield (
            session,
            SettingsService(session, SecretService(session, cipher), "demo-provider", DEFINITION),
        )
    engine.dispose()


def test_project_channel_default_resolution_and_schema_version(setup) -> None:
    session, service = setup
    assert service.resolve("temperature", project_id="p1") == 0.2
    service.set("temperature", 0.4, scope="channel", scope_id="c1")
    assert service.resolve("temperature", project_id="p1") == 0.4
    service.set("temperature", 0.7, scope="project", scope_id="p1")
    assert service.resolve("temperature", project_id="p1") == 0.7
    row = session.query(PluginSetting).filter_by(key="temperature", scope="project").one()
    assert row.settings_schema_version == 3


def test_secret_is_routed_out_of_settings_table_and_falls_back(setup) -> None:
    session, service = setup
    service.set("api-key", "platform-secret", scope="platform")
    service.set("api-key", "channel-secret", scope="channel", scope_id="c1")
    assert service.resolve("api-key", channel_id="c1") == "channel-secret"
    assert service.resolve("api-key", channel_id="other") == "platform-secret"
    assert session.query(PluginSetting).filter_by(key="api-key").count() == 0


def test_scope_and_value_validation(setup) -> None:
    _, service = setup
    with pytest.raises(SettingsError, match="not allowed"):
        service.set("temperature", 0.5, scope="run", scope_id="r1")
    with pytest.raises(ValidationError):
        service.set("temperature", "hot", scope="channel", scope_id="c1")
