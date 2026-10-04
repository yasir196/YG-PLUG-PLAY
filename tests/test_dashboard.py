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


def test_dashboard_can_grant_trust_enable_plugin_and_edit_route(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/dashboard/setup", data={"password": "correct horse battery staple"})
    client.post("/dashboard/login", data={"password": "correct horse battery staple"})
    page = client.get("/dashboard/channels")
    csrf = page.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    created = client.post(
        "/dashboard/channels",
        data={"_csrf": csrf, "name": "Demo", "niche_id": "demo", "niche_version": "1.0.0"},
        follow_redirects=False,
    )
    channel_url = created.headers["location"]
    app = client.app
    factory = __import__("core.database", fromlist=["session_factory"]).session_factory(
        app.state.db_engine
    )
    import json
    from core.database.models import Plugin, PluginVersion

    root = Path(__file__).parents[1]
    raw = json.loads((root / "plugins/demo-text-provider/plugin.json").read_text(encoding="utf-8"))
    with factory() as db:
        if db.get(Plugin, "demo-text-provider") is None:
            db.add(Plugin(id="demo-text-provider", kind="general"))
        db.add(
            PluginVersion(
                plugin_id="demo-text-provider",
                version="1.0.0",
                package_sha256="a" * 64,
                manifest_json=json.dumps(raw),
            )
        )
        db.commit()

    plugins_url = channel_url + "/plugins"
    plugins = client.get(plugins_url)
    csrf = plugins.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    trust = client.post(
        plugins_url + "/demo-text-provider/1.0.0/" + ("a" * 64) + "/trust",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert trust.status_code == 303
    plugins = client.get(plugins_url)
    csrf = plugins.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    enabled = client.post(
        plugins_url + "/demo-text-provider/1.0.0/" + ("a" * 64) + "/assignment",
        data={"_csrf": csrf, "enabled": "true"},
        follow_redirects=False,
    )
    assert enabled.status_code == 303
    assert "Channel: enabled" in client.get(plugins_url).text

    routing_url = channel_url + "/routing"
    routing = client.get(routing_url)
    assert "demo-writing" in routing.text
    csrf = routing.text.split('name="_csrf" value="', 1)[1].split('"', 1)[0]
    route_id = routing.text.split('name="route_id" value="', 1)[1].split('"', 1)[0]
    saved = client.post(
        routing_url,
        data={
            "_csrf": csrf,
            "route_id": route_id,
            "capability": "text-generation",
            "purpose": "demo-writing",
            "variant": "",
            "plugin_id": "demo-text-provider",
            "options": '{"model":"demo-deterministic","temperature":0}',
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert "demo-deterministic" in client.get(routing_url).text
