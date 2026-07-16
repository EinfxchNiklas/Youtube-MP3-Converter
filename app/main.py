import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    check_credentials,
    is_authenticated,
    login_user,
    logout_user,
    require_login,
)
from app.converter import get_video_info, convert_to_mp3

load_dotenv()

# Windows: user-PATH aus Registry laden damit winget-installiertes ffmpeg gefunden wird
import sys as _sys
if _sys.platform == "win32":
    try:
        import winreg as _reg
        _key = _reg.OpenKey(_reg.HKEY_CURRENT_USER, "Environment")
        _user_path, _ = _reg.QueryValueEx(_key, "Path")
        _reg.CloseKey(_key)
        os.environ["PATH"] = os.environ.get("PATH", "") + ";" + _user_path
    except Exception:
        pass

BASE_DIR = Path(__file__).parent

app = FastAPI(title="YouTube MP3 Converter")

# ── Session middleware ──────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=False)

# ── Static files & templates ────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Auth routes ─────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if check_credentials(username, password):
        login_user(request, username)
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Ungültiger Benutzername oder Passwort."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


# ── Main app route ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _=Depends(require_login)):
    return templates.TemplateResponse("index.html", {"request": request})


# ── API routes ───────────────────────────────────────────────────────────────

@app.post("/api/info")
async def api_info(request: Request, _=Depends(require_login)):
    body = await request.json()
    url: str = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Keine URL angegeben.")
    try:
        info = get_video_info(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(info)


@app.post("/api/convert")
async def api_convert(request: Request, _=Depends(require_login)):
    body = await request.json()
    url: str = body.get("url", "").strip()
    start_ms: int = int(body.get("start_ms", 0))
    end_ms: int = int(body.get("end_ms", 0))
    filename: str = body.get("filename", "audio").strip() or "audio"

    # Basic sanitise – keep only safe chars
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.()")
    filename = "".join(c for c in filename if c in safe_chars) or "audio"

    if not url:
        raise HTTPException(status_code=400, detail="Keine URL angegeben.")
    if end_ms <= start_ms:
        raise HTTPException(status_code=400, detail="Endzeit muss nach der Startzeit liegen.")

    try:
        mp3_path = convert_to_mp3(url, start_ms, end_ms, filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return FileResponse(
        path=mp3_path,
        media_type="audio/mpeg",
        filename=f"{filename}.mp3",
        background=None,  # we clean up in converter via tmp dir
    )
