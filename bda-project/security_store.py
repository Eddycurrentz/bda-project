"""SQLite-backed local identity, refresh-token and audit store.

The Docker deployment can point this at a persistent mounted volume. The API
uses parameterized statements and keeps raw refresh tokens out of the store.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

DB_PATH = Path(os.getenv("SENTINEL_DB_PATH", Path(__file__).parent / "output" / "sentinelpulse.sqlite3"))
_lock = threading.RLock()
_pg_engine = None


class _PgRow(dict):
    def __init__(self, row):
        super().__init__(row._mapping)
        self._values = tuple(row)

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else super().__getitem__(key)


class _PgCursor:
    def __init__(self, result):
        self.result = result
        self.rowcount = result.rowcount

    def fetchone(self):
        row = self.result.fetchone()
        return _PgRow(row) if row is not None else None

    def fetchall(self):
        return [_PgRow(row) for row in self.result.fetchall()]


class _PgConnection:
    def __init__(self):
        global _pg_engine
        url = os.environ["DATABASE_URL"]
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if _pg_engine is None:
            _pg_engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=2)
        self.connection = _pg_engine.connect()
        self.transaction = self.connection.begin()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.transaction.rollback()
        else:
            self.transaction.commit()
        self.connection.close()

    def execute(self, query, params=()):
        if query.strip().upper().startswith("PRAGMA "):
            return _PgCursor(self.connection.execute(text("SELECT 1 WHERE false")))
        # Positional DB API bindings are converted into named SQLAlchemy bindings.
        sql = query
        bind = {}
        index = 0
        def replace(_match):
            nonlocal index
            key = f"p{index}"
            bind[key] = params[index]
            index += 1
            return f":{key}"
        sql = re.sub(r"\?", replace, sql)
        return _PgCursor(self.connection.execute(text(sql), bind))

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


def connect():
    if os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        return _PgConnection()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with _lock, connect() as db:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'viewer',
          enabled INTEGER NOT NULL DEFAULT 1, failed_logins INTEGER NOT NULL DEFAULT 0,
          locked_until TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          family_id TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, event TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS totp_factors (
          user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS password_resets (
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL, used_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sentiment_tweets (
          tweet_hash TEXT PRIMARY KEY, timestamp TEXT NOT NULL, tweet TEXT NOT NULL,
          brand TEXT NOT NULL, username TEXT NOT NULL DEFAULT 'community', sentiment TEXT NOT NULL, polarity REAL NOT NULL,
          subjectivity REAL NOT NULL, confidence REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_tweet_timestamp ON sentiment_tweets(timestamp);
        CREATE INDEX IF NOT EXISTS ix_tweet_brand ON sentiment_tweets(brand);
        CREATE TABLE IF NOT EXISTS alert_statuses (
          alert_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE IF NOT EXISTS alert_events (
          alert_id TEXT PRIMARY KEY, title TEXT NOT NULL, detail TEXT NOT NULL,
          severity TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_events(created_at);
        CREATE INDEX IF NOT EXISTS ix_refresh_user ON refresh_tokens(user_id);
        """
        if os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        db.executescript(schema)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_user(email: str, display_name: str, password_hash: str, role: str = "viewer") -> dict[str, Any]:
    user_id = secrets.token_urlsafe(16)
    with _lock, connect() as db:
        db.execute("INSERT INTO users(id,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                   (user_id, email.lower(), display_name.strip(), password_hash, role, iso(now())))
    return get_user_by_id(user_id) or {}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT id,email,display_name,role,enabled,created_at FROM users ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def set_role(user_id: str, role: str) -> bool:
    with _lock, connect() as db:
        cur = db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        return cur.rowcount == 1


def login_failure(user_id: str) -> int:
    with _lock, connect() as db:
        db.execute("UPDATE users SET failed_logins=failed_logins+1 WHERE id=?", (user_id,))
        row = db.execute("SELECT failed_logins FROM users WHERE id=?", (user_id,)).fetchone()
        failures = int(row[0]) if row else 0
        if failures >= 5:
            db.execute("UPDATE users SET locked_until=? WHERE id=?", (iso(now()+timedelta(minutes=15)), user_id))
        return failures


def login_success(user_id: str) -> None:
    with _lock, connect() as db:
        db.execute("UPDATE users SET failed_logins=0,locked_until=NULL WHERE id=?", (user_id,))


def issue_refresh(user_id: str, family_id: str | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    with _lock, connect() as db:
        db.execute("INSERT INTO refresh_tokens(token_hash,user_id,family_id,expires_at) VALUES(?,?,?,?)",
                   (token_hash(raw), user_id, family_id or secrets.token_urlsafe(18), iso(now()+timedelta(days=14))))
    return raw


def rotate_refresh(raw: str) -> tuple[str, str] | None:
    hashed = token_hash(raw)
    with _lock, connect() as db:
        row = db.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (hashed,)).fetchone()
        if not row:
            return None
        if row["revoked_at"] or datetime.fromisoformat(row["expires_at"]) <= now():
            db.execute("UPDATE refresh_tokens SET revoked_at=COALESCE(revoked_at,?) WHERE family_id=?", (iso(now()), row["family_id"]))
            return None
        db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE token_hash=?", (iso(now()), hashed))
        raw_new = secrets.token_urlsafe(48)
        db.execute("INSERT INTO refresh_tokens(token_hash,user_id,family_id,expires_at) VALUES(?,?,?,?)",
                   (token_hash(raw_new), row["user_id"], row["family_id"], iso(now()+timedelta(days=14))))
        return str(row["user_id"]), raw_new


def revoke_refresh(raw: str) -> None:
    with _lock, connect() as db:
        db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE token_hash=?", (iso(now()), token_hash(raw)))


def audit(user_id: str | None, event: str, detail: str = "{}") -> None:
    with _lock, connect() as db:
        db.execute("INSERT INTO audit_events(user_id,event,detail,created_at) VALUES(?,?,?,?)", (user_id, event, detail[:2000], iso(now())))


def audit_rows(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT id,user_id,event,detail,created_at FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_totp(user_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM totp_factors WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def save_totp(user_id: str, secret: str, enabled: bool) -> None:
    with _lock, connect() as db:
        db.execute("INSERT INTO totp_factors(user_id,secret,enabled) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET secret=excluded.secret, enabled=excluded.enabled",
                   (user_id, secret, int(enabled)))


def remove_totp(user_id: str) -> None:
    with _lock, connect() as db:
        db.execute("DELETE FROM totp_factors WHERE user_id=?", (user_id,))


def issue_password_reset(user_id: str, raw_token: str) -> None:
    with _lock, connect() as db:
        db.execute("UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL", (iso(now()), user_id))
        db.execute("INSERT INTO password_resets(token_hash,user_id,expires_at) VALUES(?,?,?)",
                   (token_hash(raw_token), user_id, iso(now()+timedelta(minutes=30))))


def consume_password_reset(raw_token: str) -> str | None:
    with _lock, connect() as db:
        row = db.execute("SELECT * FROM password_resets WHERE token_hash=?", (token_hash(raw_token),)).fetchone()
        if not row or row["used_at"] or datetime.fromisoformat(row["expires_at"]) <= now():
            return None
        db.execute("UPDATE password_resets SET used_at=? WHERE token_hash=?", (iso(now()), token_hash(raw_token)))
        db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (iso(now()), row["user_id"]))
        return str(row["user_id"])


def save_tweets(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with _lock, connect() as db:
        for row in rows:
            stamp, tweet = str(row.get("timestamp", "")), str(row.get("tweet", ""))
            tweet_hash = hashlib.sha256(f"{stamp}|{tweet}".encode("utf-8")).hexdigest()
            db.execute("INSERT INTO sentiment_tweets(tweet_hash,timestamp,tweet,brand,username,sentiment,polarity,subjectivity,confidence) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tweet_hash) DO NOTHING",
                (tweet_hash, stamp, tweet, str(row.get("brand", "Other")), str(row.get("username", "community")), str(row.get("sentiment", "Neutral")),
                 float(row.get("polarity", 0)), float(row.get("subjectivity", 0)), float(row.get("confidence", 0))))


def list_tweets(limit: int = 5000) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT timestamp,tweet,brand,username,sentiment,polarity,subjectivity,confidence FROM sentiment_tweets ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows][::-1]


def save_alert(alert: dict[str, Any]) -> None:
    stamp = iso(now())
    with _lock, connect() as db:
        db.execute("INSERT INTO alert_events(alert_id,title,detail,severity,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(alert_id) DO UPDATE SET title=excluded.title, detail=excluded.detail, severity=excluded.severity, updated_at=excluded.updated_at",
                   (str(alert["id"]), str(alert["title"]), str(alert.get("detail", "")), str(alert.get("severity", "Medium")),
                    str(alert.get("status", "Open")), stamp, stamp))


def update_alert(alert_id: str, status: str) -> bool:
    with _lock, connect() as db:
        cur = db.execute("UPDATE alert_events SET status=?,updated_at=? WHERE alert_id=?", (status, iso(now()), alert_id))
        if cur.rowcount:
            return True
        cur = db.execute("INSERT INTO alert_statuses(alert_id,status,updated_at) VALUES(?,?,?) ON CONFLICT(alert_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at",
                         (alert_id, status, iso(now())))
        return bool(cur.rowcount)


def get_alert_status(alert_id: str) -> str | None:
    with connect() as db:
        row = db.execute("SELECT status FROM alert_events WHERE alert_id=? UNION ALL SELECT status FROM alert_statuses WHERE alert_id=? LIMIT 1", (alert_id, alert_id)).fetchone()
        return str(row[0]) if row else None


def list_alerts(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT alert_id AS id,title,detail,severity,status,created_at,updated_at FROM alert_events ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
