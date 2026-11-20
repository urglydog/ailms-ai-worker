"""Ghi nhận mức dùng AI (21/11/2026) — MỌI lệnh gọi Gemini/Groq báo số token/giây thật về BE (`/api/internal/ai-usage`) để theo dõi chi phí.

Trước đây chỉ Flashcard/Mindmap/Quiz được ghi (qua BE), nên màn "AI Analytics" thấp hơn nhiều so với hóa đơn thật. Module này gom việc ghi nhận về MỘT chỗ (`gemini._execute_request`,
`gemini.embed_*`, `groq_asr.transcribe`); nơi gọi chỉ cần gắn nhãn tính năng bằng `usage_tag(...)` (hoặc tham số `feature=`). Ghi nhận là "best effort": lỗi gửi về BE chỉ được ghi log
(không chứa khóa/token) và KHÔNG BAO GIỜ làm hỏng lệnh gọi AI của người dùng.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Giữ tham chiếu tới các task đang gửi để event loop không thu dọn giữa chừng.
_pending: set[asyncio.Task] = set()


@dataclass(frozen=True)
class UsageTag:
    """Ngữ cảnh gắn cho các lệnh gọi AI bên trong khối `usage_tag`."""

    feature: str
    user_email: str | None = None
    user_id: int | None = None
    course_id: int | None = None
    lesson_id: int | None = None
    # True khi tính năng này đã được BE tự ghi bằng đường khác (học liệu Flashcard/Mindmap/Quiz) — không ghi lần nữa để tránh đếm đôi.
    already_logged: bool = False


_tag: ContextVar[UsageTag | None] = ContextVar("ai_usage_tag", default=None)


@contextmanager
def usage_tag(
    feature: str,
    *,
    user_email: str | None = None,
    user_id: int | None = None,
    course_id: int | None = None,
    lesson_id: int | None = None,
    already_logged: bool = False,
):
    """Gắn nhãn tính năng cho mọi lệnh gọi AI trong khối này (kể cả các task con tạo ra trong khối)."""
    token = _tag.set(UsageTag(feature, user_email, user_id, course_id, lesson_id, already_logged))
    try:
        yield
    finally:
        _tag.reset(token)


def set_tag(feature: str, *, user_email: str | None = None, already_logged: bool = False) -> None:
    """Gắn nhãn cho phần còn lại của request HIỆN TẠI (mỗi request HTTP chạy trong context riêng nên nhãn không rò sang request khác). Dùng ở đầu các route handler
    thay cho decorator — decorator làm FastAPI không phân giải được kiểu tham số khi module dùng `from __future__ import annotations`."""
    _tag.set(UsageTag(feature, user_email=user_email, already_logged=already_logged))


def current_tag() -> UsageTag | None:
    return _tag.get()


def estimate_tokens(text: str) -> int:
    """Ước lượng thô số token của một đoạn văn (~4 ký tự/token) — dùng cho nhúng dữ liệu vì API không trả số token."""
    return max(1, len(text) // 4)


def report_gemini(
    *, model: str, prompt_tokens: int, completion_tokens: int, thinking_tokens: int = 0, embedding: bool = False, estimated: bool = False
) -> None:
    """Báo một lệnh gọi Gemini (sinh văn bản hoặc nhúng). Không có nhãn thì ghi vào tính năng `UNTAGGED` để lộ ra chỗ chưa gắn nhãn."""
    tag = current_tag()
    if tag is not None and tag.already_logged:
        return
    _schedule(
        {
            "provider": "GEMINI",
            "feature": (tag.feature if tag else "UNTAGGED"),
            "model": model,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "thinkingTokens": thinking_tokens,
            "embedding": embedding,
            "estimated": estimated,
        },
        tag,
    )


def report_groq_audio(*, model: str, audio_seconds: float) -> None:
    """Báo một lần nhận dạng giọng nói Groq (tính tiền theo thời lượng âm thanh)."""
    tag = current_tag()
    if tag is not None and tag.already_logged:
        return
    _schedule(
        {"provider": "GROQ", "feature": (tag.feature if tag else "UNTAGGED"), "model": model, "audioSeconds": int(round(audio_seconds))},
        tag,
    )


def _schedule(body: dict, tag: UsageTag | None) -> None:
    if tag is not None:
        body.update({"userEmail": tag.user_email, "userId": tag.user_id, "courseId": tag.course_id, "lessonId": tag.lesson_id})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # không có event loop (vd test đồng bộ) — bỏ qua, không ném lỗi
    task = loop.create_task(_send(body))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _send(body: dict) -> None:
    try:
        # Import muộn để tránh vòng phụ thuộc (backend_client không cần biết module này).
        from app.http import backend_client

        await backend_client.report_ai_usage(body)
    except Exception as exc:  # noqa: BLE001 — ghi nhận chi phí không được làm hỏng luồng chính
        logger.warning("Khong ghi nhan duoc muc dung AI (%s)", type(exc).__name__)


def tagged(feature: str, *, already_logged: bool = False):
    """Decorator gắn nhãn tính năng cho MỌI lệnh gọi AI bên trong một hàm async (kể cả các lời gọi lồng nhau; nhãn bên trong ghi đè nhãn bên ngoài)."""

    def decorate(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            with usage_tag(feature, already_logged=already_logged):
                return await fn(*args, **kwargs)

        return wrapper

    return decorate
