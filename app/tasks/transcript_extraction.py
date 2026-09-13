"""UC34 mở rộng — trích script gốc (Groq ASR, KHÔNG dịch, KHÔNG TTS) ngay khi giảng viên nạp
xong video, thay vì chỉ chạy như một phần của lần lồng tiếng đầu tiên (UC19 cũ). Lý do: UC24/25
(sinh học liệu) theo BR-MAT-01 đọc transcript gốc bất kể bài học đã lồng tiếng hay chưa, nên
transcript gốc cần có SẴN từ lúc nạp video, không chờ tới lần lồng tiếng đầu tiên.

CỐ TÌNH đơn giản hơn hẳn `app/services/dubbing_service.py`: không có khái niệm AiJob, không
chunk-level retry/progress WebSocket (BR-CHUNK-03 "phát được ngay chunk đầu" không áp dụng — chưa
ai xem bài học lúc vừa upload xong). Một chunk lỗi ASR thì bỏ qua đoạn đó, KHÔNG làm hỏng cả job —
transcript thiếu vài câu vẫn còn hữu ích hơn không có gì; nếu bài học chưa có transcript gốc lúc
có người bấm "Lồng tiếng AI", `InternalDubbingService.getContext` tự rơi về hành vi ASR-lại-từ-đầu
quen thuộc (xem `dubbing_service.py` — job này chỉ là một bước tối ưu "chạy trước cho nhanh").

UC30 mở rộng (13/09/2026) — cũng là nơi DUY NHẤT giờ đánh index embedding cho Gia sư AI
(`tutor_indexing.index_segments`) trong đa số trường hợp: từ khi job này tồn tại, dubbing hầu như
luôn `reuse_source=True` (transcript gốc đã có sẵn) nên nhánh đánh index cũ trong
`dubbing_service.py` (chỉ chạy khi ASR THẬT xảy ra ở đó) gần như không còn cơ hội chạy nữa. Lỗi ở
bước đánh index KHÔNG được làm hỏng việc lưu transcript đã ASR xong — bọc try/except riêng.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from decimal import Decimal
from pathlib import Path

from app import audio_utils, media
from app.celery_app import celery_app
from app.config import settings
from app.http import backend_client
from app.models import Segment
from app.providers import gemini, groq_asr
from app.services import tutor_indexing
from app.services.dubbing_service import MIN_SPEECH_RATIO, split_into_chunks

log = logging.getLogger(__name__)


async def _extract_source_transcript(lesson_id: int, video_source: str, video_url: str, duration_sec: int) -> dict:
    work_dir = Path(settings.temp_dir) / f"transcript_{lesson_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        source_audio = work_dir / "source.wav"
        try:
            if video_source == "YOUTUBE":
                await media.download_youtube_audio(video_url, source_audio)
            else:
                await media.extract_audio_from_url(video_url, source_audio)
        except Exception as exc:
            # Không phải BR-DUB-11 thật (không có AiJob/Lesson.status để đánh dấu ở job này) —
            # chỉ đơn giản là job trích script này thất bại, dubbing sau này sẽ tự thử lại.
            log.warning("Khong tach duoc audio lesson %s, bo qua job trich script goc: %s", lesson_id, exc)
            await backend_client.report_source_transcript(lesson_id, outcome="FAILED", error_message=str(exc))
            return {"status": "FAILED", "lessonId": lesson_id, "error": str(exc)}

        actual_duration = duration_sec or int(await media.probe_duration_sec(source_audio))
        chunks = split_into_chunks(actual_duration, settings.chunk_minutes)

        all_segments: list[Segment] = []
        detected_language: str | None = None
        next_seq = 1
        for chunk in chunks:
            chunk_wav = work_dir / f"chunk_{chunk.index}.wav"
            try:
                await audio_utils.extract_range(source_audio, chunk.start_sec, chunk.end_sec, chunk_wav)
                stt = await groq_asr.transcribe(str(chunk_wav))
            except Exception as exc:
                log.warning("Loi ASR doan %s cua lesson %s, bo qua doan nay: %s", chunk.index, lesson_id, exc)
                continue

            chunk_len = chunk.end_sec - chunk.start_sec
            if chunk_len <= 0 or not stt.segments or (stt.speech_duration_sec / chunk_len) < MIN_SPEECH_RATIO:
                continue  # Đoạn lặng/nhạc nền (BR-DUB-10 ở cấp đoạn) — không có gì để lưu.

            detected_language = detected_language or stt.language
            for s in stt.segments:
                all_segments.append(Segment(
                    seq=next_seq, start=chunk.start_sec + s.start, end=chunk.start_sec + s.end, text=s.text,
                ))
                next_seq += 1

        if not all_segments:
            await backend_client.report_source_transcript(
                lesson_id, outcome="SKIPPED", error_message="Video khong co loi thoai dang ke (BR-DUB-10)")
            return {"status": "SKIPPED", "lessonId": lesson_id}

        segment_dtos = [
            backend_client.segment_to_json(seg.seq, Decimal(str(seg.start)), Decimal(str(seg.end)), seg.text)
            for seg in all_segments
        ]
        await backend_client.report_source_transcript(
            lesson_id, outcome="COMPLETED", detected_language=detected_language, segments=segment_dtos)

        try:
            await tutor_indexing.index_segments(lesson_id, detected_language, all_segments)
        except Exception as exc:
            # UC30 — Gia sư AI chỉ mất khả năng tìm nội dung bài này, KHÔNG được làm mất transcript
            # đã lưu thành công ở trên (dòng trước đã báo COMPLETED về be/ rồi).
            log.warning("Danh index embedding cho lesson %s that bai (transcript van da luu): %s", lesson_id, exc)

        return {"status": "COMPLETED", "lessonId": lesson_id, "segments": len(all_segments)}
    except Exception as exc:
        log.exception("Trich script goc that bai cho lesson %s", lesson_id)
        await backend_client.report_source_transcript(lesson_id, outcome="FAILED", error_message=str(exc))
        return {"status": "FAILED", "lessonId": lesson_id, "error": str(exc)}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def _run_and_cleanup(lesson_id: int, video_source: str, video_url: str, duration_sec: int) -> dict:
    try:
        return await _extract_source_transcript(lesson_id, video_source, video_url, duration_sec)
    finally:
        # Xem `app/tasks/dubbing.py::_run_and_cleanup` — client httpx module-level phải đóng ở
        # cuối MỖI task Celery (prefork tái sử dụng process, mỗi task có vòng loop asyncio riêng).
        await asyncio.gather(
            backend_client.aclose(),
            groq_asr.aclose(),
            gemini.aclose(),
            return_exceptions=True,
        )


@celery_app.task(bind=True, name="app.tasks.transcript_extraction.extract_source_transcript")
def extract_source_transcript(self, lesson_id: int, video_source: str, video_url: str, duration_sec: int) -> dict:
    log.info("Bat dau trich script goc: lesson=%s", lesson_id)
    return asyncio.run(_run_and_cleanup(lesson_id, video_source, video_url, duration_sec))
