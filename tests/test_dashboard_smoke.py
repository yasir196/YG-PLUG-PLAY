from fastapi.testclient import TestClient

from dashboard.app import create_dashboard_app


def test_login_page_renders(tmp_path) -> None:
    app = create_dashboard_app(data_root=tmp_path)

    with TestClient(app) as client:
        response = client.get("/dashboard/login")

    assert response.status_code == 200
    assert "<form" in response.text
