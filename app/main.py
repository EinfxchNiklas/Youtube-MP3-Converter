import asyncio
import os
import re
import shutil
import time
from contextlib import asynccontextmanager
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
from app.converter import get_video_info, convert_to_mp3, download_audio, convert_segments_to_mp3

# token → (absolute path of downloaded audio file, created_at timestamp)
_preview_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 60 * 60  # 1 Stunde

load_dotenv()

BASE_DIR = Path(__file__).parent


def _cleanup_cache() -> None:
    """Entfernt abgelaufene Cache-Einträge und löscht die zugehörigen Temp-Verzeichnisse."""
    now = time.time()
    expired = [t for t, (_, ts) in _preview_cache.items() if now - ts > _CACHE_TTL_SECONDS]
    for token in expired:
        path, _ = _preview_cache.pop(token)
        parent = os.path.dirname(path)
        if os.path.isdir(parent):
            shutil.rmtree(parent, ignore_errors=True)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(15 * 60)  # alle 15 Minuten
        _cleanup_cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="YouTube MP3 Converter", lifespan=lifespan)

# ── Session middleware ──────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-change-in-production")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=False,
    # Kein max_age → Session-Cookie (läuft beim Browser-Schließen ab).
    # Die 4-Stunden-Grenze wird server-seitig in auth.py geprüft.
)

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


# ── Health check (UptimeRobot) ───────────────────────────────────────────────

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


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


@app.post("/api/preview")
async def api_preview(request: Request, _=Depends(require_login)):
    """Download audio from YouTube and cache it for waveform preview + editing."""
    body = await request.json()
    url: str = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Keine URL angegeben.")
    try:
        token, file_path = download_audio(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _preview_cache[token] = (file_path, time.time())
    return JSONResponse({"token": token})


@app.get("/api/audio/{token}")
async def api_audio(token: str, _=Depends(require_login)):
    """Stream the cached audio file so WaveSurfer can decode it in the browser."""
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=400, detail="Ungültiger Token.")
    entry = _preview_cache.get(token)
    file_path = entry[0] if entry else None
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio nicht gefunden.")
    return FileResponse(file_path, media_type="audio/mpeg")


@app.post("/api/convert")
async def api_convert(request: Request, _=Depends(require_login)):
    body = await request.json()
    token: str    = body.get("token", "").strip()
    segments      = body.get("segments", [])   # [{start_ms, end_ms}, ...]
    filename: str = body.get("filename", "audio").strip() or "audio"

    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.()")
    filename = "".join(c for c in filename if c in safe_chars) or "audio"

    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=400, detail="Ungültiger Token.")

    entry = _preview_cache.get(token)
    file_path = entry[0] if entry else None
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio-Preview nicht gefunden. Bitte neu laden.")

    if not segments:
        raise HTTPException(status_code=400, detail="Keine Segmente angegeben.")

    keep_segs = [
        (float(seg["start_ms"]) / 1000.0, float(seg["end_ms"]) / 1000.0)
        for seg in segments
        if seg.get("end_ms", 0) > seg.get("start_ms", 0)
    ]
    if not keep_segs:
        raise HTTPException(status_code=400, detail="Keine gültigen Segmente.")

    try:
        mp3_path = convert_segments_to_mp3(file_path, keep_segs, filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return FileResponse(
        path=mp3_path,
        media_type="audio/mpeg",
        filename=f"{filename}.mp3",
    )
