"""Local SentinelPulse dashboard API for the existing sentiment pipeline."""
from __future__ import annotations

import csv
import json
import os
import re
import secrets
import threading
from contextlib import asynccontextmanager
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR, DATASET, OUTPUT
import auth_service
import security_store
from anomaly import score_windows

@asynccontextmanager
async def lifespan(_app):
    if os.getenv("SENTINEL_ENV", "development").lower() == "production":
        if len(os.getenv("SENTINEL_JWT_SECRET", "")) < 32:
            raise RuntimeError("Set SENTINEL_JWT_SECRET to at least 32 characters in production")
        if os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() != "true":
            raise RuntimeError("Set SENTINEL_COOKIE_SECURE=true behind HTTPS in production")
        if not os.getenv("SENTINEL_DEMO_PASSWORD") or "CHANGE_ME" in os.getenv("SENTINEL_DEMO_PASSWORD", ""):
            raise RuntimeError("Set a strong SENTINEL_DEMO_PASSWORD before production startup")
    security_store.init_db()
    email = os.getenv("SENTINEL_DEMO_EMAIL", "admin@sentinelpulse.local").lower()
    if not security_store.get_user_by_email(email):
        security_store.add_user(email, "SentinelPulse Admin",
            auth_service.hash_password(os.getenv("SENTINEL_DEMO_PASSWORD", "SentinelDemo!2026")), "admin")
    yield


app = FastAPI(title="SentinelPulse", version="1.0.0", description="Social sentiment analytics dashboard", lifespan=lifespan)
STATIC = BASE_DIR / "web"
_lock = threading.RLock()
_demo_active = False
_demo_speed = 1.0
_demo_index = 0
_demo_touched = False
_replay_thread: threading.Thread | None = None
_replay_stop = threading.Event()
_alerts: list[dict[str, Any]] = []
_alert_statuses: dict[str, str] = {}
_records: list[dict[str, Any]] = []
_login_attempts: dict[str, list[float]] = defaultdict(list)
_request_attempts: dict[str, list[float]] = defaultdict(list)
_redis_limiter = None
_allowed_roles = {"admin", "analyst", "viewer"}


class RegisterInput(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=128)


class LoginInput(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class TOTPInput(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class ResetRequest(BaseModel):
    email: str = Field(min_length=6, max_length=254)


class ResetComplete(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=12, max_length=128)


class RoleInput(BaseModel):
    role: str


class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)


def _public(user: dict[str, Any]) -> dict[str, Any]:
    return auth_service.public_user(user)


def require_user(request: Request) -> dict[str, Any]:
    user = auth_service.user_from_token(request.cookies.get(auth_service.ACCESS_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


def require_analyst(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user["role"] not in {"admin", "analyst"}:
        raise HTTPException(status_code=403, detail="Analyst access required")
    return user


def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket):
    token = websocket.cookies.get(auth_service.ACCESS_COOKIE)
    user = auth_service.user_from_token(token)
    origin = websocket.headers.get("origin")
    expected_origin = ("https" if websocket.url.scheme == "wss" else "http") + "://" + websocket.headers.get("host", "")
    if not user or (origin and origin.rstrip("/") != expected_origin.rstrip("/")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    client = None
    pubsub = None
    try:
        if os.getenv("REDIS_URL"):
            import redis.asyncio as aioredis
            client = aioredis.from_url(os.environ["REDIS_URL"], socket_timeout=2)
            pubsub = client.pubsub()
            await pubsub.subscribe("sentinelpulse:live")
        while True:
            if not auth_service.user_from_token(websocket.cookies.get(auth_service.ACCESS_COOKIE)):
                await websocket.close(code=1008)
                return
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1) if pubsub else None
            if message and message.get("data"):
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                await websocket.send_text(data)
            else:
                await websocket.send_json({"type": "heartbeat", "records": len(_data()), "role": user["role"]})
                await __import__("asyncio").sleep(4)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if pubsub:
            await pubsub.unsubscribe("sentinelpulse:live")
            await pubsub.aclose()
        if client:
            await client.aclose()


def redis_rate_allowed(key: str, limit: int, window: int) -> bool | None:
    global _redis_limiter
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        if _redis_limiter is None:
            import redis
            _redis_limiter = redis.Redis.from_url(url, socket_timeout=.15, decode_responses=True)
        pipe = _redis_limiter.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = pipe.execute()
        return int(count) <= limit
    except Exception:
        return None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _spreadsheet_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _read_records() -> list[dict[str, Any]]:
    candidates = [BASE_DIR / "output" / "sentiment_results_enriched.csv", OUTPUT.sentiment_csv_path]
    candidates.extend(OUTPUT.sentiment_csv_dir.glob("part-*.csv"))
    available = [p for p in candidates if p.exists() and p.is_file()]
    path = max(available, key=lambda p: p.stat().st_mtime) if available else None
    sample_path = DATASET.sample_csv_path
    # When the bundled test fixture has just been refreshed, show it until the
    # streaming pipeline writes a newer processed output. This prevents stale
    # checked-in 30-row output snapshots from hiding the 100-row test dataset.
    use_sample = sample_path.exists() and (path is None or sample_path.stat().st_mtime > path.stat().st_mtime)
    rows: list[dict[str, Any]] = []
    if path and not use_sample:
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    tweet = row.get("tweet") or row.get("tweet_text") or row.get("text") or ""
                    if not tweet:
                        continue
                    rows.append({
                        "timestamp": row.get("timestamp") or row.get("produced_at") or "",
                        "tweet": tweet, "brand": row.get("brand") or row.get("entity") or "Other",
                        "username": row.get("username") or row.get("user") or "community",
                        "sentiment": (row.get("sentiment") or row.get("sentiment_label") or "Neutral").title(),
                        "polarity": _number(row.get("polarity")),
                        "subjectivity": _number(row.get("subjectivity")),
                        "confidence": _number(row.get("confidence")),
                    })
        except (OSError, csv.Error):
            pass
    if (use_sample or not rows) and sample_path.exists():
        with sample_path.open(newline="", encoding="utf-8-sig") as f:
            sample_rows = list(csv.DictReader(f))
        for i, row in enumerate(sample_rows):
            label = (row.get("sentiment_label") or "Neutral").title()
            if label not in {"Positive", "Negative", "Neutral"}:
                label = "Neutral"
            polarity = {"Positive": .42, "Negative": -.42, "Neutral": 0}[label]
            rows.append({"timestamp": (datetime.now() - timedelta(minutes=len(sample_rows)-1-i)).isoformat(timespec="seconds"),
                "tweet": row.get("tweet_text", ""), "brand": row.get("entity", "Other"), "username": "community",
                "sentiment": label, "polarity": polarity, "subjectivity": .5, "confidence": .72})
    return rows


def _data() -> list[dict[str, Any]]:
    with _lock:
        if not _records:
            _records.extend(_read_records() or security_store.list_tweets())
            if _records:
                security_store.save_tweets(_records)
        return list(_records)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if int(request.headers.get("content-length", "0") or 0) > 1_048_576:
        return JSONResponse({"detail": "Request body too large"}, status_code=413)
    if request.url.path.startswith(("/api/", "/auth/")):
        ip = request.client.host if request.client else "unknown"
        now_s = datetime.now().timestamp()
        window = 3600 if request.url.path in {"/auth/register", "/auth/password-reset/request"} else 60
        limit = 10 if window == 3600 else 240
        rate_key = f"sentinelpulse:rate:{ip}:{request.url.path if window == 3600 else 'api'}:{int(now_s//window)}"
        redis_allowed = redis_rate_allowed(rate_key, limit, window)
        bucket = _request_attempts[f"{ip}:{request.url.path if window == 3600 else 'api'}"]
        bucket[:] = [stamp for stamp in bucket if now_s-stamp < window]
        if redis_allowed is False or (redis_allowed is None and len(bucket) >= limit):
            return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
        if redis_allowed is None:
            bucket.append(now_s)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        cookie = request.cookies.get(auth_service.CSRF_COOKIE, "")
        header = request.headers.get("x-csrf-token", "")
        if not cookie or not header or not secrets.compare_digest(cookie, header):
            return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/auth/csrf")
def csrf_token(response: Response):
    csrf = secrets.token_urlsafe(24)
    secure = os.getenv("SENTINEL_COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(auth_service.CSRF_COOKIE, csrf, max_age=14*86400, httponly=False,
                        secure=secure, samesite="strict", path="/")
    return {"csrf_token": csrf}


@app.post("/auth/register", status_code=201)
def register(payload: RegisterInput, response: Response):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Enter a valid email address")
    if not auth_service.password_is_valid(payload.password):
        raise HTTPException(422, "Use 12+ characters with upper, lower, number, and symbol")
    if security_store.get_user_by_email(email):
        raise HTTPException(409, "An account with that email already exists")
    try:
        user = security_store.add_user(email, payload.name, auth_service.hash_password(payload.password), "viewer")
    except Exception as exc:
        raise HTTPException(409, "Account could not be created") from exc
    refresh = security_store.issue_refresh(user["id"])
    csrf = auth_service.setup_cookies(response, user, refresh)
    security_store.audit(user["id"], "register", json.dumps({"role": "viewer"}))
    return {"user": _public(user), "csrf_token": csrf}


@app.post("/auth/login")
def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    now_s = datetime.now().timestamp()
    attempts = [t for t in _login_attempts[ip] if now_s-t < 300]
    _login_attempts[ip] = attempts
    if len(attempts) >= 15:
        raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.")
    user = security_store.get_user_by_email(email)
    if not user:
        _login_attempts[ip].append(now_s)
        security_store.audit(None, "login_failed", "{}")
        raise HTTPException(401, "Email or password is incorrect")
    if user.get("locked_until") and datetime.fromisoformat(user["locked_until"]) > security_store.now():
        raise HTTPException(423, "Account temporarily locked. Try again in 15 minutes.")
    if not auth_service.verify_password(user["password_hash"], payload.password):
        _login_attempts[ip].append(now_s)
        security_store.login_failure(user["id"])
        security_store.audit(user["id"], "login_failed", "{}")
        raise HTTPException(401, "Email or password is incorrect")
    factor = security_store.get_totp(user["id"])
    if factor and factor["enabled"]:
        import pyotp
        if not payload.totp_code or not pyotp.TOTP(factor["secret"]).verify(payload.totp_code, valid_window=1):
            raise HTTPException(401, "Enter the 6 digit authenticator code")
    security_store.login_success(user["id"])
    refresh = security_store.issue_refresh(user["id"])
    csrf = auth_service.setup_cookies(response, user, refresh)
    security_store.audit(user["id"], "login", "{}")
    return {"user": _public(user), "csrf_token": csrf}


@app.post("/auth/refresh")
def refresh_session(request: Request, response: Response):
    old = request.cookies.get(auth_service.REFRESH_COOKIE)
    result = security_store.rotate_refresh(old) if old else None
    if not result:
        auth_service.clear_cookies(response)
        raise HTTPException(401, "Session expired. Sign in again.")
    user_id, new_refresh = result
    user = security_store.get_user_by_id(user_id)
    if not user or not user["enabled"]:
        raise HTTPException(401, "Account is unavailable")
    csrf = auth_service.setup_cookies(response, user, new_refresh)
    return {"user": _public(user), "csrf_token": csrf}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    refresh = request.cookies.get(auth_service.REFRESH_COOKIE)
    if refresh:
        security_store.revoke_refresh(refresh)
    user = auth_service.user_from_token(request.cookies.get(auth_service.ACCESS_COOKIE))
    security_store.audit(user["id"] if user else None, "logout", "{}")
    auth_service.clear_cookies(response)
    return {"ok": True}


@app.get("/auth/me")
def current_user(user: dict[str, Any] = Depends(require_user)):
    return {"user": _public(user)}


@app.post("/auth/password")
def change_password(payload: dict[str, str], response: Response, user: dict[str, Any] = Depends(require_user)):
    if set(payload) != {"current_password", "new_password"}:
        raise HTTPException(422, "Provide current_password and new_password")
    if not auth_service.verify_password(user["password_hash"], payload["current_password"]):
        raise HTTPException(400, "Current password is incorrect")
    if not auth_service.password_is_valid(payload["new_password"]):
        raise HTTPException(422, "New password must be 12+ characters with upper, lower, number, and symbol")
    with security_store.connect() as db:
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (auth_service.hash_password(payload["new_password"]), user["id"]))
        db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (security_store.iso(security_store.now()), user["id"]))
    security_store.audit(user["id"], "password_changed", "{}")
    auth_service.clear_cookies(response)
    return {"ok": True, "message": "Password changed. Sign in again."}


@app.post("/auth/totp/setup")
def totp_setup(user: dict[str, Any] = Depends(require_user)):
    import pyotp
    secret = pyotp.random_base32()
    security_store.save_totp(user["id"], secret, False)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="SentinelPulse")
    return {"secret": secret, "otpauth_url": uri, "enabled": False}


@app.post("/auth/totp/enable")
def totp_enable(payload: TOTPInput, user: dict[str, Any] = Depends(require_user)):
    import pyotp
    factor = security_store.get_totp(user["id"])
    if not factor or not pyotp.TOTP(factor["secret"]).verify(payload.code, valid_window=1):
        raise HTTPException(400, "Authenticator code is not valid")
    security_store.save_totp(user["id"], factor["secret"], True)
    security_store.audit(user["id"], "totp_enabled", "{}")
    return {"enabled": True}


@app.post("/auth/totp/disable")
def totp_disable(payload: dict[str, str], user: dict[str, Any] = Depends(require_user)):
    import pyotp
    factor = security_store.get_totp(user["id"])
    if not factor or not auth_service.verify_password(user["password_hash"], payload.get("password", "")):
        raise HTTPException(400, "Could not verify account")
    if not pyotp.TOTP(factor["secret"]).verify(payload.get("code", ""), valid_window=1):
        raise HTTPException(400, "Authenticator code is not valid")
    security_store.remove_totp(user["id"])
    security_store.audit(user["id"], "totp_disabled", "{}")
    return {"enabled": False}


@app.post("/auth/password-reset/request", status_code=202)
def password_reset_request(payload: ResetRequest):
    user = security_store.get_user_by_email(payload.email.strip().lower())
    if user:
        import secrets as secure_random
        token = secure_random.token_urlsafe(32)
        security_store.issue_password_reset(user["id"], token)
        host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
        if host and sender:
            import smtplib
            from email.message import EmailMessage
            from urllib.parse import quote
            msg = EmailMessage()
            msg["Subject"] = "Reset your SentinelPulse password"
            msg["From"] = sender
            msg["To"] = user["email"]
            base = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
            msg.set_content(f"Use this one-time link within 30 minutes: {base}/?reset={quote(token)}")
            port = int(os.getenv("SMTP_PORT", "587"))
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(msg)
        security_store.audit(user["id"], "password_reset_requested", "{}")
    return {"message": "If that account exists, a reset link will be sent."}


@app.post("/auth/password-reset/complete")
def password_reset_complete(payload: ResetComplete):
    if not auth_service.password_is_valid(payload.new_password):
        raise HTTPException(422, "Use 12+ characters with upper, lower, number, and symbol")
    user_id = security_store.consume_password_reset(payload.token)
    if not user_id:
        raise HTTPException(400, "Reset link is invalid or expired")
    with security_store.connect() as db:
        db.execute("UPDATE users SET password_hash=?,failed_logins=0,locked_until=NULL WHERE id=?",
                   (auth_service.hash_password(payload.new_password), user_id))
    security_store.audit(user_id, "password_reset_completed", "{}")
    return {"ok": True, "message": "Password reset. You can now sign in."}


@app.get("/api/profile")
def profile(user: dict[str, Any] = Depends(require_user)):
    return _public(user)


@app.put("/api/profile")
def update_profile(payload: ProfileInput, user: dict[str, Any] = Depends(require_user)):
    with security_store.connect() as db:
        db.execute("UPDATE users SET display_name=? WHERE id=?", (payload.name.strip(), user["id"]))
    security_store.audit(user["id"], "profile_updated", "{}")
    return _public(security_store.get_user_by_id(user["id"]))


@app.get("/api/admin/users")
def admin_users(user: dict[str, Any] = Depends(require_admin)):
    return security_store.list_users()


@app.put("/api/admin/users/{user_id}/role")
def admin_set_role(user_id: str, payload: RoleInput, user: dict[str, Any] = Depends(require_admin)):
    if payload.role not in _allowed_roles:
        raise HTTPException(422, "Role must be admin, analyst, or viewer")
    target = security_store.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if user_id == user["id"] and payload.role != "admin":
        admins = [u for u in security_store.list_users() if u["role"] == "admin" and u["enabled"]]
        if len(admins) <= 1:
            raise HTTPException(409, "Cannot remove the last administrator")
    security_store.set_role(user_id, payload.role)
    security_store.audit(user["id"], "role_changed", json.dumps({"target_user": user_id, "role": payload.role}))
    return {"id": user_id, "role": payload.role}


@app.get("/api/admin/audit")
def admin_audit(limit: int = Query(100, ge=1, le=500), user: dict[str, Any] = Depends(require_admin)):
    return security_store.audit_rows(limit)


def _replay() -> None:
    global _demo_index, _demo_touched
    source = _data()
    if not source:
        return
    while not _replay_stop.wait(max(.125, 1 / _demo_speed)):
        row = dict(source[_demo_index % len(source)])
        _demo_index += 1
        row["timestamp"] = datetime.now().isoformat(timespec="seconds")
        with _lock:
            _records.append(row)
            _demo_touched = True
            if len(_records) > 5000:
                del _records[:1000]
        security_store.save_tweets([row])


def _filtered(records: list[dict[str, Any]], brand: str = "all", sentiment: str = "all", search: str = "", days: str = "all") -> list[dict[str, Any]]:
    rows = [r for r in records if (brand.lower() == "all" or r["brand"].lower() == brand.lower())
            and (sentiment.lower() == "all" or r["sentiment"].lower() == sentiment.lower())
            and (not search or search.lower() in r["tweet"].lower() or search.lower() in r["brand"].lower())]
    if days in {"7", "30", "90"}:
        parsed = []
        for row in rows:
            try:
                dt = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
                parsed.append((row, dt.replace(tzinfo=None)))
            except (ValueError, TypeError):
                continue
        if parsed:
            latest = max(dt for _, dt in parsed)
            cutoff = latest - timedelta(days=int(days))
            rows = [row for row, dt in parsed if dt >= cutoff]
    return rows


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "SentinelPulse", "records": len(_data())}


@app.get("/health")
def liveness():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    try:
        with security_store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ready", "database": "ok", "data_records": len(_data())}
    except Exception as exc:
        raise HTTPException(503, "Service not ready") from exc


@app.get("/metrics")
def prometheus_metrics():
    body = f"sentinelpulse_tweets_loaded {len(_data())}\nsentinelpulse_open_alerts {sum(a['status']=='Open' for a in alerts())}\n"
    return Response(body, media_type="text/plain; version=0.0.4")


@app.post("/api/refresh")
def refresh(user: dict[str, Any] = Depends(require_user)):
    if _demo_touched:
        return {"records": len(_data()), "source": "demo replay"}
    rows = _read_records()
    if rows:
        security_store.save_tweets(rows)
    else:
        rows = security_store.list_tweets()
    with _lock:
        _records.clear()
        _records.extend(rows)
    return {"records": len(rows), "source": "latest CSV"}


@app.get("/api/dashboard")
def dashboard(brand: str = "all", search: str = "", days: str = "all", user: dict[str, Any] = Depends(require_user)):
    rows = _filtered(_data(), brand, "all", search, days)
    n = len(rows) or 1
    counts = Counter(r["sentiment"] for r in rows)
    by_brand: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_minute: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_brand[r["brand"]].append(r)
        stamp = str(r["timestamp"] or "")
        try:
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            key = dt.strftime("%H:%M")
        except ValueError:
            key = "—"
        by_minute[key].append(r)
    return {"total": len(rows), "available_total": len(_data()), "positive": counts["Positive"], "negative": counts["Negative"],
            "neutral": counts["Neutral"], "positive_pct": round(counts["Positive"] / n * 100, 1),
            "negative_pct": round(counts["Negative"] / n * 100, 1),
            "avg_polarity": round(sum(r["polarity"] for r in rows) / n, 3),
            "tweets_per_min": round(len(rows) / 30, 1), "active_alerts": sum(a["status"] == "Open" for a in alerts()),
            "brands": [{"brand": k, "total": len(v), "polarity": round(sum(x["polarity"] for x in v)/len(v), 3),
                        "negative": round(sum(x["sentiment"] == "Negative" for x in v)/len(v)*100)}
                       for k, v in sorted(by_brand.items(), key=lambda p: len(p[1]), reverse=True)],
            "timeline": [{"time": k, "positive": sum(x["sentiment"] == "Positive" for x in v),
                          "negative": sum(x["sentiment"] == "Negative" for x in v),
                          "neutral": sum(x["sentiment"] == "Neutral" for x in v),
                          "polarity": round(sum(x["polarity"] for x in v)/len(v), 3)}
                         for k, v in sorted(by_minute.items())],
            "anomalies": score_windows(rows),
            "brands_list": sorted({r["brand"] for r in _data() if r["brand"] != "Other"})}


@app.get("/api/tweets")
def tweets(brand: str = "all", sentiment: str = "all", search: str = "", days: str = "all", page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=100), user: dict[str, Any] = Depends(require_user)):
    source_rows = _data()
    rows = list(reversed(_filtered(source_rows, brand, sentiment, search, days)))
    start = (page - 1) * limit
    return {"items": rows[start:start+limit], "total": len(rows), "available_total": len(source_rows),
            "page": page, "pages": max(1, (len(rows)+limit-1)//limit)}


@app.get("/api/alerts")
def alerts(user: dict[str, Any] = Depends(require_user)):
    auto = []
    rows = _data()
    neg = sum(r["sentiment"] == "Negative" for r in rows)
    if rows and neg / len(rows) > .3:
        item={"id": "negative-share", "title": "Elevated negative sentiment", "detail": f"{neg/len(rows)*100:.0f}% of the current stream is negative.", "severity": "High"}
        item["status"]=_alert_statuses.get(item["id"]) or security_store.get_alert_status(item["id"]) or "Open"
        item["time"]="Now"
        security_store.save_alert(item)
        auto.append(item)
    for item in score_windows(rows):
        alert={"id": item["id"], "title": item["title"], "detail": item["reason"], "severity": item["severity"]}
        alert["status"]=_alert_statuses.get(alert["id"]) or security_store.get_alert_status(alert["id"]) or "Open"
        alert["time"]=item["window"][:16].replace("T", " ")
        security_store.save_alert(alert)
        auto.append(alert)
    dynamic_ids={a["id"] for a in auto}
    persisted=[a for a in security_store.list_alerts() if a["id"] not in dynamic_ids]
    persisted_ids={a["id"] for a in persisted}
    return auto + persisted + [a for a in reversed(_alerts) if a["id"] not in dynamic_ids and a["id"] not in persisted_ids]


@app.post("/api/alerts/{alert_id}/{action}")
def update_alert(alert_id: str, action: str, user: dict[str, Any] = Depends(require_analyst)):
    if action not in {"acknowledge", "resolve"}:
        return {"error": "Unknown action"}
    _alert_statuses[alert_id] = "Acknowledged" if action == "acknowledge" else "Resolved"
    security_store.update_alert(alert_id, _alert_statuses[alert_id])
    security_store.audit(user["id"], "alert_" + action, json.dumps({"alert_id": alert_id}))
    with _lock:
        for alert in _alerts:
            if alert["id"] == alert_id:
                alert["status"] = "Acknowledged" if action == "acknowledge" else "Resolved"
                return alert
    return {"id": alert_id, "status": "Acknowledged" if action == "acknowledge" else "Resolved"}


@app.get("/api/control")
def control_state(user: dict[str, Any] = Depends(require_user)):
    return {"active": _demo_active, "speed": _demo_speed, "mode": "demo", "source": "local CSV replay"}


@app.post("/api/control/{action}")
def control(action: str, speed: float = Query(1.0, ge=.25, le=8), user: dict[str, Any] = Depends(require_analyst)):
    global _demo_active, _demo_speed, _replay_thread
    if action not in {"start", "pause"}:
        return {"error": "Unknown action"}
    _demo_speed = speed
    _demo_active = action == "start"
    if _demo_active and (_replay_thread is None or not _replay_thread.is_alive()):
        _replay_stop.clear()
        _replay_thread = threading.Thread(target=_replay, name="sentinelpulse-demo-replay", daemon=True)
        _replay_thread.start()
    elif not _demo_active:
        _replay_stop.set()
    return control_state()


@app.post("/api/inject-anomaly")
def inject_anomaly(user: dict[str, Any] = Depends(require_analyst)):
    global _demo_index, _demo_touched
    source = _data()
    neg = [r for r in source if r["sentiment"] == "Negative"]
    seed = neg[_demo_index % len(neg)] if neg else {"brand": "Demo brand", "tweet": "Service is broken and the experience is terrible", "polarity": -.8, "subjectivity": .9, "sentiment": "Negative", "confidence": .9}
    _demo_index += 1
    row = {**seed, "timestamp": datetime.now().isoformat(timespec="seconds"), "tweet": f"[DEMO SPIKE] {seed['tweet']}", "brand": seed["brand"]}
    with _lock:
        _records.append(row)
        _demo_touched = True
        _alerts.append({"id": f"demo-{_demo_index}", "title": f"Negative sentiment spike - {row['brand']}",
            "detail": "Demo anomaly injected into the local stream for dashboard review.", "severity": "High", "status": "Open", "time": "Just now"})
        alert=_alerts[-1]
    security_store.save_tweets([row])
    security_store.save_alert(alert)
    security_store.audit(user["id"], "anomaly_injected", json.dumps({"brand": row["brand"]}))
    return {"tweet": row, "alert": _alerts[-1]}


@app.get("/api/export.csv")
def export_csv(brand: str = "all", sentiment: str = "all", search: str = "", days: str = "all", user: dict[str, Any] = Depends(require_user)):
    import io
    from fastapi.responses import StreamingResponse
    out = io.StringIO()
    fields = ["timestamp", "tweet", "brand", "username", "sentiment", "polarity", "subjectivity", "confidence"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({key: _spreadsheet_safe(value) for key, value in row.items()} for row in _filtered(_data(), brand, sentiment, search, days))
    security_store.audit(user["id"], "export_csv", json.dumps({"brand": brand, "sentiment": sentiment, "days": days}))
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinelpulse-report.csv"})


@app.get("/api/export.pdf")
def export_pdf(brand: str = "all", sentiment: str = "all", search: str = "", days: str = "all", user: dict[str, Any] = Depends(require_user)):
    import html
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    rows = _filtered(_data(), brand, sentiment, search, days)
    counts = Counter(r["sentiment"] for r in rows)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="SentinelPulse sentiment report")
    styles = getSampleStyleSheet()
    story = [Paragraph("SentinelPulse · Sentiment report", styles["Title"]),
        Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} · {len(rows)} mentions", styles["Normal"]), Spacer(1, 14)]
    data = [["Metric", "Value"], ["Positive", str(counts['Positive'])], ["Neutral", str(counts['Neutral'])],
            ["Negative", str(counts['Negative'])], ["Average polarity", f"{sum(r['polarity'] for r in rows)/max(len(rows),1):.3f}"]]
    table = Table(data, colWidths=[180, 100])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#7652d6")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#e8e3ef")),
        ("PADDING", (0,0), (-1,-1), 7)]))
    story.extend([table, Spacer(1, 16), Paragraph("Recent tweets", styles["Heading2"])])
    for row in rows[-30:][::-1]:
        tweet = html.escape(row["tweet"][:300]).replace("\n", " ")
        story.append(Paragraph(f"<b>{html.escape(row['brand'])}</b> · {html.escape(row['sentiment'])} · {row['polarity']:.2f}<br/>{tweet}", styles["BodyText"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    security_store.audit(user["id"], "export_pdf", json.dumps({"brand": brand, "sentiment": sentiment, "days": days}))
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=sentinelpulse-report.pdf"})


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
