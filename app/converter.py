"""
converter.py — yt-dlp + ffmpeg helpers
"""
import functools
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

import imageio_ffmpeg
import yt_dlp


class VideoInfo(TypedDict):
    title: str
    duration_ms: int
    thumbnail: str


def _ffmpeg_bin() -> str:
    """Return the path to a bundled ffmpeg binary (via imageio-ffmpeg).

    Works locally and on hosts without a system ffmpeg (e.g. Render's
    native Python environment).
    """
    return imageio_ffmpeg.get_ffmpeg_exe()


_MAX_DURATION_S: int = 45 * 60  # Videos länger als 45 Minuten werden abgelehnt


@functools.lru_cache(maxsize=1)
def _cookie_file() -> str | None:
    """Schreibt den Inhalt der Env-Var YOUTUBE_COOKIES einmalig in eine Temp-Datei.

    Lokal nicht gesetzt -> gibt None zurück (keine Cookies).
    Auf Render: YOUTUBE_COOKIES = Inhalt einer cookies.txt (Netscape-Format).
    """
    content = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not content:
        return None
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="yt_cookies_"
    )
    f.write(content)
    f.close()
    return f.name


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
        "extractor_args": {"youtube": {"player_client": ["web", "ios", "android"]}},
        **({"cookiefile": _cookie_file()} if _cookie_file() else {}),
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
        "extractor_args": {"youtube": {"player_client": ["web", "ios", "android"]}},
        **({"cookiefile": _cookie_file()} if _cookie_file() else {}),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_ext = info.get("ext", "webm")

    raw_path = os.path.join(tmp_dir, f"raw_audio.{downloaded_ext}")

    # ── 2. Cut + encode to MP3 320k ─────────────────────────────────────────
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    out_path = os.path.join(tmp_dir, f"{filename}.mp3")

    ffmpeg_bin = _ffmpeg_bin()

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


def download_audio(url: str) -> tuple[str, str]:
    """
    Download best audio from *url*, convert to MP3 256k (universally browser-compatible),
    and store in a temporary directory.
    Returns (token, mp3_file_path).
    """
    import uuid
    _sanitize_url(url)

    info = get_video_info(url)
    duration_s = info["duration_ms"] / 1000
    if duration_s > _MAX_DURATION_S:
        mins = int(duration_s // 60)
        raise ValueError(
            f"Video ist zu lang ({mins} min). "
            f"Nur Videos bis {_MAX_DURATION_S // 60} Minuten können verarbeitet werden."
        )

    ffmpeg_bin = _ffmpeg_bin()

    token = uuid.uuid4().hex
    tmp_dir = tempfile.mkdtemp(prefix=f"ytprev_{token}_")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_bin,
        "extractor_args": {"youtube": {"player_client": ["web", "ios", "android"]}},
        **({"cookiefile": _cookie_file()} if _cookie_file() else {}),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "256",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    mp3_path = os.path.join(tmp_dir, "audio.mp3")
    if not os.path.exists(mp3_path):
        raise RuntimeError("MP3-Vorschau-Konvertierung fehlgeschlagen.")

    return token, mp3_path


def convert_segments_to_mp3(
    audio_path: str,
    keep_segments: list,  # list of (start_s: float, end_s: float)
    filename: str,
) -> str:
    """
    Encode *audio_path* keeping only *keep_segments* and produce MP3 320k.
    Returns path to the produced .mp3 file inside a new temp directory.
    """
    ffmpeg_bin = _ffmpeg_bin()

    keep_segments = [(max(0.0, s), e) for s, e in keep_segments if e > s + 0.001]
    if not keep_segments:
        raise ValueError("Keine gültigen Segmente zum Konvertieren.")

    tmp_dir = tempfile.mkdtemp(prefix="ytmp3out_")
    out_path = os.path.join(tmp_dir, f"{filename}.mp3")

    if len(keep_segments) == 1:
        start_s, end_s = keep_segments[0]
        cmd = [
            ffmpeg_bin, "-y",
            "-i", audio_path,
            "-ss", f"{start_s:.3f}",
            "-to", f"{end_s:.3f}",
            "-vn", "-acodec", "libmp3lame", "-b:a", "320k",
            out_path,
        ]
    else:
        parts = []
        for i, (start_s, end_s) in enumerate(keep_segments):
            parts.append(
                f"[0:a]atrim=start={start_s:.3f}:end={end_s:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
        concat_inputs = "".join(f"[a{i}]" for i in range(len(keep_segments)))
        parts.append(f"{concat_inputs}concat=n={len(keep_segments)}:v=0:a=1[out]")
        filter_complex = ";".join(parts)
        cmd = [
            ffmpeg_bin, "-y",
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-acodec", "libmp3lame", "-b:a", "320k",
            out_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler: {result.stderr[-500:]}")

    return out_path
