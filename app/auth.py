import os
import secrets
from functools import wraps
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse


SESSION_USERNAME_KEY = "authenticated_user"


def _get_credentials() -> tuple[str, str]:
    username = os.environ.get("APP_USERNAME", "admin")
    password = os.environ.get("APP_PASSWORD", "changeme")
    return username, password


def check_credentials(username: str, password: str) -> bool:
    expected_user, expected_pass = _get_credentials()
    user_ok = secrets.compare_digest(username.encode(), expected_user.encode())
    pass_ok = secrets.compare_digest(password.encode(), expected_pass.encode())
    return user_ok and pass_ok


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_USERNAME_KEY))


def require_login(request: Request):
    """FastAPI dependency — redirects to /login if not authenticated."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )


def login_user(request: Request, username: str):
    request.session[SESSION_USERNAME_KEY] = username


def logout_user(request: Request):
    request.session.clear()
