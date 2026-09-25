"""Đánh index embedding cho Course Discovery (UC49 nâng cấp) — sinh 1 vector DUY NHẤT
cho mỗi khóa học (khác Tutor: 1 vector/segment), ghép title + description + tên
chương/bài để câu hỏi tự nhiên KHÔNG trùng từ khóa chính xác với tên khóa vẫn khớp
ngữ nghĩa được (xem `api/discovery.py` bước rerank bằng similarity).

Móc vào `CourseService.create/update` (be/) qua hàng đợi `lms:course-embedding:jobs`
(xem `main.py::_course_embedding_queue_consumer` và `tasks/course_embedding.py`).
"""

from __future__ import annotations

from app.providers import gemini, supabase_vector

# Giới hạn độ dài text đưa vào embedContent — phòng khóa học có mô tả/nhiều
# chương-bài rất dài vượt input limit của model embedding.
_MAX_CONTENT_CHARS = 8000


def build_embedding_text(
    title: str, description: str | None, chapter_titles: list[str], lesson_titles: list[str],
) -> str:
    parts = [title, description or "", *chapter_titles, *lesson_titles]
    text = "\n".join(p for p in parts if p)
    return text[:_MAX_CONTENT_CHARS]


async def index_course(
    course_id: int, title: str, description: str | None,
    chapter_titles: list[str], lesson_titles: list[str],
) -> None:
    text = build_embedding_text(title, description, chapter_titles, lesson_titles)
    if not text:
        return
    vector = await gemini.embed_content(text)
    await supabase_vector.insert_course_embedding(
        supabase_vector.CourseEmbeddingRow(course_id=course_id, content=text, embedding=vector)
    )
