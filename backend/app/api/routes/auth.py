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


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "billflow_access",
        token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


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
    response.delete_cookie("billflow_access", path="/")


@router.get("/google")
def google_login() -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    now = datetime.now(timezone.utc)
    state = jwt.encode(
        {"type": "oauth_state", "nonce": token_urlsafe(24), "iat": now, "exp": now + timedelta(minutes=10)},
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
            "access_type": "offline",
            "prompt": "select_account",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    try:
        state_payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if state_payload.get("type") != "oauth_state":
            raise ValueError("invalid state")
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_response.is_error:
        raise HTTPException(status_code=401, detail="Google authentication failed")
    raw_id_token = token_response.json().get("id_token")
    try:
        claims = google_id_token.verify_oauth2_token(raw_id_token, google_requests.Request(), settings.google_client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Google identity could not be verified") from exc
    if not claims.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google email is not verified")

    email = claims["email"].lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, full_name=claims.get("name") or email.split("@")[0], google_subject=claims["sub"])
        db.add(user)
        db.flush()
    elif not user.google_subject:
        user.google_subject = claims["sub"]
    write_audit(db, user_id=user.id, action="user.google_login", entity_type="user", entity_id=user.id)
    db.commit()
    token = create_access_token(user.id, user.email)
    redirect = RedirectResponse(f"{settings.frontend_url}/auth/callback")
    set_auth_cookie(redirect, token)
    return redirect

