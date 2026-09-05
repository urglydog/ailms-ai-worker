"""Tách audio nguồn — FFmpeg (URL MP4 trên B2) hoặc yt-dlp (YouTube).

FFmpeg chạy qua `asyncio.create_subprocess_exec` (KHÔNG dùng `subprocess.run` đồng
bộ) — mục 4 `lms-ai-worker-rules`. yt-dlp tự nó đồng bộ nên bọc `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)


class FFmpegProcessingError(RuntimeError):
    pass


def _load_youtube_proxies() -> list[str]:
    """BUG THẬT (05/09/2026) — xem docstring `download_youtube_audio` để biết vì sao cần proxy
    dân dụng. Đọc `settings.youtube_proxy_list_path`, MỖI DÒNG 1 proxy, chấp nhận 2 dạng để không
    phụ thuộc 1 nhà cung cấp cụ thể:
      - URL đầy đủ: `http://user:pass@host:port` (DataImpulse và đa số nhà cung cấp residential
        hiện đại — thường chỉ 1 dòng, 1 cổng gateway duy nhất tự luân chuyển IP phía sau).
      - `host:port:user:pass` (Webshare và vài nhà cung cấp cũ — nhiều dòng, mỗi dòng 1 IP cố định).
    File không tồn tại/rỗng -> trả về `[]`, `download_youtube_audio` tự hiểu là "không dùng proxy",
    tải thẳng như trước đây — không bắt buộc phải có proxy mới chạy được.
    """
    path = settings.youtube_proxy_list_path
    if not path or not os.path.exists(path):
        return []
    proxies: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" in line:
                proxies.append(line)
                continue
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, password = parts
                proxies.append(f"http://{user}:{password}@{host}:{port}")
            else:
                log.warning("Bo qua dong proxy khong dung dinh dang trong %s: %s", path, line)
    return proxies


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

    BUG THẬT (05/09/2026): yt-dlp bị YouTube chặn ("Sign in to confirm you're not a bot") khi tải
    trực tiếp từ IP datacenter/VPS thật của server production. Đã XÁC NHẬN THẬT 10 proxy MIỄN PHÍ
    dạng datacenter (dùng chung, dễ bị liệt sẵn vào blacklist) KHÔNG giải quyết được — vẫn bị chặn
    y hệt trên cả 4/4 proxy đã thử, có lúc còn kèm 429 Too Many Requests. Chỉ proxy RESIDENTIAL
    thật (trả phí, IP trông như 1 kết nối Internet nhà dân) mới có tác dụng thật sự — xem
    `_load_youtube_proxies`/`secrets/README.md`. Thử lần lượt các proxy theo thứ tự xáo trộn ngẫu
    nhiên (dàn tải qua nhiều IP thay vì luôn đi cùng 1 IP — giảm khả năng chính IP đó bị chặn dần
    theo thời gian), dùng proxy tiếp theo nếu cái trước lỗi. Không có proxy nào cấu hình -> tải
    thẳng như trước đây, hành vi y hệt (không bắt buộc phải có proxy mới chạy được).
    """
    import yt_dlp

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_wav.with_suffix(""))
    base_opts = {
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
        proxies = _load_youtube_proxies()
        if not proxies:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                ydl.download([youtube_url])
            return

        shuffled = proxies[:]
        random.shuffle(shuffled)
        last_error: Exception | None = None
        for proxy in shuffled:
            try:
                with yt_dlp.YoutubeDL({**base_opts, "proxy": proxy}) as ydl:
                    ydl.download([youtube_url])
                return
            except Exception as e:
                last_error = e
                log.warning("Proxy loi khi tai audio YouTube, thu proxy khac: %s", e)
        if last_error is not None:
            raise last_error

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
