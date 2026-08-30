"""Admin endpoints — thống kê nội bộ cho Admin Dashboard.

Không yêu cầu JWT (đã kiểm soát bởi INTERNAL_API_TOKEN header).
Chỉ dùng trong mạng nội bộ Docker; không expose ra ngoài.
"""

from __future__ import annotations

import logging

import redis as redis_sync
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

from app.celery_app import celery_app
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_internal_token(x_internal_token: Optional[str] = Header(default=None)):
    """Bảo vệ endpoint — chỉ backend nội bộ mới có token này."""
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Forbidden: invalid internal token")


class CancelJobReq(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # `be/` gửi JSON camelCase (khớp quy ước REST của cả dự án).
    celery_task_id: Optional[str] = Field(default=None, alias="celeryTaskId")


@router.post("/dubbing-jobs/{job_id}/cancel", dependencies=[Depends(_verify_internal_token)])
async def cancel_dubbing_job(job_id: int, req: CancelJobReq) -> dict:
    """UC20 — `be/` gọi khi học viên bấm huỷ. `be/` ĐÃ ghi `AiJob.status=CANCELLED` trước khi
    gọi tới đây rồi (nguồn sự thật là DB) — việc ở đây chỉ là cố dừng tiến trình Celery đang
    chạy THẬT SỚM, tránh tốn thêm request Gemini/Groq/Azure vô ích cho một job đã bị huỷ.

    `terminate=True` gửi SIGTERM cho đúng process con (prefork pool) đang chạy task này —
    Celery tự thay process con mới, KHÔNG ảnh hưởng các job khác đang chạy song song trong
    cùng worker (khác hẳn cách chữa cháy thủ công trước đây: `docker restart` cả container,
    giết luôn mọi job đang chạy chứ không chỉ job bị huỷ). `revoke()` cũng tự ghi nhớ
    `celery_task_id` này vào danh sách "đã huỷ" trên mọi worker, nên nếu message vô tình được
    phát lại (redelivery do `task_acks_late=True`) thì cũng không chạy lại nữa.
    """
    if not req.celery_task_id:
        return {"cancelled": False, "reason": "job chua duoc AI Worker nhan (chua co celery_task_id)"}

    celery_app.control.revoke(req.celery_task_id, terminate=True, signal="SIGTERM")
    log.info("Job %s: da gui lenh huy Celery task %s", job_id, req.celery_task_id)
    return {"cancelled": True}


@router.get("/queue-stats", dependencies=[Depends(_verify_internal_token)])
async def get_queue_stats() -> dict:
    """Thống kê hàng đợi Celery qua Redis.

    Trả về:
    - pending: số task đang chờ trong từng queue
    - active: task đang chạy (từ celery inspect nếu có)
    - key_pool: trạng thái các Gemini API key (active/cooldown)
    """
    try:
        r = redis_sync.from_url(settings.redis_url, decode_responses=True)

        # Celery mặc định dùng key "celery" cho default queue
        queue_names = ["celery"]
        queues = {}
        for q in queue_names:
            length = r.llen(q)
            queues[q] = {"pending": length}

        # Thống kê các task result (PENDING/SUCCESS/FAILURE)
        # Celery lưu result dạng celery-task-meta-<uuid>
        result_keys = r.keys("celery-task-meta-*")
        stats = {"SUCCESS": 0, "FAILURE": 0, "PENDING": 0, "STARTED": 0}
        for key in result_keys[:200]:  # Giới hạn 200 key để tránh chậm
            try:
                import json
                val = r.get(key)
                if val:
                    data = json.loads(val)
                    status = data.get("status", "PENDING")
                    if status in stats:
                        stats[status] += 1
            except Exception:
                pass

        # Trạng thái Key Pool Gemini
        from app.providers.gemini import get_key_pool
        pool = get_key_pool()
        key_pool_status = pool.get_status() if pool else []

        r.close()

        return {
            "queues": queues,
            "task_stats": stats,
            "total_result_keys": len(result_keys),
            "key_pool": key_pool_status,
        }
    except Exception as e:
        log.error(f"Failed to get queue stats: {e}")
        return {
            "queues": {},
            "task_stats": {},
            "total_result_keys": 0,
            "key_pool": [],
            "error": str(e),
        }
