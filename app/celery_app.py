"""Celery app — tác vụ nặng bất đồng bộ và tác vụ định kỳ.

Hai loại công việc:
  · Theo yêu cầu — UC19 pipeline lồng tiếng, UC25 sinh học liệu.
    Backend LPUSH vào Redis, worker nhận và xử lý.
  · Định kỳ (beat) — các quy tắc có mốc thời gian: BR-STORAGE-01, BR-NOTIFY-01,
    BR-DUB-08.

Chạy:
    celery -A app.celery_app worker --loglevel=info     (service ai-worker)
    celery -A app.celery_app beat   --loglevel=info     (service ai-beat)
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "lms_ai_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.dubbing", "app.tasks.material", "app.tasks.maintenance"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=False,
    # Chỉ nhận thêm task khi đã xử lý xong task hiện tại — quan trọng với task nặng
    # như lồng tiếng, tránh một worker giữ hàng loạt job rồi chết chung.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # BR-CHUNK-04: retry tối đa 3 lần với exponential backoff
    task_default_retry_delay=30,
    task_annotations={
        "*": {"max_retries": settings.max_retry},
    },
)

# ── Tác vụ định kỳ ────────────────────────────────────────────────
# Điền dần theo từng giai đoạn; hàm tương ứng nằm trong app/tasks/maintenance.py.
celery_app.conf.beat_schedule = {
    # BR-STORAGE-01: file trung gian (.wav, chunk video) xoá sau khi job kết thúc,
    # tối đa 24 giờ. Chạy mỗi giờ để dọn phần sót.
    "cleanup-temp-files": {
        "task": "app.tasks.maintenance.cleanup_temp_files",
        "schedule": crontab(minute=0),
    },
    # BR-NOTIFY-01: thông báo đã đọc giữ tối đa 90 ngày rồi tự dọn.
    "cleanup-old-notifications": {
        "task": "app.tasks.maintenance.cleanup_old_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
    # BR-NOTIFY-01: nhắc lịch ôn tập Flashcards trong ngày (SM-2, BR-CARD-01).
    "remind-flashcard-reviews": {
        "task": "app.tasks.maintenance.remind_flashcard_reviews",
        "schedule": crontab(hour=7, minute=0),
    },
    # BR-DUB-08: báo cáo audio không có lượt phát trong 180 ngày, hàng tuần.
    # Hệ thống CHỈ báo cáo — Admin quyết định xoá thủ công, không tự xoá.
    "report-unused-audio": {
        "task": "app.tasks.maintenance.report_unused_audio",
        "schedule": crontab(day_of_week=1, hour=4, minute=0),
    },
}
