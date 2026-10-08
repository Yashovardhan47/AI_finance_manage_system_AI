from urllib.parse import parse_qs, urlparse

import pytest
from jose import jwt
from pydantic import ValidationError

from app.api.routes import auth as auth_routes
from app.core.config import Settings
from app.core.security import settings as security_settings


def _configure_google(monkeypatch) -> None:
    monkeypatch.setattr(auth_routes.settings, "google_client_id", "google-client.apps.exampleusercontent.com")
    monkeypatch.setattr(auth_routes.settings, "google_client_secret", "google-client-secret")
    monkeypatch.setattr(auth_routes.settings, "google_redirect_uri", "http://testserver/api/v1/auth/google/callback")
    monkeypatch.setattr(auth_routes.settings, "frontend_url", "http://frontend.test")


def _start_google(client) -> tuple[str, str]:
    response = client.get("/api/v1/auth/google", follow_redirects=False)
    assert response.status_code == 302
    authorization_url = urlparse(response.headers["location"])
    assert authorization_url.netloc == "accounts.google.com"
    query = parse_qs(authorization_url.query)
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert query["redirect_uri"] == ["http://testserver/api/v1/auth/google/callback"]
    assert client.cookies.get(auth_routes.OAUTH_CONTEXT_COOKIE)
    return query["state"][0], query["nonce"][0]


def _mock_google_exchange(monkeypatch, *, nonce: str, subject: str, email: str, captured: dict) -> None:
    class TokenResponse:
        is_error = False

        @staticmethod
        def json() -> dict:
            return {"id_token": "verified-google-id-token"}

    class AsyncClient:
        def __init__(self, **_: object):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def post(self, url: str, *, data: dict):
            captured.update({"url": url, "data": data})
            return TokenResponse()

    monkeypatch.setattr(auth_routes.httpx, "AsyncClient", AsyncClient)
    monkeypatch.setattr(
        auth_routes.google_id_token,
        "verify_oauth2_token",
        lambda *_: {
            "sub": subject,
            "email": email,
            "email_verified": True,
            "name": "Google Test User",
            "nonce": nonce,
        },
    )


def test_password_jwt_cookie_bearer_login_and_logout(client):
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "  OWNER@Example.com ",
            "full_name": "JWT Owner",
            "password": "SecurePass123",
            "monthly_income": 75000,
            "minimum_balance": 12000,
        },
    )
    assert registered.status_code == 201
    payload = registered.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "owner@example.com"
    token_payload = jwt.decode(
        payload["access_token"],
        security_settings.jwt_secret,
        algorithms=[security_settings.jwt_algorithm],
    )
    assert token_payload["type"] == "access"
    assert token_payload["email"] == "owner@example.com"
    assert client.cookies.get(auth_routes.ACCESS_COOKIE) == payload["access_token"]
    set_cookie = registered.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    current = client.get("/api/v1/auth/me")
    assert current.status_code == 200
    assert current.json()["full_name"] == "JWT Owner"

    client.cookies.clear()
    bearer = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert bearer.status_code == 200

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.com", "password": "SecurePass123"},
    )
    assert logged_in.status_code == 200
    assert client.cookies.get(auth_routes.ACCESS_COOKIE)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_wrong_password_and_duplicate_registration(client):
    registration = {
        "email": "security@example.com",
        "full_name": "Security User",
        "password": "SecurePass123",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    assert client.post("/api/v1/auth/register", json=registration).status_code == 409
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registration["email"], "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert not client.cookies.get(auth_routes.ACCESS_COOKIE)


def test_auth_methods_report_google_configuration(client, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "google_client_id", None)
    monkeypatch.setattr(auth_routes.settings, "google_client_secret", None)
    response = client.get("/api/v1/auth/methods")
    assert response.status_code == 200
    assert response.json() == {
        "password": True,
        "google": False,
        "google_login_path": "/api/v1/auth/google",
    }
    assert client.get("/api/v1/auth/google", follow_redirects=False).status_code == 503


def test_production_auth_configuration_fails_closed():
    with pytest.raises(ValidationError, match="Production JWT_SECRET"):
        Settings(
            environment="production",
            frontend_url="https://app.example.com",
            jwt_secret="change-this-development-secret",
            _env_file=None,
        )

    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(google_client_id="client-only", _env_file=None)

    with pytest.raises(ValidationError, match="requires secure"):
        Settings(auth_cookie_samesite="none", auth_cookie_secure=False, _env_file=None)

    configured = Settings(
        environment="production",
        jwt_secret="production-secret-with-more-than-32-characters",
        frontend_url="https://app.example.com",
        google_client_id="google-client",
        google_client_secret="google-secret",
        google_redirect_uri="https://api.example.com/api/v1/auth/google/callback",
        _env_file=None,
    )
    assert configured.secure_auth_cookies is True
    assert configured.google_oauth_enabled is True


def test_google_oauth_pkce_callback_creates_billflow_session(client, monkeypatch):
    _configure_google(monkeypatch)
    state, nonce = _start_google(client)
    captured = {}
    _mock_google_exchange(
        monkeypatch,
        nonce=nonce,
        subject="google-subject-001",
        email="google.user@example.com",
        captured=captured,
    )

    callback = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "one-time-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "http://frontend.test/auth/callback?status=success"
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["data"]["code"] == "one-time-code"
    assert captured["data"]["code_verifier"]
    assert captured["data"]["client_secret"] == "google-client-secret"
    assert client.cookies.get(auth_routes.ACCESS_COOKIE)
    assert not client.cookies.get(auth_routes.OAUTH_CONTEXT_COOKIE)
    assert client.get("/api/v1/auth/me").json()["email"] == "google.user@example.com"


def test_google_callback_rejects_state_not_bound_to_browser(client, monkeypatch):
    _configure_google(monkeypatch)
    state, _ = _start_google(client)
    client.cookies.clear()
    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "attacker-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == (
        "http://frontend.test/auth/callback?status=error&error=invalid_oauth_state"
    )
    assert not client.cookies.get(auth_routes.ACCESS_COOKIE)


def test_google_provider_cancellation_returns_frontend_error(client, monkeypatch):
    _configure_google(monkeypatch)
    state, _ = _start_google(client)
    response = client.get(
        "/api/v1/auth/google/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == (
        "http://frontend.test/auth/callback?status=error&error=google_access_denied"
    )
    assert not client.cookies.get(auth_routes.OAUTH_CONTEXT_COOKIE)


def test_google_verified_email_links_existing_password_account(client, monkeypatch):
    _configure_google(monkeypatch)
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "link.me@example.com",
            "full_name": "Existing Password User",
            "password": "SecurePass123",
        },
    )
    original_id = registration.json()["user"]["id"]
    assert client.post("/api/v1/auth/logout").status_code == 204

    state, nonce = _start_google(client)
    _mock_google_exchange(
        monkeypatch,
        nonce=nonce,
        subject="google-subject-linked",
        email="link.me@example.com",
        captured={},
    )
    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "link-code", "state": state},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("status=success")
    assert client.get("/api/v1/auth/me").json()["id"] == original_id


def test_google_callback_rejects_openid_nonce_mismatch(client, monkeypatch):
    _configure_google(monkeypatch)
    state, _ = _start_google(client)
    _mock_google_exchange(
        monkeypatch,
        nonce="nonce-from-a-different-request",
        subject="google-subject-nonce",
        email="nonce@example.com",
        captured={},
    )
    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "wrong-nonce-code", "state": state},
        follow_redirects=False,
    )
    assert response.headers["location"] == (
        "http://frontend.test/auth/callback?status=error&error=google_identity_invalid"
    )
    assert not client.cookies.get(auth_routes.ACCESS_COOKIE)


def test_google_identity_mismatch_does_not_take_over_existing_account(client, monkeypatch):
    _configure_google(monkeypatch)
    first_state, first_nonce = _start_google(client)
    _mock_google_exchange(
        monkeypatch,
        nonce=first_nonce,
        subject="google-subject-owner",
        email="linked@example.com",
        captured={},
    )
    assert client.get(
        "/api/v1/auth/google/callback",
        params={"code": "first-code", "state": first_state},
        follow_redirects=False,
    ).headers["location"].endswith("status=success")
    assert client.post("/api/v1/auth/logout").status_code == 204

    second_state, second_nonce = _start_google(client)
    _mock_google_exchange(
        monkeypatch,
        nonce=second_nonce,
        subject="different-google-subject",
        email="linked@example.com",
        captured={},
    )
    conflict = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "second-code", "state": second_state},
        follow_redirects=False,
    )
    assert conflict.status_code == 302
    assert conflict.headers["location"] == (
        "http://frontend.test/auth/callback?status=error&error=google_account_conflict"
    )
    assert client.get("/api/v1/auth/me").status_code == 401
