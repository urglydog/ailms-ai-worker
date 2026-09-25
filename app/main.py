"""FastAPI app — phục vụ 2 use case ĐỒNG BỘ.

Chỉ UC30 (Socratic Tutor) và UC49 (Course Discovery) đi qua đây, vì chúng trả lời
trực tiếp cho người dùng. Các tác vụ nặng (UC19 pipeline lồng tiếng, UC25 sinh học
liệu) chạy bất đồng bộ qua Celery — xem `app/celery_app.py`.

`lifespan` đóng toàn bộ provider client khi shutdown; đây là lý do các provider dùng
client module-level thay vì tạo mới mỗi request.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import redis_client
from app.api import admin, discovery, health, instructor_ai, live_admin, proctoring, tutor
from app.http import backend_client
from app.providers import azure_tts, gemini, groq_asr, supabase_vector
from app.tasks.dubbing import run_pipeline

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def _dubbing_queue_consumer() -> None:
    """`be/` (F5.1) LPUSH job vào `lms:dubbing:jobs`; vòng lặp nền này BRPOP rồi giao
    cho Celery qua `.delay(...)` — tách hàng đợi "job đến" (do `be/` sở hữu, JSON đơn
    giản) khỏi hàng đợi nội bộ của Celery, tránh chồng 2 tầng queue lên nhau.
    """
    log.info("Dubbing queue consumer: bat dau lang nghe lms:dubbing:jobs")
    while True:
        try:
            job = await redis_client.brpop_job(timeout_sec=5)
            if job is None:
                continue
            log.info("Nhan job long tieng tu hang doi: %s", job)
            run_pipeline.delay(
                job_id=job["jobId"],
                lesson_id=job["lessonId"],
                video_url=job["videoUrl"],
                target_language=job["targetLanguage"],
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - vong lap nen KHONG duoc chet vi 1 job loi dinh dang
            log.exception("Loi khi xu ly hang doi lms:dubbing:jobs, tiep tuc lang nghe")
            await asyncio.sleep(1)


async def _material_queue_consumer() -> None:
    log.info("Material queue consumer: bat dau lang nghe lms:material:jobs")
    while True:
        try:
            job = await redis_client.brpop_job("lms:material:jobs", timeout_sec=5)
            if job is None:
                continue
            log.info("Nhan job sinh hoc lieu tu hang doi: %s", job)
            from app.tasks.material import generate_material
            generate_material.delay(generation_id=job["generationId"])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Loi khi xu ly hang doi lms:material:jobs, tiep tuc lang nghe")
            await asyncio.sleep(1)


async def _transcript_queue_consumer() -> None:
    """UC34 mở rộng — `be/` LPUSH ngay sau khi nạp video xong (xem
    `TranscriptExtractionService`), TÁCH khỏi `lms:dubbing:jobs` vì job này không có `jobId`
    (không gắn với 1 `AiJob` nào — xem docblock `app/tasks/transcript_extraction.py`).
    """
    log.info("Transcript queue consumer: bat dau lang nghe lms:transcript:jobs")
    while True:
        try:
            job = await redis_client.brpop_job("lms:transcript:jobs", timeout_sec=5)
            if job is None:
                continue
            log.info("Nhan job trich script goc tu hang doi: %s", job)
            from app.tasks.transcript_extraction import extract_source_transcript
            extract_source_transcript.delay(
                lesson_id=job["lessonId"],
                video_source=job["videoSource"],
                video_url=job["videoUrl"],
                duration_sec=job.get("durationSec") or 0,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Loi khi xu ly hang doi lms:transcript:jobs, tiep tuc lang nghe")
            await asyncio.sleep(1)


async def _course_embedding_queue_consumer() -> None:
    """UC49 nâng cấp — `be/` LPUSH ngay sau khi tạo/sửa course (tiêu đề/mô tả) hoặc sửa
    tên chương/bài (xem `CourseEmbeddingService.requestEmbedding`), TÁCH khỏi các hàng
    đợi khác vì job này không gắn `jobId`/`AiJob` nào.
    """
    log.info("Course embedding queue consumer: bat dau lang nghe lms:course-embedding:jobs")
    while True:
        try:
            job = await redis_client.brpop_job("lms:course-embedding:jobs", timeout_sec=5)
            if job is None:
                continue
            log.info("Nhan job danh index embedding course tu hang doi: %s", job)
            from app.tasks.course_embedding import embed_course
            embed_course.delay(
                course_id=job["courseId"],
                title=job["title"],
                description=job.get("description"),
                chapter_titles=job.get("chapterTitles") or [],
                lesson_titles=job.get("lessonTitles") or [],
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Loi khi xu ly hang doi lms:course-embedding:jobs, tiep tuc lang nghe")
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AI Worker API khoi dong")
    dubbing_task = asyncio.create_task(_dubbing_queue_consumer())
    material_task = asyncio.create_task(_material_queue_consumer())
    transcript_task = asyncio.create_task(_transcript_queue_consumer())
    course_embedding_task = asyncio.create_task(_course_embedding_queue_consumer())
    yield
    dubbing_task.cancel()
    material_task.cancel()
    transcript_task.cancel()
    course_embedding_task.cancel()
    # Đóng client của TỪNG provider (mỗi provider một client riêng — bulkhead).
    log.info("Dang dong provider client...")
    await groq_asr.aclose()
    await gemini.aclose()
    await azure_tts.aclose()
    await supabase_vector.aclose()
    await backend_client.aclose()
    await redis_client.aclose()
    log.info("AI Worker API da dung")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI-Powered LMS — AI Worker",
    description=(
        "Dich vu AI: pipeline long tieng (Celery), Socratic Tutor va Course Discovery (HTTP). "
        "Khong ket noi MySQL truc tiep — moi thay doi du lieu goi callback ve backend."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tutor.router)
app.include_router(discovery.router)
app.include_router(admin.router)
app.include_router(instructor_ai.router)
app.include_router(proctoring.router)
app.include_router(live_admin.router)
app.include_router(live_admin.transcription_router)
