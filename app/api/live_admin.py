"""F11.3 (UC52) — `be/` gọi vào đây để bật/tắt Translation Agent của 1 LiveLanguageTrack.

Không yêu cầu JWT (đã kiểm soát bởi INTERNAL_API_TOKEN header) — giống hệt mô hình
`/admin/dubbing-jobs/{id}/cancel` đã có ở Giai đoạn 5, chỉ dùng trong mạng nội bộ Docker.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.live import registry
from app.live.translation_agent import TranslationAgentConfig

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/live-tracks", tags=["live"])


def _verify_internal_token(x_internal_token: Optional[str] = Header(default=None)):
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Forbidden: invalid internal token")


class StartTrackReq(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # `be/` gửi JSON camelCase (khớp quy ước REST của cả dự án).
    room_name: str = Field(alias="roomName")
    server_url: str = Field(alias="serverUrl")
    agent_token: str = Field(alias="agentToken")
    instructor_identity: str = Field(alias="instructorIdentity")
    source_language: str = Field(alias="sourceLanguage")
    target_language: str = Field(alias="targetLanguage")
    voice_name: str = Field(alias="voiceName")
    track_name: str = Field(alias="trackName")


@router.post("/{track_id}/start", dependencies=[Depends(_verify_internal_token)])
async def start_live_track(track_id: int, req: StartTrackReq) -> dict:
    """`be/` ĐÃ ghi `LiveLanguageTrack.status=ACTIVE` trước khi gọi tới đây (nguồn sự thật là
    DB) — đây chỉ là lệnh mở agent thật, chạy nền dưới dạng 1 asyncio task trong tiến trình
    `ai-api` hiện có (xem `app/live/translation_agent.py` để biết vì sao không cần tiến trình
    riêng). Trả về ngay lập tức, KHÔNG chờ agent join phòng xong — độ trễ vài giây đầu tiên
    (BR-LIVE-08) đã bao gồm cả bước này.
    """
    registry.start(TranslationAgentConfig(
        track_id=track_id,
        room_name=req.room_name,
        server_url=req.server_url,
        agent_token=req.agent_token,
        instructor_identity=req.instructor_identity,
        source_language=req.source_language,
        target_language=req.target_language,
        voice_name=req.voice_name,
        track_name=req.track_name,
    ))
    log.info("Live track %s: da nhan lenh start Translation Agent", track_id)
    return {"started": True}


@router.post("/{track_id}/stop", dependencies=[Depends(_verify_internal_token)])
async def stop_live_track(track_id: int) -> dict:
    """`be/` ĐÃ ghi `LiveLanguageTrack.status=STOPPED` trước khi gọi tới đây — best-effort,
    giống hệt tinh thần `/admin/dubbing-jobs/{id}/cancel`."""
    stopped = registry.stop(track_id)
    log.info("Live track %s: da nhan lenh stop Translation Agent (tung chay: %s)", track_id, stopped)
    return {"stopped": stopped}
