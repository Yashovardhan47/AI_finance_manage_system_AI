import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas import AuthResponse, UserCreate, UserLogin, UserRead
from app.services.audit import write_audit


router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()
ACCESS_COOKIE = "billflow_access"
OAUTH_CONTEXT_COOKIE = "billflow_oauth_context"


def _cookie_options(*, path: str = "/", samesite: str | None = None) -> dict:
    return {
        "httponly": True,
        "secure": settings.secure_auth_cookies,
        "samesite": samesite or settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain or None,
        "path": path,
    }


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=settings.access_token_minutes * 60,
        **_cookie_options(),
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, **_cookie_options())


def _oauth_cookie_path() -> str:
    return f"{settings.api_prefix.rstrip('/')}/auth/google"


def _set_oauth_context_cookie(response: Response, context: str) -> None:
    response.set_cookie(
        OAUTH_CONTEXT_COOKIE,
        context,
        max_age=settings.oauth_state_minutes * 60,
        **_cookie_options(path=_oauth_cookie_path(), samesite="lax"),
    )


def _clear_oauth_context_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_CONTEXT_COOKIE, **_cookie_options(path=_oauth_cookie_path(), samesite="lax"))


def _frontend_auth_redirect(*, success: bool, error: str | None = None) -> RedirectResponse:
    query = {"status": "success" if success else "error"}
    if error:
        query["error"] = error
    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}/auth/callback?{urlencode(query)}",
        status_code=status.HTTP_302_FOUND,
    )
    response.headers["Cache-Control"] = "no-store"
    _clear_oauth_context_cookie(response)
    return response


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    normalized_email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == normalized_email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=normalized_email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        monthly_income=payload.monthly_income,
        minimum_balance=payload.minimum_balance,
    )
    db.add(user)
    db.flush()
    write_audit(db, user_id=user.id, action="user.registered", entity_type="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(user.id, user.email)
    set_auth_cookie(response, token)
    write_audit(db, user_id=user.id, action="user.logged_in", entity_type="user", entity_id=user.id)
    db.commit()
    return AuthResponse(access_token=token, user=user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    clear_auth_cookie(response)


@router.get("/methods")
def authentication_methods() -> dict:
    return {
        "password": True,
        "google": settings.google_oauth_enabled,
        "google_login_path": f"{settings.api_prefix.rstrip('/')}/auth/google",
    }


@router.get("/google")
def google_login() -> RedirectResponse:
    if not settings.google_oauth_enabled:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    now = datetime.now(timezone.utc)
    nonce = token_urlsafe(24)
    code_verifier = token_urlsafe(64)
    state = jwt.encode(
        {
            "type": "oauth_state",
            "nonce": nonce,
            "iat": now,
            "exp": now + timedelta(minutes=settings.oauth_state_minutes),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    context = jwt.encode(
        {
            "type": "oauth_context",
            "nonce": nonce,
            "code_verifier": code_verifier,
            "iat": now,
            "exp": now + timedelta(minutes=settings.oauth_state_minutes),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        status_code=status.HTTP_302_FOUND,
    )
    response.headers["Cache-Control"] = "no-store"
    _set_oauth_context_cookie(response, context)
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not settings.google_oauth_enabled:
        return _frontend_auth_redirect(success=False, error="google_not_configured")
    context_token = request.cookies.get(OAUTH_CONTEXT_COOKIE)
    try:
        if not state or not context_token:
            raise ValueError("missing browser-bound OAuth state")
        state_payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        context_payload = jwt.decode(context_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if state_payload.get("type") != "oauth_state" or context_payload.get("type") != "oauth_context":
            raise ValueError("invalid state")
        if not hmac.compare_digest(str(state_payload.get("nonce", "")), str(context_payload.get("nonce", ""))):
            raise ValueError("state is not bound to this browser")
        code_verifier = str(context_payload["code_verifier"])
    except (JWTError, KeyError, TypeError, ValueError):
        return _frontend_auth_redirect(success=False, error="invalid_oauth_state")
    if error:
        error_code = "google_access_denied" if error == "access_denied" else "google_provider_error"
        return _frontend_auth_redirect(success=False, error=error_code)
    if not code:
        return _frontend_auth_redirect(success=False, error="missing_authorization_code")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
            )
    except httpx.HTTPError:
        return _frontend_auth_redirect(success=False, error="google_token_exchange_failed")
    if token_response.is_error:
        return _frontend_auth_redirect(success=False, error="google_token_exchange_failed")
    try:
        raw_id_token = token_response.json().get("id_token")
    except (AttributeError, ValueError):
        return _frontend_auth_redirect(success=False, error="google_token_exchange_failed")
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception:
        return _frontend_auth_redirect(success=False, error="google_identity_invalid")
    if (
        not claims.get("email_verified")
        or not claims.get("email")
        or not claims.get("sub")
        or not hmac.compare_digest(str(claims.get("nonce", "")), str(state_payload["nonce"]))
    ):
        return _frontend_auth_redirect(success=False, error="google_identity_invalid")

    email = claims["email"].lower()
    subject = claims["sub"]
    user = db.scalar(select(User).where(User.google_subject == subject))
    email_user = db.scalar(select(User).where(User.email == email))
    if user and email_user and user.id != email_user.id:
        return _frontend_auth_redirect(success=False, error="google_account_conflict")
    user = user or email_user
    if not user:
        user = User(email=email, full_name=claims.get("name") or email.split("@")[0], google_subject=subject)
        db.add(user)
        db.flush()
    elif user.google_subject and not hmac.compare_digest(user.google_subject, subject):
        return _frontend_auth_redirect(success=False, error="google_account_conflict")
    else:
        user.google_subject = subject
    write_audit(db, user_id=user.id, action="user.google_login", entity_type="user", entity_id=user.id)
    db.commit()
    token = create_access_token(user.id, user.email)
    redirect = _frontend_auth_redirect(success=True)
    set_auth_cookie(redirect, token)
    return redirect

