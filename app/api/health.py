"""Health check — docker-compose va RUNNING.md dung endpoint nay."""

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Tra ve trang thai va cau hinh khong bi mat (khong lo API key)."""
    return {
        "status": "ok",
        "service": "ai-worker",
        "asr_backend": settings.asr_backend,
        "gemini_model": settings.gemini_model,
        "chunk_minutes": settings.chunk_minutes,
    }
