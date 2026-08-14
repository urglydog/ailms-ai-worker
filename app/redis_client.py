"""Redis dùng chung — hàng đợi job (`be/` LPUSH) và Pub/Sub tiến độ (worker publish).

Xem `lms-dubbing-pipeline`:
  · `lms:dubbing:jobs`      List  — `be/` LPUSH, `ai-api` BRPOP rồi gọi `run_pipeline.delay(...)`
  · `lms:dubbing:progress`  Pub/Sub — worker publish, `be/` (F5.3) forward qua STOMP

Dùng client redis-py bất đồng bộ (`redis.asyncio`) vì toàn bộ pipeline dùng asyncio.
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from app.config import settings

log = logging.getLogger(__name__)

QUEUE_KEY = "lms:dubbing:jobs"
PROGRESS_CHANNEL = "lms:dubbing:progress"

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def brpop_job(queue_key: str = QUEUE_KEY, timeout_sec: int = 5) -> dict | None:
    """Lấy 1 job từ hàng đợi `be/` LPUSH. None nếu hết timeout (hàng đợi rỗng)."""
    result = await get_client().brpop(queue_key, timeout=timeout_sec)
    if result is None:
        return None
    _key, raw_payload = result
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError:
        log.error("Payload hang doi %s khong phai JSON hop le: %r", queue_key, raw_payload)
        return None


async def publish_progress(job_id: int, lesson_id: int, **fields: object) -> None:
    """Bắn tiến độ realtime. `be/` (F5.3) sẽ subscribe kênh này và forward qua STOMP.

    Không có subscriber cũng không sao — Pub/Sub của Redis không lưu lại message,
    chỉ đơn giản là không ai nhận (không lỗi, không rơi vào hàng đợi treo).
    """
    payload = {"jobId": job_id, "lessonId": lesson_id, **fields}
    await get_client().publish(PROGRESS_CHANNEL, json.dumps(payload))
