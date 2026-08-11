"""Admin endpoints — thống kê nội bộ cho Admin Dashboard.

Không yêu cầu JWT (đã kiểm soát bởi INTERNAL_API_TOKEN header).
Chỉ dùng trong mạng nội bộ Docker; không expose ra ngoài.
"""

from __future__ import annotations

import logging

import redis as redis_sync
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_internal_token(x_internal_token: Optional[str] = Header(default=None)):
    """Bảo vệ endpoint — chỉ backend nội bộ mới có token này."""
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Forbidden: invalid internal token")


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
