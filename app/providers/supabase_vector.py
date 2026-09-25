"""Provider Vector Database — Supabase (pgvector), dùng cho RAG của Socratic Tutor.

Gọi thẳng PostgREST (REST/RPC) qua httpx mỏng, KHÔNG dùng SDK `supabase-py` — khớp quy
ước "anti-corruption layer mỏng" của các provider khác trong `app/providers/` (xem
`base.py`). Bảng `transcript_embeddings` và hàm RPC `match_transcript_embeddings` được
tạo thủ công trong Supabase SQL Editor (không phải Flyway của `be/`, project này không
sở hữu schema Postgres qua migration).

`settings.supabase_vector_url` đã có sẵn hậu tố `/rest/v1/` — các hàm dưới đây chỉ nối
thêm đường dẫn tương đối (`transcript_embeddings`, `rpc/...`).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings
from app.providers.base import build_client, map_http_error

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = build_client(
            settings.supabase_vector_url,
            read=30.0,
            max_connections=10,
            max_keepalive=5,
            headers={
                "apikey": settings.supabase_vector_key,
                "Authorization": f"Bearer {settings.supabase_vector_key}",
                "Content-Type": "application/json",
            },
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@dataclass(frozen=True)
class EmbeddingRow:
    """`segment_id` ở đây là `TranscriptSegment.seq` (số thứ tự câu trong bài học),
    KHÔNG PHẢI khóa chính MySQL — lúc đánh index (móc vào `dubbing_service.py`, TRƯỚC
    khi BE tạo `TranscriptSegment` thật), khóa chính MySQL chưa tồn tại. `seq` chỉ duy
    nhất TRONG 1 bài học nên khóa duy nhất của bảng là `(lesson_id, segment_id)`, không
    phải riêng `segment_id`.
    """

    segment_id: int
    lesson_id: int
    language: str
    start_sec: float
    end_sec: float
    content: str
    embedding: list[float]


@dataclass(frozen=True)
class MatchedSegment:
    """Một đoạn transcript truy xuất được, dùng dựng ngữ cảnh RAG (BR-TUTOR-03/04).

    `lesson_id` — UC30 mở rộng (13/09/2026): tìm kiếm giờ chạy trên NHIỀU bài học cùng lúc
    (`match_segments_by_lessons`), nên mỗi đoạn trả về phải tự mang theo nó thuộc bài nào, thay vì
    suy ra từ đúng 1 `lesson_id` cố định của cả lượt gọi như hàm `match_segments` (1 bài) cũ.
    """

    segment_id: int
    lesson_id: int
    content: str
    start_sec: float
    end_sec: float
    similarity: float


async def insert_embeddings(rows: list[EmbeddingRow]) -> None:
    """Ghi embedding — dùng upsert theo `(lesson_id, segment_id)` (UNIQUE) để job đánh
    index chạy lại (retry) không tạo dòng trùng.
    """
    if not rows:
        return
    payload = [
        {
            "segment_id": r.segment_id,
            "lesson_id": r.lesson_id,
            "language": r.language,
            "start_sec": r.start_sec,
            "end_sec": r.end_sec,
            "content": r.content,
            "embedding": r.embedding,
        }
        for r in rows
    ]
    try:
        resp = await get_client().post(
            "transcript_embeddings",
            params={"on_conflict": "lesson_id,segment_id"},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc


async def match_segments(
    lesson_id: int, query_embedding: list[float], *, limit: int | None = None, min_similarity: float | None = None,
) -> list[MatchedSegment]:
    """RAG retrieval cho DUNG 1 bai hoc — gọi hàm RPC `match_transcript_embeddings` (BR-TUTOR-04:
    tối đa `settings.rag_top_k` đoạn, ngưỡng `settings.rag_min_similarity`). Chỉ còn dùng bởi
    `tutor_service._answer_for_lesson` (luồng giải thích quiz) — Socratic Tutor chính giờ dùng
    `match_segments_by_lessons` (tìm xuyên suốt khóa, xem hàm đó).
    """
    payload = {
        "query_embedding": query_embedding,
        "match_lesson_id": lesson_id,
        "match_count": limit or settings.rag_top_k,
        "min_similarity": min_similarity if min_similarity is not None else settings.rag_min_similarity,
    }
    try:
        resp = await get_client().post("rpc/match_transcript_embeddings", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc

    return [
        MatchedSegment(
            segment_id=row["segment_id"],
            # Hàm RPC 1-bài không trả lesson_id (chỉ tìm trong đúng 1 bài) — caller đã biết sẵn.
            lesson_id=lesson_id,
            content=row["content"],
            start_sec=float(row["start_sec"]),
            end_sec=float(row["end_sec"]),
            similarity=float(row["similarity"]),
        )
        for row in resp.json()
    ]


async def match_segments_by_lessons(
    lesson_ids: list[int], query_embedding: list[float], *, limit: int | None = None,
    min_similarity: float | None = None,
) -> list[MatchedSegment]:
    """UC30 mở rộng (13/09/2026) — RAG retrieval trên NHIỀU bài học cùng lúc (toàn bộ khóa học),
    gọi hàm RPC MỚI `match_transcript_embeddings_by_lessons` (khác `match_transcript_embeddings`
    cũ — hàm cũ chỉ nhận đúng 1 `lesson_id`). Hàm RPC này cần được tạo thủ công trong Supabase SQL
    Editor giống hàm cũ (xem `docs/`/tin nhắn bàn giao SQL) — trả về thêm cột `lesson_id` vì kết
    quả giờ có thể thuộc bất kỳ bài nào trong danh sách truyền vào.
    """
    if not lesson_ids:
        return []
    payload = {
        "query_embedding": query_embedding,
        "match_lesson_ids": lesson_ids,
        "match_count": limit or settings.rag_top_k,
        "min_similarity": min_similarity if min_similarity is not None else settings.rag_min_similarity,
    }
    try:
        resp = await get_client().post("rpc/match_transcript_embeddings_by_lessons", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc

    return [
        MatchedSegment(
            segment_id=row["segment_id"],
            lesson_id=row["lesson_id"],
            content=row["content"],
            start_sec=float(row["start_sec"]),
            end_sec=float(row["end_sec"]),
            similarity=float(row["similarity"]),
        )
        for row in resp.json()
    ]


@dataclass(frozen=True)
class CourseEmbeddingRow:
    """1 vector DUY NHẤT cho mỗi Course (khác Tutor: 1 vector/segment) — UC49 nâng cấp.
    `content` là title + description + tên chương/bài đã ghép, dùng lại để debug/trace
    xem embedding được sinh từ text gì.
    """

    course_id: int
    content: str
    embedding: list[float]


@dataclass(frozen=True)
class MatchedCourse:
    course_id: int
    similarity: float


async def insert_course_embedding(row: CourseEmbeddingRow) -> None:
    """Upsert theo `course_id` (PK) — job đánh index chạy lại (sửa khóa học) ghi đè,
    không tạo dòng trùng.
    """
    payload = {
        "course_id": row.course_id,
        "content": row.content,
        "embedding": row.embedding,
    }
    try:
        resp = await get_client().post(
            "course_embeddings",
            params={"on_conflict": "course_id"},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc


async def match_courses_by_ids(
    course_ids: list[int], query_embedding: list[float], *, limit: int | None = None,
    min_similarity: float | None = None,
) -> list[MatchedCourse]:
    """UC49 nâng cấp — rerank bằng similarity TRONG tập course_id đã lọc cứng
    (category/level/priceType) ở BE. Gọi RPC `match_courses_by_ids` (tạo thủ công
    trong Supabase SQL Editor, cùng đợt với bảng `course_embeddings`).
    """
    if not course_ids:
        return []
    payload = {
        "query_embedding": query_embedding,
        "match_course_ids": course_ids,
        "match_count": limit or settings.discovery_similarity_top_k,
        "min_similarity": min_similarity if min_similarity is not None else settings.discovery_min_similarity,
    }
    try:
        resp = await get_client().post("rpc/match_courses_by_ids", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc

    return [
        MatchedCourse(course_id=row["course_id"], similarity=float(row["similarity"]))
        for row in resp.json()
    ]


async def match_courses(
    query_embedding: list[float], *, limit: int | None = None, min_similarity: float | None = None,
) -> list[MatchedCourse]:
    """Tìm kiếm KHÔNG lọc cứng, toàn bộ `course_embeddings` — dùng cho backfill/verify
    thủ công, KHÔNG dùng ở luồng chat chính (luôn phải qua `match_courses_by_ids` để
    tôn trọng bộ lọc status/visibility mà BE đã áp dụng).
    """
    payload = {
        "query_embedding": query_embedding,
        "match_count": limit or settings.discovery_similarity_top_k,
        "min_similarity": min_similarity if min_similarity is not None else settings.discovery_min_similarity,
    }
    try:
        resp = await get_client().post("rpc/match_courses", json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc

    return [
        MatchedCourse(course_id=row["course_id"], similarity=float(row["similarity"]))
        for row in resp.json()
    ]
