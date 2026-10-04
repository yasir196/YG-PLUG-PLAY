from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from core.database import Repository, create_sqlite_engine, session_factory
from core.database.models import Channel, Niche, User

EXPECTED = {
    "users",
    "sessions",
    "channels",
    "niches",
    "projects",
    "project_briefs",
    "plugins",
    "plugin_versions",
    "plugin_trust_grants",
    "channel_plugin_assignments",
    "plugin_settings",
    "encrypted_secrets",
    "capabilities",
    "contracts",
    "namespace_registry",
    "workflows",
    "workflow_versions",
    "channel_routes",
    "workflow_runs",
    "run_snapshots",
    "workflow_node_runs",
    "approval_queue",
    "approval_decisions",
    "artifacts",
    "artifact_generations",
    "jobs",
    "audit_log",
}


def alembic_config(path: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def test_fresh_database_migrates_up_and_down(tmp_path) -> None:
    db = tmp_path / "fresh.db"
    cfg = alembic_config(str(db))
    command.upgrade(cfg, "head")
    engine = create_sqlite_engine(db)
    assert set(inspect(engine).get_table_names()) >= EXPECTED
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_sqlite_engine(db)
    assert not (EXPECTED & set(inspect(engine).get_table_names()))
    engine.dispose()


def test_repository_crud(tmp_path) -> None:
    db = tmp_path / "repo.db"
    command.upgrade(alembic_config(str(db)), "head")
    engine = create_sqlite_engine(db)
    Session = session_factory(engine)
    with Session.begin() as session:
        users = Repository(session, User)
        niches = Repository(session, Niche)
        channels = Repository(session, Channel)
        users.add(User(id="admin", username="admin"))
        niches.add(Niche(id="demo", version="1.0.0"))
        channels.add(Channel(id="channel-1", name="Demo", niche_id="demo", niche_version="1.0.0"))
        assert users.get("admin") is not None
        assert [channel.id for channel in channels.list()] == ["channel-1"]
        channel = channels.get("channel-1")
        assert channel is not None
        channels.delete(channel)
        assert channels.get("channel-1") is None
    engine.dispose()
