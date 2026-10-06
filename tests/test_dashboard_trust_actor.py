from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.auth.app import SESSION_COOKIE
from core.auth.service import AuthService
from core.database.models import Plugin, PluginTrustGrant, PluginVersion
from dashboard.app import create_dashboard_app

PASSWORD = "correct horse battery staple"
SHA = "a" * 64


def test_trust_grant_records_session_user(tmp_path: Path) -> None:
    auth = AuthService(admin_user_id="owner")
    auth.setup_admin(PASSWORD)
    app = create_dashboard_app(data_root=tmp_path, auth=auth)

    with Session(app.state.db_engine) as db:
        db.add(Plugin(id="demo-plugin"))
        db.add(
            PluginVersion(
                plugin_id="demo-plugin",
                version="1.0.0",
                package_sha256=SHA,
                manifest_json="{}",
            )
        )
        db.commit()

    with TestClient(app) as client:
        form = {"password": PASSWORD}
        login = client.post("/dashboard/login", data=form, follow_redirects=False)
        assert login.status_code == 303
        token = client.cookies.get(SESSION_COOKIE)
        csrf = auth.require_session(token).csrf_token
        url = f"/dashboard/channels/c1/plugins/demo-plugin/1.0.0/{SHA}/trust"
        response = client.post(url, data={"_csrf": csrf}, follow_redirects=False)

    assert response.status_code == 303
    with Session(app.state.db_engine) as db:
        grant = db.scalar(select(PluginTrustGrant))
    assert grant is not None
    assert grant.granted_by == "owner"
