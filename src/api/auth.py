import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, field_validator

from api._common import api_error, ok
from auth import core

router = APIRouter()

# small TTL cache so every request doesn't hit the users table
_users_exist_cache: dict = {"value": None, "at": 0.0}


def users_exist_cached() -> bool:
    now = time.monotonic()
    if _users_exist_cache["value"] is None or now - _users_exist_cache["at"] > 5:
        _users_exist_cache["value"] = core.any_users_exist()
        _users_exist_cache["at"] = now
    return _users_exist_cache["value"]


def invalidate_users_cache() -> None:
    _users_exist_cache["value"] = None


def require_user(request: Request) -> dict | None:
    """None in open mode (no users yet)."""
    return getattr(request.state, "user", None)


def require_role(request: Request, *roles: str) -> dict | None:
    if not users_exist_cached():
        return None  # open mode — single-user prototype
    user = require_user(request)
    if user is None:
        raise api_error("AUTH_REQUIRED", "Login required.", 401)
    if roles and user["role"] not in roles:
        raise api_error("FORBIDDEN", "Your role does not allow this action.", 403)
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


class BootstrapRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 3:
            raise ValueError("username must be at least 3 characters")
        return v

    @field_validator("password")
    @classmethod
    def _p(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


@router.get("/auth/me")
def me(request: Request) -> dict:
    return ok({
        "auth_required": users_exist_cached(),
        "user": getattr(request.state, "user", None),
    })


@router.post("/auth/bootstrap")
def bootstrap(req: BootstrapRequest, response: Response) -> dict:
    """Create the FIRST admin — only possible while zero users exist."""
    if core.any_users_exist():
        raise api_error("ALREADY_SET_UP", "Login is already configured — ask an admin.", 409)
    user = core.create_user(req.username, req.password, role="admin")
    invalidate_users_cache()
    token = core.login(req.username, req.password)
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return ok({"user": user})


@router.post("/auth/login")
def login(req: LoginRequest, response: Response) -> dict:
    token = core.login(req.username, req.password)
    if token is None:
        raise api_error("BAD_CREDENTIALS", "Wrong username or password.", 401)
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return ok({"user": core.user_for_token(token)})


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get("session")
    if token:
        core.logout(token)
    response.delete_cookie("session")
    return ok({"logged_out": True})
