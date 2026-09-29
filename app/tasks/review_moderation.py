import logging
import json
from celery import shared_task

from app.providers import gemini
from app.http import backend_client
import asyncio

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là hệ thống kiểm duyệt (Moderator). Nhiệm vụ của bạn LÀ PHÂN BIỆT GIỮA:
1. Góp ý tiêu cực / Chê bai chuyên môn (VD: 'giảng viên nói nhỏ', 'âm thanh rè', 'khóa học chán', 'dạy dở'): Phải được GIỮ LẠI (is_toxic = false).
2. Độc hại / Quấy rối / Spam (VD: chửi thề tục tĩu, công kích cá nhân, link quảng cáo cá độ, spam vô nghĩa): Phải bị LOẠI BỎ (is_toxic = true).

Hãy trả về chính xác JSON với schema:
{"is_toxic": boolean, "reason": "Lý do bằng tiếng Việt"}
"""

async def _moderate_review(review_id: int, text: str) -> None:
    try:
        res = await gemini.generate_conversation(
            [{"role": "user", "parts": [{"text": text}]}],
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "is_toxic": {"type": "BOOLEAN"},
                    "reason": {"type": "STRING"}
                },
                "required": ["is_toxic", "reason"]
            }
        )
        
        reply = res.text.strip()
        data = json.loads(reply)
        is_toxic = data.get("is_toxic", False)
        reason = data.get("reason", "Nội dung vi phạm")
        
        if is_toxic:
            log.info("Review %d bi danh dau la toxic: %s", review_id, reason)
            # Gọi ngược lại Backend
            client = backend_client.get_client()
            resp = await client.put(f"/api/internal/course-reviews/{review_id}/hide", json={"reason": reason})
            if resp.status_code != 200:
                log.error("Loi khi an review %d: %d %s", review_id, resp.status_code, resp.text)
        else:
            log.info("Review %d HOP LE.", review_id)
            
    except Exception as e:
        log.error("Loi khi cham diem review %d: %s", review_id, str(e))

@shared_task(name="app.tasks.review_moderation.moderate_review")
def moderate_review(review_id: int, text: str) -> dict:
    """Task Celery phan tich review doc hai."""
    log.info("Bat dau moderate review %d", review_id)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        loop.run_until_complete(_moderate_review(review_id, text))
        return {"status": "SUCCESS"}
    finally:
        # Don dep pool
        loop.run_until_complete(gemini.aclose())
        loop.run_until_complete(backend_client.aclose())
