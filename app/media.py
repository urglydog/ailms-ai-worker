"""Tách audio nguồn — FFmpeg (URL MP4 trên B2) hoặc yt-dlp (YouTube).

FFmpeg chạy qua `asyncio.create_subprocess_exec` (KHÔNG dùng `subprocess.run` đồng
bộ) — mục 4 `lms-ai-worker-rules`. yt-dlp tự nó đồng bộ nên bọc `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class FFmpegProcessingError(RuntimeError):
    pass


async def _run_ffmpeg(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise FFmpegProcessingError(
            f"FFmpeg that bai (exit {process.returncode}): {stderr.decode(errors='ignore')[-1000:]}"
        )


async def extract_audio_from_url(source_url: str, out_wav: Path) -> None:
    """Video MP4 đã upload lên B2 (`videoSource=UPLOAD`) — FFmpeg đọc trực tiếp từ URL
    HTTPS, không cần tải nguyên file video về trước.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    await _run_ffmpeg("-i", source_url, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(out_wav))


async def download_youtube_audio(youtube_url: str, out_wav: Path) -> None:
    """`videoSource=YOUTUBE` — chỉ cần audio để bóc băng/lồng tiếng, không cần tải
    video chất lượng cao (Dual Player phát video gốc riêng, xem `core/_1_ytdlp.py`
    để đối chiếu — bản này CHỈ tải audio, nhẹ hơn nhiều so với tải cả video).
    """
    import yt_dlp

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_wav.with_suffix(""))
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": tmpl + ".%(ext)s",
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }],
        "postprocessor_args": ["-ar", "16000", "-ac", "1"],
        "quiet": True,
        "noprogress": True,
    }

    def _download() -> None:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

    await asyncio.to_thread(_download)
    if not out_wav.exists():
        raise FFmpegProcessingError(f"yt-dlp khong tao ra file mong doi: {out_wav}")


async def probe_duration_sec(path: Path) -> float:
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise FFmpegProcessingError(f"ffprobe that bai: {stderr.decode(errors='ignore')[-500:]}")
    raw = stdout.decode().strip()
    return float(raw) if raw else 0.0
