"""Tac vu dinh ky (Celery beat) — cac quy tac co moc thoi gian.

Lich chay khai trong app/celery_app.py -> beat_schedule.
Cac task nay goi API noi bo cua backend, KHONG truy cap MySQL truc tiep.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.celery_app import celery_app
from app.config import settings

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance.cleanup_temp_files")
def cleanup_temp_files() -> dict:
    """BR-STORAGE-01: xoa file trung gian (.wav, chunk video) qua 24 gio.

    File .mp3 lồng tiếng thì lưu VĨNH VIỄN để tái sử dụng (BR-DUB-04) — nhưng chỉ
    SAU KHI đã upload lên B2; mọi thứ còn nằm trong `settings.temp_dir` đều là file
    trung gian, tuyệt đối không có ngoại lệ nào cần giữ lại ở đây.

    `dubbing_service.run_dubbing_pipeline` đã tự dọn thư mục job ngay khi kết thúc
    (nhánh `finally`) — task này chỉ là LƯỚI AN TOÀN cho thư mục mồ côi khi worker
    bị crash/OOM giữa chừng, chạy mỗi giờ theo `celery_app.py::beat_schedule`.
    """
    root = Path(settings.temp_dir)
    if not root.exists():
        return {"removed": 0}

    cutoff = time.time() - settings.intermediate_file_ttl_hours * 3600
    removed = 0
    for entry in root.iterdir():
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            if entry.is_file() and entry.suffix.lower() == ".mp3":
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            log.warning("Khong xoa duoc %s: %s", entry, exc)
    log.info("cleanup_temp_files: da xoa %s muc qua %sh", removed, settings.intermediate_file_ttl_hours)
    return {"removed": removed}


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
