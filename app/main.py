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
from app.api import admin, discovery, health, instructor_ai, tutor
from app.http import backend_client
from app.providers import edge_tts, gemini, groq_asr, supabase_vector
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AI Worker API khoi dong")
    dubbing_task = asyncio.create_task(_dubbing_queue_consumer())
    material_task = asyncio.create_task(_material_queue_consumer())
    yield
    dubbing_task.cancel()
    material_task.cancel()
    # Đóng client của TỪNG provider (mỗi provider một client riêng — bulkhead).
    log.info("Dang dong provider client...")
    await groq_asr.aclose()
    await gemini.aclose()
    await edge_tts.aclose()
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
