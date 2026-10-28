"""Cookie-based authentication helpers for the SentinelPulse API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

import security_store as store

ACCESS_COOKIE = "sp_access"
REFRESH_COOKIE = "sp_refresh"
CSRF_COOKIE = "sp_csrf"
ACCESS_TTL = 15 * 60
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
JWT_SECRET = os.getenv("SENTINEL_JWT_SECRET") or secrets.token_urlsafe(48)


def hash_password(password: str) -> str:
    return PASSWORDS.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_access(user: dict[str, Any]) -> str:
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({"sub": user["id"], "role": user["role"], "iat": now,
        "exp": now + ACCESS_TTL, "jti": secrets.token_urlsafe(16)}, separators=(",", ":")).encode())
    message = f"{header}.{payload}".encode("ascii")
    signature = _b64(hmac.new(JWT_SECRET.encode(), message, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access(token: str) -> dict[str, Any] | None:
    try:
        header, payload, signature = token.split(".")
        header_data = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        if header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            return None
        msg = f"{header}.{payload}".encode("ascii")
        expected = _b64(hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data["exp"]) < int(time.time()):
            return None
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def setup_cookies(response, user: dict[str, Any], refresh: str | None = None) -> str:
    secure = os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true"
    csrf = secrets.token_urlsafe(24)
    response.set_cookie(ACCESS_COOKIE, issue_access(user), max_age=ACCESS_TTL, httponly=True,
                        secure=secure, samesite="strict", path="/")
    if refresh:
        response.set_cookie(REFRESH_COOKIE, refresh, max_age=14*86400, httponly=True,
                            secure=secure, samesite="strict", path="/auth")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=14*86400, httponly=False,
                        secure=secure, samesite="strict", path="/")
    return csrf


def clear_cookies(response) -> None:
    secure = os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true"
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, "/auth"), (CSRF_COOKIE, "/")):
        response.delete_cookie(name, path=path, secure=secure, httponly=name != CSRF_COOKIE, samesite="strict")


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "name": user["display_name"], "role": user["role"]}


def user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    claims = decode_access(token)
    if not claims:
        return None
    user = store.get_user_by_id(str(claims.get("sub", "")))
    if not user or not user["enabled"]:
        return None
    return user


def password_is_valid(password: str) -> bool:
    return (len(password) >= 12 and len(password) <= 128 and any(c.islower() for c in password)
            and any(c.isupper() for c in password) and any(c.isdigit() for c in password)
            and any(not c.isalnum() for c in password))
