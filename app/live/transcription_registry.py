"""F11.5 mở rộng — sổ theo dõi các `TranscriptionAgentSession` đang chạy, khoá theo `session_id`
(khớp `LiveSession.id` phía `be/`). Tách RIÊNG khỏi `registry.py` (khoá theo `track_id`) dù cùng
mẫu hệt nhau — 2 không gian khoá khác nhau (session_id của `LiveSession` vs track_id của
`LiveLanguageTrack`), gộp chung 1 dict dễ đụng độ khoá nếu 2 bảng tình cờ trùng ID.
"""

from __future__ import annotations

import asyncio
import logging

from app.live.transcription_agent import TranscriptionAgentConfig, TranscriptionAgentSession

log = logging.getLogger(__name__)

_sessions: dict[int, tuple[TranscriptionAgentSession, asyncio.Task]] = {}


def start(config: TranscriptionAgentConfig) -> None:
    if config.session_id in _sessions:
        log.warning(
            "Live session %s: da co Transcription Agent dang chay, bo qua yeu cau start trung",
            config.session_id,
        )
        return
    session = TranscriptionAgentSession(config)
    task = asyncio.create_task(session.run())
    task.add_done_callback(lambda t: _on_task_done(config.session_id, t))
    _sessions[config.session_id] = (session, task)


def stop(session_id: int) -> bool:
    entry = _sessions.get(session_id)
    if entry is None:
        log.info("Live session %s: khong co Transcription Agent nao dang chay (co the da tu dung)", session_id)
        return False
    session, _task = entry
    session.stop()
    return True


def _on_task_done(session_id: int, task: asyncio.Task) -> None:
    _sessions.pop(session_id, None)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Live session %s: Transcription Agent ket thuc voi loi chua bat duoc: %s", session_id, exc)
