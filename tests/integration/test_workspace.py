from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from core.config.data_root import initialize_data_root
from core.database import create_sqlite_engine, session_factory
from core.database.models import Base, ProjectBrief
from core.workspace.bootstrap import install_bundled_demo_packages
from core.workspace.service import WorkspaceService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def session(tmp_path):
    engine = create_sqlite_engine(tmp_path / "workspace.db")
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    layout = initialize_data_root(install_root=ROOT, override=tmp_path / "data")
    with Session() as db:
        install_bundled_demo_packages(db, layout, source_root=ROOT)
        db.commit()
        yield db
    engine.dispose()


def test_channel_project_and_valid_brief_integration(session) -> None:
    service = WorkspaceService(session)
    channel = service.create_channel("Demo Channel", "demo", "1.0.0")
    project = service.create_project(channel.id, "First Project")
    data = {
        "title": "First Project",
        "topic": "Demo topic",
        "goal": "Demonstrate the vertical slice",
        "language": "en",
        "metadata": {},
    }
    brief = service.save_brief(project.id, data)
    session.commit()

    assert service.open_channel(channel.id).niche_id == "demo"
    assert service.list_channels()[0].id == channel.id
    assert service.list_projects(channel.id)[0].id == project.id
    assert service.open_project(project.id).title == "First Project"
    assert json.loads(service.open_brief(project.id).data_json) == data
    assert brief.generation == 1


def test_invalid_project_brief_is_rejected(session) -> None:
    service = WorkspaceService(session)
    channel = service.create_channel("Demo Channel", "demo", "1.0.0")
    project = service.create_project(channel.id, "Bad Brief")
    with pytest.raises(ValidationError):
        service.save_brief(project.id, {"title": "incomplete"})


def test_brief_edits_create_new_generation(session) -> None:
    service = WorkspaceService(session)
    channel = service.create_channel("Demo Channel", "demo", "1.0.0")
    project = service.create_project(channel.id, "Versioned Brief")
    data = {"title": "A", "topic": "T", "goal": "G", "language": "en", "metadata": {}}
    first = service.save_brief(project.id, data)
    second = service.save_brief(project.id, {**data, "title": "B"})
    assert (first.generation, second.generation) == (1, 2)
    assert session.query(ProjectBrief).filter_by(project_id=project.id).count() == 2
