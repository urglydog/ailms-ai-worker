"""F11.3 — sổ theo dõi các `TranslationAgentSession` đang chạy trong tiến trình `ai-api`, khoá
theo `track_id` (khớp `LiveLanguageTrack.id` phía `be/`). `be/` là nguồn sự thật cho trạng thái
track; sổ này chỉ là bookkeeping CỤC BỘ để `/admin/live-tracks/{id}/stop` biết tìm task nào để
dừng — mất khi `ai-api` restart, chấp nhận được vì `be/` không dựa vào sổ này để biết track nào
đang "thật sự" chạy (nếu `ai-api` restart giữa lúc có track ACTIVE, track đó coi như mất agent,
học viên phải rời rồi kích hoạt lại — biết trước, chưa xử lý tự phục hồi ở đây).
"""

from __future__ import annotations

import asyncio
import logging

from app.live.translation_agent import TranslationAgentConfig, TranslationAgentSession

log = logging.getLogger(__name__)

_sessions: dict[int, tuple[TranslationAgentSession, asyncio.Task]] = {}


def start(config: TranslationAgentConfig) -> None:
    if config.track_id in _sessions:
        log.warning("Live track %s: da co Translation Agent dang chay, bo qua yeu cau start trung", config.track_id)
        return
    session = TranslationAgentSession(config)
    task = asyncio.create_task(session.run())
    task.add_done_callback(lambda t: _on_task_done(config.track_id, t))
    _sessions[config.track_id] = (session, task)


def stop(track_id: int) -> bool:
    entry = _sessions.get(track_id)
    if entry is None:
        log.info("Live track %s: khong co Translation Agent nao dang chay (co the da tu dung)", track_id)
        return False
    session, _task = entry
    session.stop()
    return True


def _on_task_done(track_id: int, task: asyncio.Task) -> None:
    _sessions.pop(track_id, None)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Live track %s: Translation Agent ket thuc voi loi chua bat duoc: %s", track_id, exc)
