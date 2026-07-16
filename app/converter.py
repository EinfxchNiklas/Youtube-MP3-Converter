"""
converter.py — yt-dlp + ffmpeg helpers
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

import yt_dlp


class VideoInfo(TypedDict):
    title: str
    duration_ms: int
    thumbnail: str


def _sanitize_url(url: str) -> str:
    """Basic whitelist check: only allow youtube.com and youtu.be URLs."""
    pattern = re.compile(
        r"^https?://(www\.)?(youtube\.com/watch\?.*v=[\w-]+|youtu\.be/[\w-]+)"
    )
    if not pattern.match(url):
        raise ValueError("Nur YouTube-URLs werden unterstützt (youtube.com / youtu.be).")
    return url


def get_video_info(url: str) -> VideoInfo:
    _sanitize_url(url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "bestaudio/best",
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    duration_s: float = info.get("duration") or 0
    thumbnail: str = info.get("thumbnail") or ""
    title: str = info.get("title") or "Unbekannt"

    return VideoInfo(
        title=title,
        duration_ms=int(duration_s * 1000),
        thumbnail=thumbnail,
    )


def convert_to_mp3(url: str, start_ms: int, end_ms: int, filename: str) -> str:
    """
    Download best audio from *url* with yt-dlp, then cut [start_ms, end_ms]
    using ffmpeg (frame-accurate re-encode at 320 kbps).

    Returns the absolute path to the produced .mp3 file inside a temp directory.
    The caller (FileResponse) streams it; cleanup happens via the OS tmp dir.
    """
    _sanitize_url(url)

    tmp_dir = tempfile.mkdtemp(prefix="ytmp3_")
    raw_audio = os.path.join(tmp_dir, "raw_audio.%(ext)s")

    # ── 1. Download best audio ──────────────────────────────────────────────
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": raw_audio,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [],  # no post-processing; ffmpeg handles everything
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_ext = info.get("ext", "webm")

    raw_path = os.path.join(tmp_dir, f"raw_audio.{downloaded_ext}")

    # ── 2. Cut + encode to MP3 320k ─────────────────────────────────────────
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    out_path = os.path.join(tmp_dir, f"{filename}.mp3")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError(
            "ffmpeg nicht gefunden. Terminal neu starten oder installieren: "
            "winget install Gyan.FFmpeg"
        )

    cmd = [
        ffmpeg_bin, "-y",
        "-i", raw_path,
        "-ss", f"{start_s:.3f}",
        "-to", f"{end_s:.3f}",
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "320k",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler: {result.stderr[-500:]}")

    return out_path
