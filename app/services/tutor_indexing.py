"""Đánh index embedding cho Socratic Tutor (UC30) — việc phát sinh của F8.1, móc vào
cuối pipeline lồng tiếng (F5.2, xem `dubbing_service.py`) đúng lần đầu bài học được
bóc băng, KHÔNG lặp lại cho mỗi ngôn ngữ dịch sau đó.

Chỉ embed CÂU GỐC (chưa dịch) — đây là ngữ cảnh Gia sư AI dùng để trả lời, không phụ
thuộc ngôn ngữ lồng tiếng nào đã chọn.
"""

from __future__ import annotations

from app.models import Segment
from app.providers import gemini, supabase_vector


async def index_segments(lesson_id: int, language: str | None, segments: list[Segment]) -> None:
    if not segments:
        return

    rows: list[supabase_vector.EmbeddingRow] = []
    for seg in segments:
        vector = await gemini.embed_content(seg.text)
        rows.append(
            supabase_vector.EmbeddingRow(
                segment_id=seg.seq,
                lesson_id=lesson_id,
                language=language or "unknown",
                start_sec=seg.start,
                end_sec=seg.end,
                content=seg.text,
                embedding=vector,
            )
        )

    await supabase_vector.insert_embeddings(rows)
