"""FastAPI app — phục vụ 2 use case ĐỒNG BỘ.

Chỉ UC30 (Socratic Tutor) và UC49 (Course Discovery) đi qua đây, vì chúng trả lời
trực tiếp cho người dùng. Các tác vụ nặng (UC19 pipeline lồng tiếng, UC25 sinh học
liệu) chạy bất đồng bộ qua Celery — xem `app/celery_app.py`.

`lifespan` đóng toàn bộ provider client khi shutdown; đây là lý do các provider dùng
client module-level thay vì tạo mới mỗi request.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, discovery, health, instructor_ai, tutor
from app.providers import edge_tts, gemini, groq_asr

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AI Worker API khoi dong")
    yield
    # Đóng client của TỪNG provider (mỗi provider một client riêng — bulkhead).
    log.info("Dang dong provider client...")
    await groq_asr.aclose()
    await gemini.aclose()
    await edge_tts.aclose()
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
