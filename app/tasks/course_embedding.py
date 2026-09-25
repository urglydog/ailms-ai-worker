"""UC49 nâng cấp — đánh index embedding cho Course khi giảng viên tạo/sửa khóa học
(tiêu đề/mô tả) hoặc sửa tên chương/bài. Xem `be/CourseEmbeddingService.requestEmbedding`
(LPUSH vào `lms:course-embedding:jobs`) và `main.py::_course_embedding_queue_consumer`
(BRPOP rồi `.delay(...)` vào task này).

CỐ TÌNH đơn giản như `transcript_extraction.py`: lỗi ở bước này KHÔNG được coi là lỗi
nghiêm trọng — course đã lưu xong ở be/ TRƯỚC KHI job này chạy, nên course vẫn tìm được
qua bộ lọc category/level/priceType như cũ, chỉ mất phần rerank ngữ nghĩa của riêng nó
cho tới lần index thành công tiếp theo. Vì vậy không có callback báo lỗi về be/ (khác
transcript extraction — trạng thái embedding không gate gì user-facing).
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app
from app.providers import gemini, supabase_vector
from app.services import course_indexing

log = logging.getLogger(__name__)


async def _run_and_cleanup(
    course_id: int, title: str, description: str | None,
    chapter_titles: list[str], lesson_titles: list[str],
) -> dict:
    try:
        await course_indexing.index_course(course_id, title, description, chapter_titles, lesson_titles)
        return {"status": "COMPLETED", "courseId": course_id}
    except Exception as exc:
        log.warning("Danh index embedding cho course %s that bai: %s", course_id, exc)
        return {"status": "FAILED", "courseId": course_id, "error": str(exc)}
    finally:
        # Client httpx module-level phải đóng ở cuối MỖI task Celery (prefork tái sử
        # dụng process, mỗi task có event loop riêng qua asyncio.run()) — xem cùng lý
        # do ở `tasks/transcript_extraction.py`. BUG THẬT (25/09/2026): thiếu đóng
        # `supabase_vector` gây `RuntimeError: Event loop is closed` ở task Celery THỨ 2
        # trở đi trong cùng 1 worker process — kết nối keep-alive (httpcore/anyio) của
        # client cũ vẫn giữ tham chiếu tới event loop đã đóng.
        await asyncio.gather(gemini.aclose(), supabase_vector.aclose(), return_exceptions=True)


@celery_app.task(bind=True, name="app.tasks.course_embedding.embed_course")
def embed_course(
    self, course_id: int, title: str, description: str | None,
    chapter_titles: list[str], lesson_titles: list[str],
) -> dict:
    log.info("Bat dau danh index embedding: course=%s", course_id)
    return asyncio.run(_run_and_cleanup(course_id, title, description, chapter_titles, lesson_titles))
