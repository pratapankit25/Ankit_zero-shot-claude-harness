"""Auth: scrypt password hashing (stdlib — no extra deps), DB-backed sessions,
open-until-first-admin bootstrap. (spec/capabilities/auth-rbac.md)

Bootstrap model: with ZERO users the app runs open (single-user prototype mode)
and the admin panel offers "create the first admin". The moment a user exists,
every data endpoint requires a session.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from config.settings import get_settings
from db.models import SessionRow, UserRow
from db.session import create_db_session

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def any_users_exist() -> bool:
    with create_db_session() as s:
        return s.query(UserRow.id).first() is not None


def create_user(username: str, password: str, role: str, district: str | None = None) -> dict:
    with create_db_session() as s:
        user = UserRow(
            username=username.strip().lower(),
            password_hash=hash_password(password),
            role=role,
            district=(district or None),
        )
        s.add(user)
        s.flush()
        return {"id": user.id, "username": user.username, "role": user.role, "district": user.district}


def login(username: str, password: str) -> str | None:
    """Returns a session token, or None on bad credentials."""
    with create_db_session() as s:
        user = s.query(UserRow).filter(UserRow.username == username.strip().lower()).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        token = secrets.token_urlsafe(32)
        s.add(SessionRow(
            token=token,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=get_settings().session_hours),
        ))
        return token


def logout(token: str) -> None:
    with create_db_session() as s:
        row = s.get(SessionRow, token)
        if row is not None:
            s.delete(row)


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    with create_db_session() as s:
        sess = s.get(SessionRow, token)
        if sess is None:
            return None
        expires = sess.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            s.delete(sess)
            return None
        user = s.get(UserRow, sess.user_id)
        if user is None:
            return None
        return {"id": user.id, "username": user.username, "role": user.role, "district": user.district}
