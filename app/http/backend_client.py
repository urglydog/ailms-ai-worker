"""Client HTTP gọi callback về `be/` — AI Worker KHÔNG kết nối MySQL trực tiếp.

Xác thực bằng header `X-Internal-Token` (secret dùng chung `INTERNAL_API_TOKEN`, xem
`docker-compose.yml`), KHÔNG phải JWT. Client RIÊNG (bulkhead) theo `lms-ai-worker-rules`
mục 5 — một backend chậm không được làm cạn pool mà Gemini/Groq/Edge-TTS đang cần.

Hợp đồng khớp `com.lms.dubbing.dto.InternalDubbingDto` phía backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import httpx

from app.config import settings
from app.providers.base import build_client, map_http_error

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = build_client(
            settings.internal_be_url,
            read=30.0,
            max_connections=10,
            max_keepalive=5,
            headers={"X-Internal-Token": settings.internal_api_token},
        )
    return _client


async def aclose() -> None:
    """Gọi khi worker process kết thúc (không có FastAPI lifespan trong Celery worker)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@dataclass(frozen=True)
class SourceSegment:
    """Một câu của bản ghi âm GỐC, đã có sẵn — dùng khi tái sử dụng transcript (BR-DUB-01)."""

    seq: int
    start_sec: Decimal
    end_sec: Decimal
    text: str


@dataclass(frozen=True)
class JobContext:
    job_id: int
    lesson_id: int
    video_source: str
    video_url: str
    duration_sec: int
    source_language: str | None
    target_language: str
    voice_name: str
    source_transcript_available: bool
    source_segments: list[SourceSegment] = field(default_factory=list)


def segment_to_json(
    seq: int,
    start_sec: Decimal,
    end_sec: Decimal,
    text: str,
    *,
    speech_rate: Decimal | None = None,
    was_summarized: bool | None = None,
) -> dict:
    """Chuẩn hoá 1 câu thoại thành JSON khớp `InternalDubbingDto.SegmentDto`."""
    return {
        "seq": seq,
        "startSec": str(start_sec),
        "endSec": str(end_sec),
        "text": text,
        "speechRate": str(speech_rate) if speech_rate is not None else None,
        "wasSummarized": was_summarized,
    }


async def _request(method: str, path: str, *, json_body: dict | None = None) -> httpx.Response:
    try:
        response = await get_client().request(method, path, json=json_body)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc


async def get_context(job_id: int) -> JobContext:
    response = await _request("GET", f"/api/internal/dubbing/jobs/{job_id}/context")
    payload = response.json()
    segments = [
        SourceSegment(
            seq=s["seq"],
            start_sec=Decimal(str(s["startSec"])),
            end_sec=Decimal(str(s["endSec"])),
            text=s["text"],
        )
        for s in payload.get("sourceSegments") or []
    ]
    return JobContext(
        job_id=payload["jobId"],
        lesson_id=payload["lessonId"],
        video_source=payload["videoSource"],
        video_url=payload["videoUrl"],
        duration_sec=payload["durationSec"],
        source_language=payload.get("sourceLanguage"),
        target_language=payload["targetLanguage"],
        voice_name=payload["voiceName"],
        source_transcript_available=payload["sourceTranscriptAvailable"],
        source_segments=segments,
    )


async def start_job(job_id: int, *, total_chunks: int, celery_task_id: str | None) -> None:
    await _request(
        "POST",
        f"/api/internal/dubbing/jobs/{job_id}/start",
        json_body={"totalChunks": total_chunks, "celeryTaskId": celery_task_id},
    )


async def upsert_chunk_completed(
    job_id: int,
    chunk_index: int,
    *,
    start_sec: int,
    end_sec: int,
    audio_file_url: str,
    detected_source_language: str | None,
    source_segments: list[dict] | None,
    target_segments: list[dict],
) -> None:
    """BR-CHUNK-03: gọi ngay khi MỘT chunk xong, không đợi cả job — chunk 0 xong là
    `AudioTrack` đã ở PARTIAL, học viên vào học được.
    """
    await _request(
        "PUT",
        f"/api/internal/dubbing/jobs/{job_id}/chunks/{chunk_index}",
        json_body={
            "status": "COMPLETED",
            "startSec": start_sec,
            "endSec": end_sec,
            "audioFileUrl": audio_file_url,
            "detectedSourceLanguage": detected_source_language,
            "sourceSegments": source_segments,
            "targetSegments": target_segments,
        },
    )


async def upsert_chunk_failed(job_id: int, chunk_index: int, *, start_sec: int, end_sec: int, error_message: str) -> None:
    """BR-CHUNK-04: hết retry cho MỘT chunk — chunk đó FAILED, các chunk khác không bị ảnh hưởng."""
    await _request(
        "PUT",
        f"/api/internal/dubbing/jobs/{job_id}/chunks/{chunk_index}",
        json_body={"status": "FAILED", "startSec": start_sec, "endSec": end_sec, "errorMessage": error_message},
    )


async def finish_completed(job_id: int, *, final_url: str, duration_sec: int, file_size: int) -> None:
    await _request(
        "POST",
        f"/api/internal/dubbing/jobs/{job_id}/finish",
        json_body={"outcome": "COMPLETED", "finalUrl": final_url, "durationSec": duration_sec, "fileSize": file_size},
    )


async def finish_failed(job_id: int, *, error_message: str) -> None:
    await _request(
        "POST",
        f"/api/internal/dubbing/jobs/{job_id}/finish",
        json_body={"outcome": "FAILED", "errorMessage": error_message},
    )


async def finish_skipped(job_id: int, *, reason: str) -> None:
    """BR-DUB-10: ký âm rỗng hoặc thoại < 10% thời lượng — KHÔNG retry."""
    await _request(
        "POST",
        f"/api/internal/dubbing/jobs/{job_id}/finish",
        json_body={"outcome": "SKIPPED", "errorMessage": reason},
    )


@dataclass(frozen=True)
class TutorContext:
    """Ngữ cảnh bài học cho prompt Socratic Tutor (UC30) — lấy qua endpoint nội bộ,
    KHÔNG dùng client rời rạc như `discovery.py`/`instructor_ai.py` (2 file đó tự mở
    `httpx.AsyncClient()` với header `Authorization: Bearer` sai quy ước — client
    bulkhead + header `X-Internal-Token` của module này mới là chuẩn của dự án).
    """

    lesson_title: str
    source_language: str | None
    duration_sec: int


async def get_tutor_context(lesson_id: int) -> TutorContext:
    response = await _request("GET", f"/api/internal/tutor/lessons/{lesson_id}/context")
    payload = response.json()
    return TutorContext(
        lesson_title=payload["lessonTitle"],
        source_language=payload.get("sourceLanguage"),
        duration_sec=payload["durationSec"],
    )


async def finish_source_unavailable(job_id: int, *, error_message: str) -> None:
    """BR-DUB-11: nguồn video không còn khả dụng — backend đánh dấu Lesson.status=UNAVAILABLE."""
    await _request(
        "POST",
        f"/api/internal/dubbing/jobs/{job_id}/finish",
        json_body={"outcome": "SOURCE_UNAVAILABLE", "errorMessage": error_message},
    )

@dataclass(frozen=True)
class MaterialContext:
    generation_id: int
    course_id: int
    course_title: str
    material_type: str
    language: str
    scope_type: str
    scope_ref_id: int | None
    quantity_level: str | None
    difficulty_level: str | None
    transcripts: list[dict]

async def get_material_context(generation_id: int) -> MaterialContext:
    response = await _request("GET", f"/api/internal/materials/{generation_id}/context")
    payload = response.json()
    return MaterialContext(
        generation_id=payload["generationId"],
        course_id=payload["courseId"],
        course_title=payload["courseTitle"],
        material_type=payload["materialType"],
        language=payload["language"],
        scope_type=payload["scopeType"],
        scope_ref_id=payload.get("scopeRefId"),
        quantity_level=payload.get("quantityLevel"),
        difficulty_level=payload.get("difficultyLevel"),
        transcripts=payload.get("transcripts") or [],
    )

async def finish_material_generation(generation_id: int, *, outcome: str, error_message: str | None = None, mermaid_code: str | None = None) -> None:
    payload = {"outcome": outcome}
    if error_message:
        payload["errorMessage"] = error_message
    if mermaid_code:
        payload["mermaidCode"] = mermaid_code
    
    await _request("POST", f"/api/internal/materials/{generation_id}/finish", json_body=payload)

