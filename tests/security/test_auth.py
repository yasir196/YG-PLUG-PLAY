from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from core.auth.app import create_app
from core.auth.service import AuthService

PASSWORD = "correct horse battery staple"


def configured_client() -> tuple[TestClient, AuthService]:
    auth = AuthService()
    auth.setup_admin(PASSWORD)
    return TestClient(create_app(auth)), auth


def login(client: TestClient) -> str:
    response = client.post("/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_first_run_setup_and_argon2id_hashing() -> None:
    auth = AuthService()
    assert auth.setup_required
    auth.setup_admin(PASSWORD)
    assert not auth.setup_required
    assert auth._password_hash is not None
    assert auth._password_hash.startswith("$argon2id$")


def test_unauthenticated_request_is_rejected() -> None:
    client, _ = configured_client()
    assert client.get("/api/me").status_code == 401


def test_bad_host_is_rejected() -> None:
    client, _ = configured_client()
    assert client.get("/auth/status", headers={"host": "evil.example"}).status_code == 400


def test_missing_csrf_is_rejected() -> None:
    client, _ = configured_client()
    login(client)
    assert client.post("/api/change").status_code == 403


def test_valid_session_and_csrf_are_accepted() -> None:
    client, _ = configured_client()
    csrf = login(client)
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/change", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_session_expiry() -> None:
    auth = AuthService(ttl=timedelta(microseconds=1))
    auth.setup_admin(PASSWORD)
    token, _ = auth.authenticate(PASSWORD)
    import time

    time.sleep(0.01)
    try:
        auth.require_session(token)
    except ValueError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired session was accepted")


def test_cors_rejects_untrusted_origin() -> None:
    client, _ = configured_client()
    response = client.options(
        "/api/me",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_session_carries_configured_admin_identity() -> None:
    auth = AuthService(admin_user_id="owner")
    auth.setup_admin(PASSWORD)
    token, _ = auth.authenticate(PASSWORD)
    assert auth.require_session(token).user_id == "owner"


def test_session_identity_defaults_to_admin() -> None:
    auth = AuthService()
    auth.setup_admin(PASSWORD)
    token, _ = auth.authenticate(PASSWORD)
    assert auth.require_session(token).user_id == "admin"


def test_audit_actor_uses_configured_admin_identity() -> None:
    events: list[dict[str, str]] = []

    def record(**event: str) -> None:
        events.append(event)

    auth = AuthService(admin_user_id="owner", audit_callback=record)
    auth.setup_admin(PASSWORD)
    auth.authenticate(PASSWORD)
    assert events
    assert {event["actor"] for event in events} == {"owner"}
