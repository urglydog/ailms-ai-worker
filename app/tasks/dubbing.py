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
"""

from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.dubbing.run_pipeline")
def run_pipeline(self, job_id: int, lesson_id: int, video_url: str, target_language: str) -> dict:
    """Chay toan bo pipeline long tieng cho mot cap (bai hoc, ngon ngu)."""
    raise NotImplementedError("Se duoc hien thuc o Giai doan 5. Doc skill lms-dubbing-pipeline truoc.")
