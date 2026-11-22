"""M2 — giữ nhạc nền của audio gốc trong bản lồng tiếng (thử nghiệm, bật bằng `BGM_SEPARATION=modal`).

Trước đây bản lồng tiếng chỉ có giọng đọc đặt trên nền im lặng -> mọi đoạn nhạc/hiệu ứng của video
gốc bị mất (video phát tắt tiếng, người học chỉ nghe file MP3 lồng tiếng).

Luồng:
  1. `start_separation`: ngay sau khi tải audio gốc, gửi lên hàm Demucs đã deploy trên Modal
     (`modal_apps/demucs_separator.py`) để tách phần KHÔNG có giọng người. Chạy NỀN, song song với
     ASR -> dịch -> TTS, nên gần như không cộng thêm thời gian.
  2. `mix_into_chunk`: trước khi upload mỗi chunk, trộn phần nhạc của đúng đoạn đó dưới giọng lồng
     tiếng. Nhạc giữ NGUYÊN âm lượng gốc (người làm video đã cân sẵn nhạc so với giọng), còn giọng
     lồng tiếng được chỉnh cho TO BẰNG giọng gốc (đo trên phần giọng Demucs tách ra, chuẩn EBU R128)
     -> tỉ lệ giọng/nhạc giống bản gốc. Tự hạ nhạc khi có lời (ducking) chỉ là tuỳ chọn
     (`BGM_DUCKING`) để che phần giọng gốc còn sót trong nhạc nếu có.
Nhạc/giọng đã tách được lưu lên B2 theo (bài học, video) -> lồng tiếng bài đó sang ngôn ngữ khác
dùng lại, không gọi GPU lần nữa.
Mọi lỗi ở đây chỉ log cảnh báo và giữ bản lồng tiếng không nhạc như cũ — KHÔNG làm hỏng job.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from pathlib import Path

from app import audio_utils, storage
from app.config import settings

log = logging.getLogger(__name__)


def start_separation(
    source_audio: Path, work_dir: Path, lesson_id: int | None = None, video_url: str | None = None,
) -> asyncio.Task | None:
    if settings.bgm_separation != "modal":
        return None
    return asyncio.create_task(_separate(source_audio, work_dir, cache_prefix(lesson_id, video_url)))


_warm_tasks: set[asyncio.Task] = set()


def warm_up(lesson_id: int | None, video_url: str | None) -> asyncio.Task | None:
    """Đánh thức GPU trên Modal ngay đầu job (không chờ): container khởi động (~15–20 s) song song
    với việc tải audio gốc, đến lúc gửi file thật thì máy đã sẵn sàng. Bài đã có nhạc trên B2 thì bỏ
    qua (không cần GPU). Lỗi chỉ log — đây thuần là tối ưu."""
    if settings.bgm_separation != "modal" or not settings.bgm_warm_up:
        return None
    task = asyncio.create_task(_warm(cache_prefix(lesson_id, video_url)))
    _warm_tasks.add(task)
    task.add_done_callback(_warm_tasks.discard)
    return task


async def _warm(prefix: str | None) -> None:
    t0 = time.monotonic()
    try:
        if prefix and await storage.exists(f"{prefix}/vocals.mp3"):
            return
        import modal

        await modal.Function.from_name(settings.bgm_modal_app, "separate").remote.aio(b"", ".mp3")
        log.info("BGM da danh thuc GPU tach nhac: %.1fs", time.monotonic() - t0)
    except Exception as exc:
        log.warning("BGM khong danh thuc duoc GPU (bo qua): %s", exc)


def cache_prefix(lesson_id: int | None, video_url: str | None) -> str | None:
    """Khoá cache trên B2: theo bài học VÀ video (đổi video thì không dùng nhầm nhạc cũ)."""
    if lesson_id is None or not video_url:
        return None
    digest = hashlib.sha1(video_url.encode("utf-8")).hexdigest()[:12]
    return f"bgm/{lesson_id}/{digest}"


async def _separate(source_audio: Path, work_dir: Path, prefix: str | None = None) -> Path | None:
    t0 = time.monotonic()
    music = work_dir / "bgm_music.mp3"
    vocals = _vocals_path(music)
    if prefix and await storage.download_file(f"{prefix}/music.mp3", music)             and await storage.download_file(f"{prefix}/vocals.mp3", vocals):
        log.info("BGM dung lai nhac da tach tren B2 (%s): %.1fs, khong goi GPU", prefix, time.monotonic() - t0)
        return music
    try:
        import modal

        from app import source_audio as _src

        source_audio = await _src.ensure(source_audio)   # tối ưu B: audio gốc có thể chưa được tải
        upload = work_dir / "bgm_source.mp3"
        # gửi MP3 thay vì WAV: nhỏ hơn ~10 lần, Demucs vẫn tách tốt. 128 kbps thay cho 192 kbps
        # (22/11/2026): bài 6 phút 9 MB -> 6 MB, chuyển mã vẫn ~2,5 s — gửi lên Modal nhanh hơn 1/3.
        await audio_utils._ffmpeg(
            "-i", str(source_audio), "-ac", "2", "-ar", "44100", "-b:a", settings.bgm_upload_bitrate, str(upload),
        )
        fn = modal.Function.from_name(settings.bgm_modal_app, "separate")
        result = await fn.remote.aio(upload.read_bytes(), ".mp3")
        music.write_bytes(result["music"])
        if result.get("vocals"):
            vocals.write_bytes(result["vocals"])
        log.info(
            "BGM tach nhac xong: tren Modal %.1fs, tong %.1fs",
            result.get("separate_sec", -1), time.monotonic() - t0,
        )
        if prefix and vocals.exists():
            # Lưu cache lên B2 chạy NỀN — không bắt bước trộn chờ upload (job 40: chờ thêm ~150 s
            # vì upload 2 file trên mạng chậm). `wait_pending_uploads` đợi nó trước khi dọn thư mục job.
            task = asyncio.create_task(_upload_cache(music, vocals, prefix))
            _pending_uploads.add(task)
            task.add_done_callback(_pending_uploads.discard)
        return music
    except Exception as exc:
        log.warning("BGM tach nhac that bai sau %.1fs — giu ban long tieng khong nhac: %s", time.monotonic() - t0, exc)
        return None


_pending_uploads: set[asyncio.Task] = set()


async def _upload_cache(music: Path, vocals: Path, prefix: str) -> None:
    t0 = time.monotonic()
    try:
        await asyncio.gather(
            storage.upload_file(music, f"{prefix}/music.mp3"),
            storage.upload_file(vocals, f"{prefix}/vocals.mp3"),
        )
        log.info("BGM da luu nhac len B2 (%s): %.1fs", prefix, time.monotonic() - t0)
    except Exception as exc:  # cache chỉ là tối ưu
        log.warning("BGM khong luu duoc nhac len B2: %s", exc)


async def wait_pending_uploads(timeout_sec: float = 300) -> None:
    """Gọi TRƯỚC khi xoá thư mục tạm của job: đợi các lượt lưu cache B2 đang chạy nền xong."""
    if _pending_uploads:
        await asyncio.wait(list(_pending_uploads), timeout=timeout_sec)


_MAX_GAIN_DB = 12.0


def _vocals_path(music: Path) -> Path:
    return music.with_name("bgm_vocals.mp3")


async def measure_loudness_lufs(path: Path, start_sec: float | None = None, end_sec: float | None = None) -> float | None:
    """Độ to tích hợp (LUFS, EBU R128) của file, hoặc của đoạn [start_sec, end_sec) — None nếu im lặng.

    Dùng bộ lọc `ebur128` (nhẹ hơn `loudnorm`) và cắt đoạn ngay ở đầu vào (`-ss/-to`) thay vì xuất
    file mp3 trung gian rồi mới đo — bớt 1 lượt giải mã + mã hoá cho mỗi chunk.
    """
    seek = ["-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}"] if start_sec is not None and end_sec is not None else []
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-nostats", *seek, "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _out, err = await process.communicate()
    found = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", err.decode(errors="ignore"))
    if process.returncode != 0 or not found or found[-1] == "-inf":
        return None
    value = float(found[-1])
    return value if value > -70 else None   # cực nhỏ = im lặng


def loudness_gain_db(dub_lufs: float | None, original_vocals_lufs: float | None) -> float:
    """Số dB cần cộng vào giọng lồng tiếng để to bằng giọng gốc (kẹp ±12 dB cho an toàn)."""
    if dub_lufs is None or original_vocals_lufs is None:
        return 0.0
    return max(-_MAX_GAIN_DB, min(_MAX_GAIN_DB, original_vocals_lufs - dub_lufs))


async def mix_into_chunk(
    chunk_audio: Path, music_task: asyncio.Task | None, start_sec: float, end_sec: float, work_dir: Path,
) -> bool:
    """Trộn nhạc nền đoạn [start_sec, end_sec) dưới `chunk_audio` (ghi đè tại chỗ). Trả True nếu đã trộn."""
    if music_task is None:
        return False
    t0 = time.monotonic()
    try:
        music = await asyncio.wait_for(asyncio.shield(music_task), timeout=settings.bgm_wait_timeout_sec)
    except asyncio.TimeoutError:
        log.warning("BGM: cho tach nhac qua %ss — chunk nay khong co nhac nen", settings.bgm_wait_timeout_sec)
        return False
    if music is None:
        return False
    waited = time.monotonic() - t0
    try:
        mixed = work_dir / f"bgm_mixed_{int(start_sec)}.mp3"

        # Khớp độ to giọng lồng tiếng với giọng gốc của CHÍNH đoạn này (2 phép đo chạy song song).
        dub_gain_db = 0.0
        vocals = _vocals_path(music)
        if vocals.exists():
            dub_lufs, orig_lufs = await asyncio.gather(
                measure_loudness_lufs(chunk_audio), measure_loudness_lufs(vocals, start_sec, end_sec),
            )
            dub_gain_db = loudness_gain_db(dub_lufs, orig_lufs)
            log.info("BGM do to: giong long tieng %s LUFS, giong goc %s LUFS -> chinh %+.1f dB", dub_lufs, orig_lufs, dub_gain_db)

        music_chain = f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={settings.bgm_music_volume}[mus];"
        dub_chain = f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={dub_gain_db:.2f}dB"
        if settings.bgm_ducking:
            graph = (
                dub_chain + ",asplit=2[dub][sc];" + music_chain
                + "[mus][sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=350[bg];"
                "[bg][dub]amix=inputs=2:normalize=0:duration=first[out]"
            )
        else:
            graph = dub_chain + "[dub];" + music_chain + "[mus][dub]amix=inputs=2:normalize=0:duration=longest[mix];[mix]alimiter=limit=0.97[out]"
        # Cắt đúng đoạn nhạc ngay ở đầu vào thứ 2 -> 1 lượt FFmpeg duy nhất, không file trung gian.
        await audio_utils._ffmpeg(
            "-i", str(chunk_audio), "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}", "-i", str(music),
            "-filter_complex", graph,
            "-map", "[out]", "-t", f"{end_sec - start_sec:.3f}", "-b:a", settings.bgm_mix_bitrate, str(mixed),
        )
        mixed.replace(chunk_audio)
        log.info(
            "BGM tron nhac chunk %s-%ss: cho %.1fs, tron %.1fs (giong %+.1f dB, nhac x%s, ducking=%s)",
            int(start_sec), int(end_sec), waited, time.monotonic() - t0 - waited,
            dub_gain_db, settings.bgm_music_volume, settings.bgm_ducking,
        )
        return True
    except Exception as exc:
        log.warning("BGM tron nhac that bai — giu ban long tieng khong nhac: %s", exc)
        return False
