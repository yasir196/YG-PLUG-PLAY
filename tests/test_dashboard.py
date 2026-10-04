from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.auth.service import AuthService
from dashboard.app import create_dashboard_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_dashboard_app(data_root=tmp_path / "data", auth=AuthService()))


def test_dashboard_requires_login_and_supports_first_time_setup(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/dashboard/channels").status_code == 401
    page = client.get("/dashboard/login")
    assert page.status_code == 200
    assert "First-time admin setup" in page.text
    setup = client.post(
        "/dashboard/setup", data={"password": "correct horse battery staple"}, follow_redirects=False
    )
    assert setup.status_code == 303
    login = client.post(
        "/dashboard/login", data={"password": "correct horse battery staple"}, follow_redirects=False
    )
    assert login.status_code == 303
    assert "yg_session" in login.cookies


def test_browser_can_create_channel_project_and_versioned_brief(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/dashboard/setup", data={"password": "correct horse battery staple"})
    client.post("/dashboard/login", data={"password": "correct horse battery staple"})
    channels = client.get("/dashboard/channels")
    assert channels.status_code == 200
    csrf = channels.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]

    created = client.post(
        "/dashboard/channels",
        data={"_csrf": csrf, "name": "Demo Channel", "niche_id": "demo", "niche_version": "1.0.0"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    channel_url = created.headers["location"]
    channel = client.get(channel_url)
    assert "Demo Channel" in channel.text

    projects_url = channel_url + "/projects"
    project_page = client.get(projects_url)
    csrf = project_page.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    created_project = client.post(
        projects_url,
        data={"_csrf": csrf, "title": "Browser Project"},
        follow_redirects=False,
    )
    assert created_project.status_code == 303
    project_url = created_project.headers["location"]

    project = client.get(project_url)
    csrf = project.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    saved = client.post(
        project_url + "/brief",
        data={
            "_csrf": csrf,
            "title": "Browser Project",
            "topic": "Demo topic",
            "goal": "Prove the browser workspace flow",
            "language": "en",
            "metadata": "{}",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert "Current generation: 1" in client.get(project_url).text


def test_dashboard_mutations_reject_missing_csrf(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/dashboard/setup", data={"password": "correct horse battery staple"})
    client.post("/dashboard/login", data={"password": "correct horse battery staple"})
    response = client.post(
        "/dashboard/channels",
        data={"name": "No CSRF", "niche_id": "demo", "niche_version": "1.0.0"},
    )
    assert response.status_code == 403
