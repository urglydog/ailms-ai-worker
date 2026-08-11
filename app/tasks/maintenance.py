"""Tac vu dinh ky (Celery beat) — cac quy tac co moc thoi gian.

Lich chay khai trong app/celery_app.py -> beat_schedule.
Cac task nay goi API noi bo cua backend, KHONG truy cap MySQL truc tiep.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance.cleanup_temp_files")
def cleanup_temp_files() -> dict:
    import os
    import time
    
    target_dir = "/tmp/lms-processing"
    if not os.path.exists(target_dir):
        return {"status": "skipped", "reason": "directory not found"}
        
    deleted_files = 0
    now = time.time()
    cutoff = now - (24 * 3600)  # 24 hours
    
    for root, _, files in os.walk(target_dir):
        for f in files:
            # BR-STORAGE-01: Không xoá file mp3 lồng tiếng (BR-DUB-04)
            if f.endswith('.mp3'):
                continue
                
            filepath = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime < cutoff:
                    os.remove(filepath)
                    deleted_files += 1
            except OSError:
                pass
                
    log.info(f"Cleaned up {deleted_files} old temp files from {target_dir}.")
    return {"status": "success", "deleted_files": deleted_files}


@celery_app.task(name="app.tasks.maintenance.cleanup_old_notifications")
def cleanup_old_notifications() -> dict:
    """BR-NOTIFY-01: xoa thong bao DA DOC qua 90 ngay."""
    raise NotImplementedError("Se duoc hien thuc o Giai doan 9 (BR-NOTIFY-01).")


@celery_app.task(name="app.tasks.maintenance.remind_flashcard_reviews")
def remind_flashcard_reviews() -> dict:
    """BR-NOTIFY-01: nhac hoc vien co the den han on tap hom nay (SM-2)."""
    raise NotImplementedError("Se duoc hien thuc o Giai doan 9 (BR-CARD-01 + BR-NOTIFY-01).")


@celery_app.task(name="app.tasks.maintenance.report_unused_audio")
def report_unused_audio() -> dict:
    """BR-DUB-08: bao cao audio_tracks khong co luot phat trong 180 ngay.

    CHI bao cao cho Admin xem. He thong KHONG tu dong xoa — Admin quyet dinh
    thu cong de tranh mat du lieu ngoai y muon.
    """
    raise NotImplementedError("Se duoc hien thuc o Giai doan 9 (BR-DUB-08).")
