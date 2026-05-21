from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()
SESSION_COOKIE_NAME = "lab_session"


class LoginPayload(BaseModel):
    username: str
    password: str


def is_auth_enabled() -> bool:
    return bool(get_settings().auth_password)


def _session_secret() -> str:
    settings = get_settings()
    return settings.auth_session_secret or f"lab::{settings.auth_password or ''}"


def _sign_session_payload(payload: str) -> str:
    digest = hmac.new(_session_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_session_token(username: str) -> str:
    issued_at = int(time.time())
    payload = f"{username}:{issued_at}"
    signature = _sign_session_payload(payload)
    return f"{payload}:{signature}"


def verify_session_token(token: str | None) -> str | None:
    if not token:
        return None
    settings = get_settings()
    parts = token.split(":")
    if len(parts) != 3:
        return None
    username, issued_at_raw, provided_sig = parts
    try:
        issued_at = int(issued_at_raw)
    except ValueError:
        return None
    if int(time.time()) - issued_at > settings.auth_session_ttl_seconds:
        return None
    payload = f"{username}:{issued_at_raw}"
    expected_sig = _sign_session_payload(payload)
    if not hmac.compare_digest(expected_sig, provided_sig):
        return None
    return username


@router.get("/session")
def get_session(token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict:
    if not is_auth_enabled():
        return {"enabled": False, "authenticated": True, "username": None}
    username = verify_session_token(token)
    return {"enabled": True, "authenticated": bool(username), "username": username}


@router.post("/login")
def login(payload: LoginPayload, response: Response) -> dict:
    settings = get_settings()
    if not is_auth_enabled():
        return {"ok": True, "username": None}
    username_ok = hmac.compare_digest(payload.username, settings.auth_username)
    password_ok = hmac.compare_digest(payload.password, settings.auth_password or "")
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = create_session_token(payload.username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        max_age=settings.auth_session_ttl_seconds,
        path="/",
    )
    return {"ok": True, "username": payload.username}


@router.post("/logout")
def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )
    return {"ok": True}
