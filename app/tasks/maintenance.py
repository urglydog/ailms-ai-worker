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
    """BR-STORAGE-01: xoa file trung gian (.wav, chunk video) qua 24 gio.

    File .mp3 long tieng thi luu VINH VIEN de tai su dung (BR-DUB-04) —
    tuyet doi khong xoa trong task nay.
    """
    raise NotImplementedError("Se duoc hien thuc o Giai doan 5 (BR-STORAGE-01).")


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
