import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse


SESSION_USERNAME_KEY = "authenticated_user"
SESSION_LOGIN_TIME_KEY = "login_time"
SESSION_MAX_AGE = timedelta(hours=4)


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
    if not request.session.get(SESSION_USERNAME_KEY):
        return False
    login_time_str = request.session.get(SESSION_LOGIN_TIME_KEY)
    if not login_time_str:
        # Session ohne Zeitstempel (alt) → abmelden
        request.session.clear()
        return False
    try:
        login_time = datetime.fromisoformat(login_time_str)
    except ValueError:
        request.session.clear()
        return False
    if datetime.now(timezone.utc) - login_time > SESSION_MAX_AGE:
        request.session.clear()   # abgelaufen → Session löschen
        return False
    return True


def require_login(request: Request):
    """FastAPI dependency — redirects to /login if not authenticated."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )


def login_user(request: Request, username: str):
    request.session[SESSION_USERNAME_KEY] = username
    request.session[SESSION_LOGIN_TIME_KEY] = datetime.now(timezone.utc).isoformat()


def logout_user(request: Request):
    request.session.clear()
