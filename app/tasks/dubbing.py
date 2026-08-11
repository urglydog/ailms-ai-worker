"""UC19 — pipeline long tieng AI (Celery).

Thu tu buoc day du o skill lms-dubbing-pipeline. Rut gon:
  1. Kiem nguon video con kha dung (BR-DUB-11)
  2. FFmpeg tach audio .wav
  3. Chia phan doan co dinh 10 phut (BR-CHUNK-02)
  4. STT -> Transcript + TranscriptSegment, word-level timestamp (BR-DUB-01)
     Ky am rong hoac thoai < 10% thoi luong -> SKIPPED, KHONG retry (BR-DUB-10)
  5. Dich 3 buoc Gemini (BR-DUB-02)
  6. Adaptive Speech Rate cho tung segment (BR-DUB-03)
  7. Edge-TTS -> AudioChunk
  8. Chunk 0 xong -> publish tien do NGAY, TrackStatus = PARTIAL (BR-CHUNK-03)
  9. Moi chunk COMPLETED -> FFmpeg concat -> final.mp3 (BR-CHUNK-05)
 10. Xoa file trung gian (BR-STORAGE-01), release Redis lock o CA nhanh loi

TAI SU DUNG TU VideoLingo: buoc 1-4 va 8, 10, 11 cua core/ (xem bang trong
doc/DEVELOPMENT_PLAN.md muc 1). TUYET DOI khong dung core/_12_dub_to_vid.py —
Dual Player can video goc muted + .mp3 RIENG, khong ghep vao video.

Thuat toan thuc te da viet lai o app/services/dubbing_service.py voi tham so
tuong minh (khong doc config.yaml toan cuc cua core/) de chay song song nhieu job.
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app
from app.services.dubbing_service import run_dubbing_pipeline

log = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.dubbing.run_pipeline")
def run_pipeline(self, job_id: int, lesson_id: int, video_url: str, target_language: str) -> dict:
    """Chạy toàn bộ pipeline lồng tiếng cho một cặp (bài học, ngôn ngữ).

    Bản thân task này HIẾM KHI cần retry ở cấp Celery — mọi lỗi tạm thời (Groq/Gemini
    429, timeout...) đã được xử lý ở CẤP CHUNK bên trong `run_dubbing_pipeline`
    (BR-CHUNK-04, tối đa `MAX_RETRY` lần/chunk, giữ audio gốc cho chunk hết retry).
    `AiJob.retryCount`/`canRetry()` dành cho Admin bấm "Thử lại" thủ công ở UC45
    (F5.3), không phải để Celery tự động retry lại toàn bộ task ở đây.
    """
    log.info("Bat dau pipeline long tieng: job=%s lesson=%s lang=%s", job_id, lesson_id, target_language)
    return asyncio.run(
        run_dubbing_pipeline(job_id, lesson_id, video_url, target_language, celery_task_id=self.request.id)
    )
